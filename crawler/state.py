"""
Domain Sniper - 크롤링 상태 관리
자동/수동 크롤링 간 충돌 방지를 위한 전역 상태 관리
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
import structlog

logger = structlog.get_logger()


class CrawlType(str, Enum):
    """크롤링 유형"""
    FULL = "full"
    WEEK = "week"
    DAY = "day"
    MANUAL_FULL = "manual_full"
    MANUAL_WEEK = "manual_week"
    MANUAL_DAY = "manual_day"


@dataclass
class CrawlStatus:
    """크롤링 상태"""
    is_running: bool = False
    crawl_type: Optional[str] = None
    started_at: Optional[datetime] = None
    is_manual: bool = False
    progress: int = 0  # 0-100
    message: str = ""


class CrawlStateManager:
    """
    크롤링 상태 관리자 (싱글톤)

    자동 스케줄 크롤링과 수동 크롤링 간의 충돌을 방지합니다.
    - 크롤링이 진행 중이면 새로운 크롤링 시작을 차단
    - 상태 정보를 웹 UI에서 조회 가능
    """

    _instance: Optional["CrawlStateManager"] = None
    _lock: asyncio.Lock = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._status = CrawlStatus()
        self._lock = asyncio.Lock()

    @property
    def status(self) -> CrawlStatus:
        """현재 크롤링 상태 조회"""
        return self._status

    @property
    def is_running(self) -> bool:
        """크롤링 진행 중 여부"""
        return self._status.is_running

    async def try_start(
        self,
        crawl_type: str,
        is_manual: bool = False
    ) -> bool:
        """
        크롤링 시작 시도

        Args:
            crawl_type: 크롤링 유형 (full, week, day)
            is_manual: 수동 크롤링 여부

        Returns:
            성공 여부 (이미 진행 중이면 False)
        """
        async with self._lock:
            if self._status.is_running:
                logger.warning(
                    "crawl_start_blocked",
                    requested_type=crawl_type,
                    current_type=self._status.crawl_type,
                    is_manual=is_manual
                )
                return False

            self._status = CrawlStatus(
                is_running=True,
                crawl_type=crawl_type,
                started_at=datetime.now(),
                is_manual=is_manual,
                progress=0,
                message=f"{'수동' if is_manual else '자동'} {crawl_type} 크롤링 시작"
            )

            logger.info(
                "crawl_started",
                type=crawl_type,
                is_manual=is_manual
            )
            return True

    async def update_progress(self, progress: int, message: str = "") -> None:
        """
        크롤링 진행률 업데이트

        Args:
            progress: 진행률 (0-100)
            message: 상태 메시지
        """
        async with self._lock:
            self._status.progress = min(100, max(0, progress))
            if message:
                self._status.message = message

    async def finish(self, success: bool = True, message: str = "") -> None:
        """
        크롤링 완료 처리

        Args:
            success: 성공 여부
            message: 완료 메시지
        """
        async with self._lock:
            crawl_type = self._status.crawl_type
            duration = None
            if self._status.started_at:
                duration = (datetime.now() - self._status.started_at).total_seconds()

            logger.info(
                "crawl_finished",
                type=crawl_type,
                success=success,
                duration=duration,
                message=message
            )

            self._status = CrawlStatus()

    def to_dict(self) -> dict:
        """상태를 딕셔너리로 변환 (API 응답용)"""
        return {
            "is_running": self._status.is_running,
            "crawl_type": self._status.crawl_type,
            "started_at": self._status.started_at.isoformat() if self._status.started_at else None,
            "is_manual": self._status.is_manual,
            "progress": self._status.progress,
            "message": self._status.message,
            "elapsed_seconds": (
                (datetime.now() - self._status.started_at).total_seconds()
                if self._status.started_at else 0
            )
        }


# 전역 인스턴스
crawl_state = CrawlStateManager()
