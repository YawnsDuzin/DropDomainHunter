"""
Domain Sniper - 차단 방지 모듈
User-Agent 로테이션, 적응형 딜레이, 프록시 관리 등 차단 방지 기능을 제공합니다.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
from datetime import datetime
import structlog

logger = structlog.get_logger()


# 다양한 User-Agent 목록 (최신 브라우저 기준)
USER_AGENTS = [
    # Chrome (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

    # Chrome (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

    # Chrome (Linux)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",

    # Firefox (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:119.0) Gecko/20100101 Firefox/119.0",

    # Firefox (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.1; rv:121.0) Gecko/20100101 Firefox/121.0",

    # Firefox (Linux)
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",

    # Safari (Mac)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",

    # Edge (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]

# Accept 헤더 목록
ACCEPT_HEADERS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
]

# Accept-Language 헤더 목록
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,ko;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en,en-US;q=0.9",
]


class UserAgentRotator:
    """User-Agent 로테이션 관리자"""

    def __init__(self, user_agents: Optional[List[str]] = None):
        self.user_agents = user_agents or USER_AGENTS
        self.current_index = 0
        self._last_used: Dict[str, float] = {}

    def get_random(self) -> str:
        """무작위 User-Agent 반환"""
        return random.choice(self.user_agents)

    def get_next(self) -> str:
        """순차적으로 다음 User-Agent 반환"""
        ua = self.user_agents[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.user_agents)
        return ua

    def get_with_cooldown(self, cooldown_seconds: float = 300) -> str:
        """
        쿨다운 적용하여 User-Agent 반환
        최근 사용한 UA는 피함
        """
        now = time.time()
        available = [
            ua for ua in self.user_agents
            if now - self._last_used.get(ua, 0) > cooldown_seconds
        ]

        if not available:
            available = self.user_agents

        ua = random.choice(available)
        self._last_used[ua] = now
        return ua


@dataclass
class AdaptiveDelay:
    """적응형 딜레이 관리자"""

    base_delay: float = 2.0  # 기본 딜레이 (초)
    min_delay: float = 1.5   # 최소 딜레이
    max_delay: float = 60.0  # 최대 딜레이
    current_delay: float = field(init=False)
    consecutive_errors: int = field(default=0, init=False)
    consecutive_successes: int = field(default=0, init=False)
    total_requests: int = field(default=0, init=False)

    def __post_init__(self):
        self.current_delay = self.base_delay

    async def wait(self) -> float:
        """
        적응형 딜레이 대기

        Returns:
            실제 대기 시간
        """
        # 랜덤 지터 추가 (0.5 ~ 2.0 배)
        jitter = random.uniform(0.5, 2.0)
        actual_delay = self.current_delay * jitter

        # 최소/최대 범위 내로 제한
        actual_delay = max(self.min_delay, min(self.max_delay, actual_delay))

        await asyncio.sleep(actual_delay)
        self.total_requests += 1

        return actual_delay

    def on_success(self) -> None:
        """요청 성공 시 호출"""
        self.consecutive_successes += 1
        self.consecutive_errors = 0

        # 10번 연속 성공 시 딜레이 감소
        if self.consecutive_successes >= 10:
            self.current_delay = max(self.min_delay, self.current_delay * 0.9)
            self.consecutive_successes = 0
            logger.debug("delay_decreased", new_delay=self.current_delay)

    def on_error(self, status_code: Optional[int] = None) -> None:
        """
        요청 실패 시 호출

        Args:
            status_code: HTTP 상태 코드
        """
        self.consecutive_errors += 1
        self.consecutive_successes = 0

        if status_code == 429:  # Too Many Requests
            # 3배 증가
            self.current_delay = min(self.max_delay, self.current_delay * 3)
            logger.warning("rate_limited", new_delay=self.current_delay)
        elif status_code == 403:  # Forbidden
            # 2배 증가
            self.current_delay = min(self.max_delay, self.current_delay * 2)
            logger.warning("forbidden_response", new_delay=self.current_delay)
        else:
            # 1.5배 증가
            self.current_delay = min(self.max_delay, self.current_delay * 1.5)
            logger.debug("delay_increased", new_delay=self.current_delay)

    def reset(self) -> None:
        """딜레이 초기화"""
        self.current_delay = self.base_delay
        self.consecutive_errors = 0
        self.consecutive_successes = 0


@dataclass
class ProxyRotator:
    """프록시 로테이션 관리자"""

    proxies: List[str] = field(default_factory=list)
    failed_proxies: Set[str] = field(default_factory=set, init=False)
    proxy_failures: Dict[str, int] = field(default_factory=dict, init=False)
    max_failures: int = 3  # 최대 실패 횟수

    def add_proxy(self, proxy: str) -> None:
        """프록시 추가"""
        if proxy not in self.proxies:
            self.proxies.append(proxy)
            logger.info("proxy_added", proxy=self._mask_proxy(proxy))

    def add_proxies(self, proxies: List[str]) -> None:
        """여러 프록시 추가"""
        for proxy in proxies:
            self.add_proxy(proxy)

    def get_proxy(self) -> Optional[Dict[str, str]]:
        """
        사용 가능한 프록시 반환

        Returns:
            httpx 형식의 프록시 딕셔너리 또는 None
        """
        if not self.proxies:
            return None

        # 실패하지 않은 프록시만 선택
        available = [p for p in self.proxies if p not in self.failed_proxies]

        if not available:
            # 모든 프록시가 실패한 경우 리셋
            self.failed_proxies.clear()
            self.proxy_failures.clear()
            available = self.proxies
            logger.warning("all_proxies_failed_resetting")

        proxy = random.choice(available)
        return {"http://": proxy, "https://": proxy}

    def mark_success(self, proxy: str) -> None:
        """프록시 성공 표시"""
        # 실패 카운트 리셋
        if proxy in self.proxy_failures:
            del self.proxy_failures[proxy]
        if proxy in self.failed_proxies:
            self.failed_proxies.discard(proxy)

    def mark_failed(self, proxy: str) -> None:
        """프록시 실패 표시"""
        self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1

        if self.proxy_failures[proxy] >= self.max_failures:
            self.failed_proxies.add(proxy)
            logger.warning("proxy_marked_failed", proxy=self._mask_proxy(proxy))

    def _mask_proxy(self, proxy: str) -> str:
        """프록시 주소 마스킹 (로깅용)"""
        if "@" in proxy:
            # 인증 정보가 있는 경우 마스킹
            parts = proxy.split("@")
            return f"***@{parts[-1]}"
        return proxy[:20] + "..." if len(proxy) > 20 else proxy

    @property
    def available_count(self) -> int:
        """사용 가능한 프록시 수"""
        return len(self.proxies) - len(self.failed_proxies)


class HumanBehavior:
    """사람처럼 행동하는 패턴 시뮬레이션"""

    def __init__(self):
        self.request_count = 0
        self.session_start = time.time()
        self.last_break = time.time()

    @staticmethod
    async def random_pause() -> float:
        """
        사람처럼 불규칙한 대기

        Returns:
            대기 시간
        """
        # 10% 확률로 긴 휴식
        if random.random() < 0.1:
            delay = random.uniform(30, 60)
            logger.debug("taking_long_pause", seconds=delay)
        # 20% 확률로 중간 휴식
        elif random.random() < 0.2:
            delay = random.uniform(10, 20)
        # 일반 대기
        else:
            delay = random.uniform(2, 8)

        await asyncio.sleep(delay)
        return delay

    def should_take_break(self) -> bool:
        """
        휴식이 필요한지 확인

        Returns:
            휴식 필요 여부
        """
        self.request_count += 1

        # 20~30개 요청마다 휴식
        break_threshold = random.randint(20, 30)
        if self.request_count >= break_threshold:
            self.request_count = 0
            return True

        # 또는 30분마다 휴식
        if time.time() - self.last_break > 1800:  # 30분
            return True

        return False

    async def take_break(self) -> float:
        """
        긴 휴식 (5~10분)

        Returns:
            휴식 시간
        """
        delay = random.uniform(300, 600)  # 5~10분
        logger.info("taking_break", minutes=delay/60)
        self.last_break = time.time()
        await asyncio.sleep(delay)
        return delay

    def get_random_headers(self, base_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        브라우저처럼 보이는 헤더 생성

        Args:
            base_headers: 기본 헤더 (있으면 병합)

        Returns:
            HTTP 헤더 딕셔너리
        """
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": random.choice(ACCEPT_HEADERS),
            "Accept-Language": random.choice(ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "DNT": "1",
            "Cache-Control": "max-age=0",
        }

        if base_headers:
            headers.update(base_headers)

        return headers


