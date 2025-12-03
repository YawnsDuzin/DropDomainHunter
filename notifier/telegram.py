"""
Domain Sniper - Telegram 알림
Telegram Bot API를 통한 알림 발송
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
import structlog

from config import settings
from database.models import Domain

logger = structlog.get_logger()


class TelegramNotifier:
    """Telegram 봇 알림 관리자"""

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.enabled = bool(settings.telegram_bot_token and settings.telegram_chat_id)

        if self.enabled:
            self.bot = Bot(token=settings.telegram_bot_token)
            logger.info("telegram_notifier_initialized")
        else:
            logger.warning("telegram_notifier_disabled", reason="Missing token or chat_id")

    async def send_domain_alert(self, domain: Domain) -> bool:
        """
        고가치 도메인 알림 발송

        Args:
            domain: Domain 객체

        Returns:
            성공 여부
        """
        if not self.enabled:
            return False

        # 이모지 결정
        if domain.total_score >= 90:
            emoji = "🔥🔥🔥"
        elif domain.total_score >= 80:
            emoji = "🔥🔥"
        elif domain.total_score >= 70:
            emoji = "🔥"
        else:
            emoji = "✨"

        # 만료 정보
        if domain.days_until_expiry is not None:
            if domain.days_until_expiry <= 0:
                expiry_text = "⚠️ 오늘 만료!"
            elif domain.days_until_expiry == 1:
                expiry_text = "⏰ 내일 만료"
            else:
                expiry_text = f"⏰ {domain.days_until_expiry}일 후 만료"
        else:
            expiry_text = "⏰ 만료일 미상"

        # 메시지 생성
        message = f"""
{emoji} <b>고가치 도메인 발견!</b>

📌 <code>{domain.full_name}</code>
{expiry_text}
📊 점수: <b>{domain.total_score}/100</b>

━━━ 점수 상세 ━━━
• 길이: {domain.length}자 ({domain.length_score}점)
• 키워드: {domain.keyword_score}점
• 패턴: {domain.pattern_score}점

💰 예상가: <b>{domain.estimated_value_str}</b>
📍 소스: {domain.source or 'N/A'}
"""

        # 인라인 키보드 생성
        keyboard = self._create_domain_keyboard(domain)

        try:
            await self.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=message.strip(),
                parse_mode="HTML",
                reply_markup=keyboard
            )
            logger.info("telegram_alert_sent", domain=domain.full_name)
            return True

        except TelegramError as e:
            logger.error("telegram_send_error", domain=domain.full_name, error=str(e))
            return False

    async def send_daily_report(self, stats: Dict[str, Any], top_domains: List[Domain]) -> bool:
        """
        일일 요약 리포트 발송

        Args:
            stats: 통계 정보
            top_domains: 상위 도메인 리스트

        Returns:
            성공 여부
        """
        if not self.enabled:
            return False

        now = datetime.now()
        date_str = now.strftime("%Y년 %m월 %d일")

        # 상위 도메인 목록
        top_list = ""
        for i, d in enumerate(top_domains[:5], 1):
            expiry = f"{d.days_until_expiry}일" if d.days_until_expiry else "N/A"
            top_list += f"{i}. <code>{d.full_name}</code> - {d.total_score}점 (만료: {expiry})\n"

        message = f"""
📊 <b>일일 도메인 리포트</b>
📅 {date_str}

━━━ 통계 요약 ━━━
• 총 도메인: {stats.get('total_count', 0):,}개
• 오늘 발견: {stats.get('today_count', 0):,}개
• 고점수(80+): {stats.get('score_distribution', {}).get('high', 0):,}개
• 중점수(60-79): {stats.get('score_distribution', {}).get('medium', 0):,}개

━━━ 오늘의 TOP 5 ━━━
{top_list if top_list else '• 아직 데이터가 없습니다.'}

━━━━━━━━━━━━━━━━━━
🤖 Domain Sniper 자동 리포트
"""

        try:
            await self.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=message.strip(),
                parse_mode="HTML"
            )
            logger.info("telegram_daily_report_sent")
            return True

        except TelegramError as e:
            logger.error("telegram_daily_report_error", error=str(e))
            return False

    async def send_heartbeat(self) -> bool:
        """
        하트비트 메시지 발송 (시스템 정상 작동 확인)

        Returns:
            성공 여부
        """
        if not self.enabled:
            return False

        now = datetime.now()
        message = f"""
💓 <b>시스템 하트비트</b>
🕐 {now.strftime("%Y-%m-%d %H:%M:%S")}

Domain Sniper가 정상 작동 중입니다.
"""

        try:
            await self.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=message.strip(),
                parse_mode="HTML"
            )
            logger.debug("telegram_heartbeat_sent")
            return True

        except TelegramError as e:
            logger.error("telegram_heartbeat_error", error=str(e))
            return False

    async def send_error_alert(self, error_type: str, error_message: str) -> bool:
        """
        에러 알림 발송

        Args:
            error_type: 에러 유형
            error_message: 에러 메시지

        Returns:
            성공 여부
        """
        if not self.enabled:
            return False

        now = datetime.now()
        message = f"""
⚠️ <b>시스템 에러 알림</b>
🕐 {now.strftime("%Y-%m-%d %H:%M:%S")}

❌ 에러 유형: <code>{error_type}</code>
📝 메시지: {error_message[:500]}

즉시 확인이 필요합니다.
"""

        try:
            await self.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=message.strip(),
                parse_mode="HTML"
            )
            logger.info("telegram_error_alert_sent", error_type=error_type)
            return True

        except TelegramError as e:
            logger.error("telegram_error_alert_failed", error=str(e))
            return False

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        일반 메시지 발송

        Args:
            message: 메시지 내용
            parse_mode: 파싱 모드

        Returns:
            성공 여부
        """
        if not self.enabled:
            return False

        try:
            await self.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True

        except TelegramError as e:
            logger.error("telegram_send_error", error=str(e))
            return False

    def _create_domain_keyboard(self, domain: Domain) -> InlineKeyboardMarkup:
        """도메인 알림용 인라인 키보드 생성"""
        buttons = [
            [
                InlineKeyboardButton(
                    "🔍 상세보기",
                    callback_data=f"detail:{domain.id}"
                ),
                InlineKeyboardButton(
                    "⭐ 관심등록",
                    callback_data=f"watch:{domain.id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔗 GoDaddy",
                    url=f"https://www.godaddy.com/domainsearch/find?domainToCheck={domain.full_name}"
                ),
                InlineKeyboardButton(
                    "🔗 Namecheap",
                    url=f"https://www.namecheap.com/domains/registration/results/?domain={domain.full_name}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🚫 무시",
                    callback_data=f"ignore:{domain.id}"
                ),
            ]
        ]

        return InlineKeyboardMarkup(buttons)


# 테스트
if __name__ == "__main__":
    async def test():
        notifier = TelegramNotifier()

        if notifier.enabled:
            # 테스트 도메인
            from datetime import date, timedelta
            test_domain = Domain(
                id=1,
                name="startup",
                tld="io",
                full_name="startup.io",
                length=7,
                expiry_date=date.today() + timedelta(days=2),
                length_score=85,
                keyword_score=95,
                pattern_score=80,
                total_score=87,
                estimated_value_min=1000,
                estimated_value_max=5000,
                source="test"
            )

            success = await notifier.send_domain_alert(test_domain)
            print(f"Alert sent: {success}")
        else:
            print("Telegram notifier is disabled. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")

    asyncio.run(test())
