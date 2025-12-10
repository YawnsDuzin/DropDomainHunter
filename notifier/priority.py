"""
Domain Sniper - 알림 우선순위 시스템
도메인 점수, 만료일 등을 기반으로 알림 우선순위를 결정합니다.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from enum import IntEnum
from collections import defaultdict

import structlog

logger = structlog.get_logger()


class Priority(IntEnum):
    """알림 우선순위 레벨"""
    CRITICAL = 1   # 즉시 알림 (90점+ 또는 오늘 만료)
    HIGH = 2       # 높음 (80점+ 또는 3일 내 만료)
    MEDIUM = 3     # 중간 (70점+ 또는 7일 내 만료)
    LOW = 4        # 낮음 (그 외)
    BATCH = 5      # 배치 처리 (60점 미만)


@dataclass
class PriorityConfig:
    """우선순위 설정"""
    # 점수 임계값
    critical_score: int = 90
    high_score: int = 80
    medium_score: int = 70
    low_score: int = 60

    # 만료일 임계값 (일)
    critical_days: int = 1
    high_days: int = 3
    medium_days: int = 7

    # 반복 알림 간격 (분)
    critical_repeat_interval: int = 30
    high_repeat_interval: int = 60

    # 배치 알림 간격 (분)
    batch_interval: int = 60

    # 하루 최대 알림 수 (스팸 방지)
    max_daily_alerts: int = 100


@dataclass
class PrioritizedDomain:
    """우선순위가 지정된 도메인"""
    domain: Any  # Domain 객체
    priority: Priority
    reasons: List[str] = field(default_factory=list)
    scheduled_time: Optional[datetime] = None
    repeat_count: int = 0


class NotificationPriorityManager:
    """알림 우선순위 관리자"""

    def __init__(self, config: Optional[PriorityConfig] = None):
        self.config = config or PriorityConfig()
        self._batch_queue: List[PrioritizedDomain] = []
        self._sent_today: int = 0
        self._last_reset: datetime = datetime.now()
        self._repeat_schedule: Dict[str, datetime] = {}  # domain_id -> next_repeat_time

    def calculate_priority(self, domain: Any) -> PrioritizedDomain:
        """
        도메인의 알림 우선순위 계산

        Args:
            domain: Domain 객체

        Returns:
            PrioritizedDomain
        """
        reasons = []
        priority = Priority.LOW

        # 점수 기반 우선순위
        score = domain.total_score or 0
        days_left = domain.days_until_expiry

        # Critical 조건
        if score >= self.config.critical_score:
            priority = Priority.CRITICAL
            reasons.append(f"고점수 ({score}점)")
        elif days_left is not None and days_left <= self.config.critical_days:
            priority = Priority.CRITICAL
            reasons.append(f"긴급 만료 ({days_left}일)")

        # High 조건
        elif score >= self.config.high_score:
            priority = Priority.HIGH
            reasons.append(f"높은 점수 ({score}점)")
        elif days_left is not None and days_left <= self.config.high_days:
            priority = Priority.HIGH
            reasons.append(f"곧 만료 ({days_left}일)")

        # Medium 조건
        elif score >= self.config.medium_score:
            priority = Priority.MEDIUM
            reasons.append(f"중간 점수 ({score}점)")
        elif days_left is not None and days_left <= self.config.medium_days:
            priority = Priority.MEDIUM
            reasons.append(f"만료 예정 ({days_left}일)")

        # Low 조건
        elif score >= self.config.low_score:
            priority = Priority.LOW
            reasons.append(f"관심 점수 ({score}점)")

        # Batch 조건
        else:
            priority = Priority.BATCH
            reasons.append("배치 처리")

        return PrioritizedDomain(
            domain=domain,
            priority=priority,
            reasons=reasons
        )

    def should_send_now(self, prioritized: PrioritizedDomain) -> bool:
        """
        즉시 발송해야 하는지 확인

        Args:
            prioritized: PrioritizedDomain

        Returns:
            즉시 발송 여부
        """
        # 일일 한도 확인
        self._check_daily_reset()
        if self._sent_today >= self.config.max_daily_alerts:
            logger.warning("daily_alert_limit_reached", limit=self.config.max_daily_alerts)
            return False

        # Critical/High는 즉시 발송
        if prioritized.priority in (Priority.CRITICAL, Priority.HIGH):
            return True

        # Medium은 즉시 발송
        if prioritized.priority == Priority.MEDIUM:
            return True

        # Low/Batch는 배치 처리
        return False

    def add_to_batch(self, prioritized: PrioritizedDomain) -> None:
        """배치 큐에 추가"""
        self._batch_queue.append(prioritized)
        logger.debug(
            "added_to_batch",
            domain=prioritized.domain.full_name,
            queue_size=len(self._batch_queue)
        )

    def get_batch_ready(self) -> List[PrioritizedDomain]:
        """
        배치 발송 준비된 도메인 반환

        Returns:
            발송 준비된 도메인 리스트
        """
        if not self._batch_queue:
            return []

        # 배치 큐에서 꺼내기
        ready = self._batch_queue.copy()
        self._batch_queue.clear()

        # 우선순위 순 정렬
        ready.sort(key=lambda x: (x.priority, -(x.domain.total_score or 0)))

        return ready

    def schedule_repeat(self, prioritized: PrioritizedDomain) -> Optional[datetime]:
        """
        반복 알림 스케줄링

        Args:
            prioritized: PrioritizedDomain

        Returns:
            다음 알림 시간 (없으면 None)
        """
        domain_id = str(prioritized.domain.id)

        # Critical은 30분마다, High는 60분마다 반복
        if prioritized.priority == Priority.CRITICAL:
            interval = timedelta(minutes=self.config.critical_repeat_interval)
            max_repeats = 3
        elif prioritized.priority == Priority.HIGH:
            interval = timedelta(minutes=self.config.high_repeat_interval)
            max_repeats = 2
        else:
            return None

        # 최대 반복 횟수 확인
        if prioritized.repeat_count >= max_repeats:
            return None

        next_time = datetime.now() + interval
        self._repeat_schedule[domain_id] = next_time
        prioritized.repeat_count += 1
        prioritized.scheduled_time = next_time

        logger.info(
            "repeat_scheduled",
            domain=prioritized.domain.full_name,
            next_time=next_time.isoformat(),
            repeat_count=prioritized.repeat_count
        )

        return next_time

    def get_due_repeats(self) -> List[str]:
        """
        반복 알림 발송 시간이 된 도메인 ID 반환

        Returns:
            도메인 ID 리스트
        """
        now = datetime.now()
        due = []

        for domain_id, scheduled_time in list(self._repeat_schedule.items()):
            if scheduled_time <= now:
                due.append(domain_id)
                del self._repeat_schedule[domain_id]

        return due

    def mark_sent(self) -> None:
        """발송 카운트 증가"""
        self._sent_today += 1

    def _check_daily_reset(self) -> None:
        """일일 카운터 리셋 확인"""
        now = datetime.now()
        if now.date() > self._last_reset.date():
            self._sent_today = 0
            self._last_reset = now
            logger.info("daily_counter_reset")

    def get_stats(self) -> Dict[str, Any]:
        """통계 반환"""
        return {
            "sent_today": self._sent_today,
            "max_daily": self.config.max_daily_alerts,
            "batch_queue_size": len(self._batch_queue),
            "pending_repeats": len(self._repeat_schedule),
        }


class NotificationThrottler:
    """알림 스로틀링 (중복/스팸 방지)"""

    def __init__(self, cooldown_seconds: int = 3600):
        self.cooldown = cooldown_seconds  # 같은 도메인 재알림 쿨다운
        self._sent_domains: Dict[str, datetime] = {}

    def can_send(self, domain_name: str) -> bool:
        """
        해당 도메인에 대해 알림을 보낼 수 있는지 확인

        Args:
            domain_name: 도메인 이름

        Returns:
            발송 가능 여부
        """
        if domain_name not in self._sent_domains:
            return True

        last_sent = self._sent_domains[domain_name]
        elapsed = (datetime.now() - last_sent).total_seconds()

        return elapsed >= self.cooldown

    def mark_sent(self, domain_name: str) -> None:
        """발송 기록"""
        self._sent_domains[domain_name] = datetime.now()

    def cleanup_old(self) -> int:
        """
        오래된 기록 정리

        Returns:
            정리된 항목 수
        """
        now = datetime.now()
        old_keys = [
            k for k, v in self._sent_domains.items()
            if (now - v).total_seconds() > self.cooldown * 2
        ]

        for key in old_keys:
            del self._sent_domains[key]

        return len(old_keys)


class BatchNotificationScheduler:
    """배치 알림 스케줄러"""

    def __init__(
        self,
        interval_minutes: int = 60,
        max_per_batch: int = 10
    ):
        self.interval = interval_minutes
        self.max_per_batch = max_per_batch
        self._queue: List[PrioritizedDomain] = []
        self._last_batch: datetime = datetime.now()

    def add(self, prioritized: PrioritizedDomain) -> None:
        """배치에 추가"""
        self._queue.append(prioritized)

    def should_send_batch(self) -> bool:
        """배치 발송 시간인지 확인"""
        if not self._queue:
            return False

        elapsed = (datetime.now() - self._last_batch).total_seconds()
        return elapsed >= self.interval * 60

    def get_batch(self) -> List[PrioritizedDomain]:
        """
        배치 발송할 도메인 반환

        Returns:
            도메인 리스트
        """
        if not self._queue:
            return []

        # 우선순위 순 정렬 후 상위 N개
        self._queue.sort(key=lambda x: (x.priority, -(x.domain.total_score or 0)))
        batch = self._queue[:self.max_per_batch]
        self._queue = self._queue[self.max_per_batch:]

        self._last_batch = datetime.now()
        return batch

    @property
    def queue_size(self) -> int:
        """큐 크기"""
        return len(self._queue)


# 테스트
if __name__ == "__main__":
    from dataclasses import dataclass as dc

    @dc
    class MockDomain:
        id: int
        full_name: str
        total_score: int
        days_until_expiry: Optional[int]

    # 테스트 도메인
    domains = [
        MockDomain(1, "premium.com", 95, 1),    # Critical (고점수 + 긴급만료)
        MockDomain(2, "valuable.io", 85, 5),    # High (높은점수)
        MockDomain(3, "decent.net", 75, 10),    # Medium (중간점수)
        MockDomain(4, "normal.co", 65, 15),     # Low (관심점수)
        MockDomain(5, "basic.org", 55, 20),     # Batch (낮은점수)
    ]

    manager = NotificationPriorityManager()

    print("=== Priority Test ===\n")
    for domain in domains:
        result = manager.calculate_priority(domain)
        print(f"{domain.full_name}:")
        print(f"  Priority: {result.priority.name}")
        print(f"  Reasons: {result.reasons}")
        print(f"  Send Now: {manager.should_send_now(result)}")
        print()