class CrawlTimeWindow:
    """크롤링 시간대 관리"""

    # 크롤링 권장 시간대 (서버 부하가 낮은 시간)
    DEFAULT_WINDOWS = [
        (6, 8),    # 새벽 6-8시
        (12, 14),  # 점심 12-14시
        (20, 22),  # 저녁 20-22시
    ]

    def __init__(self, windows: Optional[List[tuple]] = None):
        self.windows = windows or self.DEFAULT_WINDOWS

    def is_optimal_time(self) -> bool:
        """현재가 크롤링에 적합한 시간인지 확인"""
        hour = datetime.now().hour
        for start, end in self.windows:
            if start <= hour < end:
                return True
        return False

    def next_optimal_time(self) -> datetime:
        """다음 최적 크롤링 시간 반환"""
        now = datetime.now()
        hour = now.hour

        for start, end in sorted(self.windows):
            if hour < start:
                return now.replace(hour=start, minute=0, second=0, microsecond=0)

        # 다음 날 첫 번째 시간대
        next_day = now.replace(hour=self.windows[0][0], minute=0, second=0, microsecond=0)
        from datetime import timedelta
        return next_day + timedelta(days=1)


class AntiBlockingManager:
    """차단 방지 통합 관리자"""

    def __init__(
        self,
        use_proxy: bool = False,
        proxy_list: Optional[List[str]] = None,
        base_delay: float = 2.0
    ):
        self.ua_rotator = UserAgentRotator()
        self.delay = AdaptiveDelay(base_delay=base_delay)
        self.proxy_rotator = ProxyRotator()
        self.human_behavior = HumanBehavior()
        self.time_window = CrawlTimeWindow()
        self.use_proxy = use_proxy

        if proxy_list:
            self.proxy_rotator.add_proxies(proxy_list)
            self.use_proxy = True

    def get_request_config(self) -> Dict:
        """
        요청에 사용할 설정 반환

        Returns:
            headers, proxy 등 설정 딕셔너리
        """
        config = {
            "headers": self.human_behavior.get_random_headers(),
            "proxy": None,
        }

        if self.use_proxy:
            config["proxy"] = self.proxy_rotator.get_proxy()

        return config

    async def wait_before_request(self) -> float:
        """요청 전 대기"""
        # 휴식이 필요한지 확인
        if self.human_behavior.should_take_break():
            await self.human_behavior.take_break()

        return await self.delay.wait()

    def on_request_success(self, proxy_used: Optional[str] = None) -> None:
        """요청 성공 처리"""
        self.delay.on_success()
        if proxy_used:
            self.proxy_rotator.mark_success(proxy_used)

    def on_request_error(
        self,
        status_code: Optional[int] = None,
        proxy_used: Optional[str] = None
    ) -> None:
        """요청 실패 처리"""
        self.delay.on_error(status_code)
        if proxy_used:
            self.proxy_rotator.mark_failed(proxy_used)

    def get_stats(self) -> Dict:
        """통계 반환"""
        return {
            "total_requests": self.delay.total_requests,
            "current_delay": self.delay.current_delay,
            "consecutive_errors": self.delay.consecutive_errors,
            "available_proxies": self.proxy_rotator.available_count if self.use_proxy else 0,
            "is_optimal_time": self.time_window.is_optimal_time(),
        }


