"""
Domain Sniper - 알림 관리자
Telegram과 Discord 알림을 통합 관리
"""

import asyncio
from typing import List, Dict, Any
from datetime import datetime
import structlog

from .telegram import TelegramNotifier
from .discord import DiscordNotifier
from database.models import Domain, Database

logger = structlog.get_logger()


class NotificationManager:
    """통합 알림 관리자"""

    def __init__(self, db: Database):
        """
        초기화

        Args:
            db: 데이터베이스 인스턴스
        """
        self.db = db
        self.telegram = TelegramNotifier()
        self.discord = DiscordNotifier()

        logger.info(
            "notification_manager_initialized",
            telegram_enabled=self.telegram.enabled,
            discord_enabled=self.discord.enabled
        )

    async def notify_domain(self, domain: Domain, mark_notified: bool = True) -> Dict[str, bool]:
        """
        도메인 알림 발송 (모든 채널)

        Args:
            domain: Domain 객체
            mark_notified: DB에 알림 완료 표시 여부

        Returns:
            채널별 성공 여부
        """
        results = {"telegram": False, "discord": False}

        # 병렬로 알림 발송
        tasks = []
        if self.telegram.enabled:
            tasks.append(("telegram", self.telegram.send_domain_alert(domain)))
        if self.discord.enabled:
            tasks.append(("discord", self.discord.send_domain_alert(domain)))

        if tasks:
            for channel, task in tasks:
                try:
                    results[channel] = await task
                except Exception as e:
                    logger.error(f"{channel}_notify_error", domain=domain.full_name, error=str(e))

        # 알림 성공 시 DB 업데이트
        if mark_notified and any(results.values()):
            await self.db.mark_domain_notified(domain.id)

        logger.info(
            "domain_notified",
            domain=domain.full_name,
            telegram=results["telegram"],
            discord=results["discord"]
        )

        return results

    async def notify_high_score_domains(self, min_score: int = None) -> int:
        """
        고점수 도메인 일괄 알림

        Args:
            min_score: 최소 점수 (None이면 설정값 사용)

        Returns:
            알림 발송된 도메인 수
        """
        from config import settings

        if min_score is None:
            min_score = settings.min_score_alert

        # 미발송 고점수 도메인 조회
        domains = await self.db.get_unnotified_high_score_domains(min_score)

        if not domains:
            logger.info("no_high_score_domains_to_notify")
            return 0

        notified_count = 0
        for domain in domains:
            results = await self.notify_domain(domain)
            if any(results.values()):
                notified_count += 1

            # 알림 간 딜레이 (스팸 방지)
            await asyncio.sleep(1)

        logger.info("high_score_notification_completed", count=notified_count)
        return notified_count

    async def send_daily_report(self) -> Dict[str, bool]:
        """
        일일 리포트 발송

        Returns:
            채널별 성공 여부
        """
        results = {"telegram": False, "discord": False}

        # 통계 조회
        stats = await self.db.get_domain_stats()

        # 오늘의 TOP 도메인
        top_domains = await self.db.get_domains(
            limit=10,
            min_score=50,
            order_by="total_score DESC"
        )

        # 알림 발송
        if self.telegram.enabled:
            try:
                results["telegram"] = await self.telegram.send_daily_report(stats, top_domains)
            except Exception as e:
                logger.error("telegram_daily_report_error", error=str(e))

        if self.discord.enabled:
            try:
                results["discord"] = await self.discord.send_daily_report(stats, top_domains)
            except Exception as e:
                logger.error("discord_daily_report_error", error=str(e))

        logger.info(
            "daily_report_sent",
            telegram=results["telegram"],
            discord=results["discord"]
        )

        return results

    async def send_heartbeat(self) -> Dict[str, bool]:
        """
        하트비트 발송

        Returns:
            채널별 성공 여부
        """
        results = {"telegram": False, "discord": False}

        if self.telegram.enabled:
            try:
                results["telegram"] = await self.telegram.send_heartbeat()
            except Exception as e:
                logger.error("telegram_heartbeat_error", error=str(e))

        if self.discord.enabled:
            try:
                results["discord"] = await self.discord.send_heartbeat()
            except Exception as e:
                logger.error("discord_heartbeat_error", error=str(e))

        return results

    async def send_error_alert(self, error_type: str, error_message: str) -> Dict[str, bool]:
        """
        에러 알림 발송

        Args:
            error_type: 에러 유형
            error_message: 에러 메시지

        Returns:
            채널별 성공 여부
        """
        results = {"telegram": False, "discord": False}

        if self.telegram.enabled:
            try:
                results["telegram"] = await self.telegram.send_error_alert(error_type, error_message)
            except Exception as e:
                logger.error("telegram_error_alert_failed", error=str(e))

        if self.discord.enabled:
            try:
                results["discord"] = await self.discord.send_error_alert(error_type, error_message)
            except Exception as e:
                logger.error("discord_error_alert_failed", error=str(e))

        return results

    async def send_crawl_summary(
        self,
        source: str,
        total_found: int,
        new_domains: int,
        high_score_count: int,
        duration: float
    ) -> Dict[str, bool]:
        """
        크롤링 완료 요약 발송

        Args:
            source: 크롤링 소스
            total_found: 발견된 총 도메인 수
            new_domains: 새로 추가된 도메인 수
            high_score_count: 고점수 도메인 수
            duration: 소요 시간 (초)

        Returns:
            채널별 성공 여부
        """
        now = datetime.now()

        message = f"""
📥 크롤링 완료 알림

🔍 소스: {source}
🕐 완료: {now.strftime('%H:%M:%S')}
⏱️ 소요: {duration:.1f}초

━━━ 결과 ━━━
• 발견: {total_found:,}개
• 신규: {new_domains:,}개
• 고점수(70+): {high_score_count:,}개
"""

        results = {"telegram": False, "discord": False}

        if self.telegram.enabled:
            try:
                results["telegram"] = await self.telegram.send_message(message)
            except Exception as e:
                logger.error("telegram_crawl_summary_error", error=str(e))

        if self.discord.enabled:
            try:
                results["discord"] = await self.discord.send_message(message)
            except Exception as e:
                logger.error("discord_crawl_summary_error", error=str(e))

        return results
