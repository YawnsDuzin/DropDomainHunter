"""
Domain Sniper - Discord 알림
Discord Webhook을 통한 알림 발송
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

import aiohttp
import structlog

from config import settings
from database.models import Domain

logger = structlog.get_logger()


class DiscordNotifier:
    """Discord Webhook 알림 관리자"""

    def __init__(self):
        self.webhook_url = settings.discord_webhook_url
        self.enabled = bool(self.webhook_url)

        if self.enabled:
            logger.info("discord_notifier_initialized")
        else:
            logger.warning("discord_notifier_disabled", reason="Missing webhook URL")

    async def _send_webhook(self, payload: Dict[str, Any]) -> bool:
        """
        Webhook 요청 발송

        Args:
            payload: 요청 데이터

        Returns:
            성공 여부
        """
        if not self.enabled:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status in (200, 204):
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(
                            "discord_webhook_error",
                            status=response.status,
                            error=error_text
                        )
                        return False

        except Exception as e:
            logger.error("discord_send_error", error=str(e))
            return False

    async def send_domain_alert(self, domain: Domain) -> bool:
        """
        고가치 도메인 알림 발송

        Args:
            domain: Domain 객체

        Returns:
            성공 여부
        """
        # 색상 결정 (점수 기반)
        if domain.total_score >= 90:
            color = 0xFF0000  # 빨강
        elif domain.total_score >= 80:
            color = 0xFF6600  # 주황
        elif domain.total_score >= 70:
            color = 0xFFCC00  # 노랑
        else:
            color = 0x00CC00  # 초록

        # 만료 정보
        if domain.days_until_expiry is not None:
            if domain.days_until_expiry <= 0:
                expiry_text = "오늘 만료!"
            elif domain.days_until_expiry == 1:
                expiry_text = "내일 만료"
            else:
                expiry_text = f"{domain.days_until_expiry}일 후 만료"
        else:
            expiry_text = "만료일 미상"

        # Embed 생성
        embed = {
            "title": f"🔥 고가치 도메인 발견: {domain.full_name}",
            "color": color,
            "fields": [
                {
                    "name": "📊 총점",
                    "value": f"**{domain.total_score}/100**",
                    "inline": True
                },
                {
                    "name": "⏰ 만료",
                    "value": expiry_text,
                    "inline": True
                },
                {
                    "name": "📏 길이",
                    "value": f"{domain.length}자 ({domain.length_score}점)",
                    "inline": True
                },
                {
                    "name": "🔤 키워드",
                    "value": f"{domain.keyword_score}점",
                    "inline": True
                },
                {
                    "name": "📐 패턴",
                    "value": f"{domain.pattern_score}점",
                    "inline": True
                },
                {
                    "name": "💰 예상가",
                    "value": domain.estimated_value_str,
                    "inline": True
                },
            ],
            "footer": {
                "text": f"소스: {domain.source or 'N/A'} | {settings.program_name}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        payload = {
            "embeds": [embed],
            "components": [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 2,  # Button
                            "style": 5,  # Link
                            "label": "GoDaddy에서 확인",
                            "url": f"https://www.godaddy.com/domainsearch/find?domainToCheck={domain.full_name}"
                        },
                        {
                            "type": 2,
                            "style": 5,
                            "label": "Namecheap에서 확인",
                            "url": f"https://www.namecheap.com/domains/registration/results/?domain={domain.full_name}"
                        }
                    ]
                }
            ]
        }

        success = await self._send_webhook(payload)
        if success:
            logger.info("discord_alert_sent", domain=domain.full_name)
        return success

    async def send_daily_report(self, stats: Dict[str, Any], top_domains: List[Domain]) -> bool:
        """
        일일 요약 리포트 발송

        Args:
            stats: 통계 정보
            top_domains: 상위 도메인 리스트

        Returns:
            성공 여부
        """
        now = datetime.now()
        date_str = now.strftime("%Y년 %m월 %d일")

        # 상위 도메인 필드
        top_list = ""
        for i, d in enumerate(top_domains[:5], 1):
            expiry = f"{d.days_until_expiry}일" if d.days_until_expiry else "N/A"
            top_list += f"**{i}. {d.full_name}** - {d.total_score}점 (만료: {expiry})\n"

        embed = {
            "title": f"📊 일일 도메인 리포트 - {date_str}",
            "color": 0x5865F2,  # Discord 블루
            "fields": [
                {
                    "name": "📈 통계 요약",
                    "value": (
                        f"• 총 도메인: **{stats.get('total_count', 0):,}**개\n"
                        f"• 오늘 발견: **{stats.get('today_count', 0):,}**개\n"
                        f"• 고점수(80+): **{stats.get('score_distribution', {}).get('high', 0):,}**개"
                    ),
                    "inline": False
                },
                {
                    "name": "🏆 오늘의 TOP 5",
                    "value": top_list if top_list else "아직 데이터가 없습니다.",
                    "inline": False
                }
            ],
            "footer": {
                "text": f"{settings.program_name} 자동 리포트"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        payload = {"embeds": [embed]}

        success = await self._send_webhook(payload)
        if success:
            logger.info("discord_daily_report_sent")
        return success

    async def send_heartbeat(self) -> bool:
        """
        하트비트 메시지 발송

        Returns:
            성공 여부
        """
        now = datetime.now()

        embed = {
            "title": "💓 시스템 하트비트",
            "description": f"{settings.program_name}가 정상 작동 중입니다.",
            "color": 0x00FF00,  # 초록
            "footer": {
                "text": f"확인 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }

        payload = {"embeds": [embed]}

        success = await self._send_webhook(payload)
        if success:
            logger.debug("discord_heartbeat_sent")
        return success

    async def send_error_alert(self, error_type: str, error_message: str) -> bool:
        """
        에러 알림 발송

        Args:
            error_type: 에러 유형
            error_message: 에러 메시지

        Returns:
            성공 여부
        """
        now = datetime.now()

        embed = {
            "title": "⚠️ 시스템 에러 알림",
            "color": 0xFF0000,  # 빨강
            "fields": [
                {
                    "name": "에러 유형",
                    "value": f"`{error_type}`",
                    "inline": True
                },
                {
                    "name": "발생 시간",
                    "value": now.strftime('%Y-%m-%d %H:%M:%S'),
                    "inline": True
                },
                {
                    "name": "메시지",
                    "value": f"```{error_message[:1000]}```",
                    "inline": False
                }
            ],
            "footer": {
                "text": "즉시 확인이 필요합니다."
            }
        }

        payload = {"embeds": [embed]}

        success = await self._send_webhook(payload)
        if success:
            logger.info("discord_error_alert_sent", error_type=error_type)
        return success

    async def send_message(self, content: str) -> bool:
        """
        일반 메시지 발송

        Args:
            content: 메시지 내용

        Returns:
            성공 여부
        """
        payload = {"content": content}
        return await self._send_webhook(payload)


# 테스트
if __name__ == "__main__":
    async def test():
        notifier = DiscordNotifier()

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
            print("Discord notifier is disabled. Set DISCORD_WEBHOOK_URL.")

    asyncio.run(test())