# 테스트
if __name__ == "__main__":
    async def test():
        print("=== Anti-Blocking Module Test ===\n")

        # User-Agent 테스트
        print("1. User-Agent Rotation:")
        ua_rotator = UserAgentRotator()
        for i in range(3):
            print(f"   {i+1}. {ua_rotator.get_random()[:60]}...")

        # Adaptive Delay 테스트
        print("\n2. Adaptive Delay:")
        delay = AdaptiveDelay(base_delay=1.0)
        print(f"   Initial delay: {delay.current_delay}s")
        delay.on_error(429)
        print(f"   After 429 error: {delay.current_delay}s")
        delay.on_success()
        print(f"   After success: {delay.current_delay}s")

        # Human Behavior 테스트
        print("\n3. Human Behavior Headers:")
        hb = HumanBehavior()
        headers = hb.get_random_headers()
        for key in ["User-Agent", "Accept-Language", "Sec-Fetch-Mode"]:
            print(f"   {key}: {headers.get(key, 'N/A')[:50]}...")

        # 통합 관리자 테스트
        print("\n4. Anti-Blocking Manager:")
        manager = AntiBlockingManager(base_delay=0.5)
        config = manager.get_request_config()
        print(f"   Headers count: {len(config['headers'])}")
        print(f"   Stats: {manager.get_stats()}")

    asyncio.run(test())
