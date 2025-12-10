"""
Domain Sniper - Telegram Bot 핸들러
콜백 쿼리, 명령어 등 Telegram Bot의 양방향 통신을 처리합니다.
"""

import asyncio
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.error import TelegramError
import structlog

from config import settings

logger = structlog.get_logger()


class TelegramBotHandler:
    """
    Telegram Bot 양방향 통신 핸들러
    콜백 쿼리와 명령어를 처리합니다.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        db_callback: Optional[Callable] = None
    ):
        """
        Args:
            token: Telegram Bot 토큰
            db_callback: 데이터베이스 작업 콜백 함수
        """
        self.token = token or settings.telegram_bot_token
        self.db_callback = db_callback
        self.app: Optional[Application] = None
        self.running = False

        if not self.token:
            logger.warning("telegram_bot_handler_disabled", reason="no_token")

    async def start(self) -> bool:
        """
        봇 핸들러 시작

        Returns:
            성공 여부
        """
        if not self.token:
            return False

        try:
            # Application 빌드
            self.app = Application.builder().token(self.token).build()

            # 핸들러 등록
            self._register_handlers()

            # 폴링 시작 (비동기)
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling(drop_pending_updates=True)

            self.running = True
            logger.info("telegram_bot_handler_started")
            return True

        except Exception as e:
            logger.error("telegram_bot_handler_start_error", error=str(e))
            return False

    async def stop(self) -> None:
        """봇 핸들러 중지"""
        if self.app and self.running:
            try:
                await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
                self.running = False
                logger.info("telegram_bot_handler_stopped")
            except Exception as e:
                logger.error("telegram_bot_handler_stop_error", error=str(e))

    def _register_handlers(self) -> None:
        """핸들러 등록"""
        # 명령어 핸들러
        self.app.add_handler(CommandHandler("start", self._cmd_start))
        self.app.add_handler(CommandHandler("help", self._cmd_help))
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("top", self._cmd_top))
        self.app.add_handler(CommandHandler("watchlist", self._cmd_watchlist))
        self.app.add_handler(CommandHandler("search", self._cmd_search))

        # 콜백 쿼리 핸들러
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))

        logger.debug("telegram_handlers_registered")

    # ===== 명령어 핸들러 =====

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """시작 명령어"""
        welcome_msg = f"""
👋 <b>안녕하세요! {settings.program_name}입니다.</b>

저는 고가치 만료 도메인을 자동으로 찾아 알려드리는 봇입니다.

📌 <b>주요 명령어</b>
/status - 시스템 상태 확인
/top - 오늘의 TOP 도메인
/watchlist - 관심 목록 보기
/search [키워드] - 도메인 검색
/help - 도움말

🔔 고가치 도메인 발견 시 자동으로 알림을 보내드립니다!
"""
        await update.message.reply_text(welcome_msg, parse_mode="HTML")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """도움말 명령어"""
        help_msg = """
📖 <b>명령어 안내</b>

<b>기본 명령어</b>
/start - 봇 시작
/help - 이 도움말
/status - 시스템 상태

<b>도메인 관련</b>
/top - 오늘의 TOP 10 도메인
/watchlist - 내 관심 목록
/search [키워드] - 키워드로 검색

<b>버튼 기능</b>
• 🔍 상세보기 - 도메인 상세 정보
• ⭐ 관심등록 - 관심 목록에 추가
• 🚫 무시 - 해당 도메인 무시

<b>점수 기준</b>
🔥🔥🔥 90점+ : 프리미엄 도메인
🔥🔥 80점+ : 고가치 도메인
🔥 70점+ : 관심 도메인
"""
        await update.message.reply_text(help_msg, parse_mode="HTML")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """시스템 상태 명령어"""
        stats = await self._get_system_stats()

        status_msg = f"""
📊 <b>시스템 상태</b>
🕐 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

━━━ 데이터베이스 ━━━
• 총 도메인: {stats.get('total_domains', 0):,}개
• 오늘 발견: {stats.get('today_domains', 0):,}개
• 관심 목록: {stats.get('watchlist_count', 0):,}개

━━━ 크롤링 ━━━
• 마지막 크롤링: {stats.get('last_crawl', 'N/A')}
• 다음 크롤링: {stats.get('next_crawl', 'N/A')}

━━━ 시스템 ━━━
• 상태: {'🟢 정상' if stats.get('healthy', True) else '🔴 오류'}
• 가동 시간: {stats.get('uptime', 'N/A')}
"""
        await update.message.reply_text(status_msg, parse_mode="HTML")

    async def _cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """TOP 도메인 명령어"""
        domains = await self._get_top_domains(limit=10)

        if not domains:
            await update.message.reply_text("📭 아직 수집된 도메인이 없습니다.")
            return

        msg = "🏆 <b>오늘의 TOP 도메인</b>\n\n"

        for i, d in enumerate(domains, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            days = f"{d.get('days_until_expiry', '?')}일" if d.get('days_until_expiry') else "N/A"

            msg += f"{emoji} <code>{d['full_name']}</code>\n"
            msg += f"   점수: {d.get('total_score', 0)}점 | 만료: {days}\n\n"

        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """관심 목록 명령어"""
        items = await self._get_watchlist()

        if not items:
            await update.message.reply_text(
                "📭 관심 목록이 비어있습니다.\n\n도메인 알림의 '⭐ 관심등록' 버튼을 눌러 추가하세요."
            )
            return

        msg = "⭐ <b>내 관심 목록</b>\n\n"

        for i, item in enumerate(items[:20], 1):
            msg += f"{i}. <code>{item.get('domain_name', 'N/A')}</code>\n"
            if item.get('note'):
                msg += f"   📝 {item['note']}\n"
            msg += "\n"

        if len(items) > 20:
            msg += f"\n... 외 {len(items) - 20}개"

        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """도메인 검색 명령어"""
        if not context.args:
            await update.message.reply_text("사용법: /search [키워드]\n예: /search tech")
            return

        keyword = " ".join(context.args)
        results = await self._search_domains(keyword, limit=10)

        if not results:
            await update.message.reply_text(f"'{keyword}' 검색 결과가 없습니다.")
            return

        msg = f"🔍 <b>'{keyword}' 검색 결과</b>\n\n"

        for i, d in enumerate(results, 1):
            msg += f"{i}. <code>{d['full_name']}</code> - {d.get('total_score', 0)}점\n"

        await update.message.reply_text(msg, parse_mode="HTML")

    # ===== 콜백 쿼리 핸들러 =====

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """콜백 쿼리 처리"""
        query = update.callback_query
        await query.answer()  # 로딩 스피너 제거

        data = query.data
        logger.debug("callback_received", data=data)

        try:
            if data.startswith("watch:"):
                await self._callback_watch(query, data)
            elif data.startswith("ignore:"):
                await self._callback_ignore(query, data)
            elif data.startswith("detail:"):
                await self._callback_detail(query, data)
            elif data.startswith("unwatch:"):
                await self._callback_unwatch(query, data)
            elif data.startswith("check:"):
                await self._callback_check_availability(query, data)
            else:
                await query.answer("알 수 없는 작업입니다.", show_alert=True)

        except Exception as e:
            logger.error("callback_error", data=data, error=str(e))
            await query.answer("오류가 발생했습니다.", show_alert=True)

    async def _callback_watch(self, query, data: str) -> None:
        """관심 목록 추가 콜백"""
        domain_id = int(data.split(":")[1])

        if self.db_callback:
            success = await self.db_callback("add_to_watchlist", domain_id=domain_id)
            if success:
                await query.answer("✅ 관심 목록에 추가되었습니다!", show_alert=True)

                # 버튼 업데이트
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔍 상세보기",
                            callback_data=f"detail:{domain_id}"
                        ),
                        InlineKeyboardButton(
                            "❌ 관심해제",
                            callback_data=f"unwatch:{domain_id}"
                        ),
                    ]
                ]
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.answer("이미 관심 목록에 있거나 추가 실패", show_alert=True)
        else:
            await query.answer("데이터베이스 연결 없음", show_alert=True)

    async def _callback_ignore(self, query, data: str) -> None:
        """도메인 무시 콜백"""
        domain_id = int(data.split(":")[1])

        if self.db_callback:
            success = await self.db_callback("ignore_domain", domain_id=domain_id)
            if success:
                await query.answer("🚫 무시 처리되었습니다.", show_alert=True)

                # 메시지에 취소선 효과
                original_text = query.message.text or query.message.caption or ""
                await query.edit_message_text(
                    f"<s>{original_text}</s>\n\n🚫 무시됨",
                    parse_mode="HTML"
                )
            else:
                await query.answer("무시 처리 실패", show_alert=True)
        else:
            await query.answer("데이터베이스 연결 없음", show_alert=True)

    async def _callback_detail(self, query, data: str) -> None:
        """상세 정보 콜백"""
        domain_id = int(data.split(":")[1])

        if self.db_callback:
            domain = await self.db_callback("get_domain", domain_id=domain_id)

            if domain:
                detail_msg = self._format_domain_detail(domain)

                # 새 키보드
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔄 가용성 확인",
                            callback_data=f"check:{domain_id}"
                        ),
                        InlineKeyboardButton(
                            "⭐ 관심등록",
                            callback_data=f"watch:{domain_id}"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🔗 GoDaddy",
                            url=f"https://www.godaddy.com/domainsearch/find?domainToCheck={domain.get('full_name')}"
                        ),
                        InlineKeyboardButton(
                            "🔗 Namecheap",
                            url=f"https://www.namecheap.com/domains/registration/results/?domain={domain.get('full_name')}"
                        ),
                    ]
                ]

                await query.message.reply_text(
                    detail_msg,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.answer("도메인 정보를 찾을 수 없습니다.", show_alert=True)
        else:
            await query.answer("데이터베이스 연결 없음", show_alert=True)

    async def _callback_unwatch(self, query, data: str) -> None:
        """관심 목록 해제 콜백"""
        domain_id = int(data.split(":")[1])

        if self.db_callback:
            success = await self.db_callback("remove_from_watchlist", domain_id=domain_id)
            if success:
                await query.answer("❌ 관심 목록에서 제거되었습니다.", show_alert=True)
            else:
                await query.answer("제거 실패", show_alert=True)
        else:
            await query.answer("데이터베이스 연결 없음", show_alert=True)

    async def _callback_check_availability(self, query, data: str) -> None:
        """도메인 가용성 확인 콜백"""
        domain_id = int(data.split(":")[1])

        await query.answer("🔄 가용성 확인 중...", show_alert=False)

        if self.db_callback:
            domain = await self.db_callback("get_domain", domain_id=domain_id)

            if domain:
                # 도메인 가용성 확인
                from checker.availability import DomainAvailabilityChecker

                checker = DomainAvailabilityChecker()
                result = await checker.check(domain.get('full_name'))

                if result.available is True:
                    status_text = "✅ 등록 가능!"
                elif result.available is False:
                    status_text = f"❌ 이미 등록됨 (레지스트라: {result.registrar or 'N/A'})"
                else:
                    status_text = f"⚠️ 확인 불가 ({result.error or '알 수 없음'})"

                await query.message.reply_text(
                    f"<b>🔍 가용성 확인 결과</b>\n\n"
                    f"도메인: <code>{domain.get('full_name')}</code>\n"
                    f"상태: {status_text}\n"
                    f"소스: {result.source}",
                    parse_mode="HTML"
                )
            else:
                await query.answer("도메인 정보를 찾을 수 없습니다.", show_alert=True)
        else:
            await query.answer("데이터베이스 연결 없음", show_alert=True)

    # ===== 헬퍼 메서드 =====

    def _format_domain_detail(self, domain: Dict[str, Any]) -> str:
        """도메인 상세 정보 포맷팅"""
        days_left = domain.get('days_until_expiry', 'N/A')
        if isinstance(days_left, int):
            if days_left <= 1:
                expiry_text = "⚠️ 긴급! 오늘/내일 만료"
            elif days_left <= 7:
                expiry_text = f"⏰ {days_left}일 후 만료"
            else:
                expiry_text = f"📅 {days_left}일 후 만료"
        else:
            expiry_text = "📅 만료일 미상"

        return f"""
📋 <b>도메인 상세 정보</b>

📌 <code>{domain.get('full_name', 'N/A')}</code>
{expiry_text}

━━━ 점수 정보 ━━━
• 총점: <b>{domain.get('total_score', 0)}/100</b>
• 길이 점수: {domain.get('length_score', 0)}
• 키워드 점수: {domain.get('keyword_score', 0)}
• 패턴 점수: {domain.get('pattern_score', 0)}

━━━ 도메인 정보 ━━━
• 길이: {domain.get('length', 0)}자
• TLD: .{domain.get('tld', 'N/A')}
• 소스: {domain.get('source', 'N/A')}

━━━ 예상 가치 ━━━
💰 ${domain.get('estimated_value_min', 0):,} ~ ${domain.get('estimated_value_max', 0):,}
"""

    async def _get_system_stats(self) -> Dict[str, Any]:
        """시스템 통계 조회"""
        if self.db_callback:
            return await self.db_callback("get_stats") or {}
        return {}

    async def _get_top_domains(self, limit: int = 10) -> List[Dict]:
        """TOP 도메인 조회"""
        if self.db_callback:
            return await self.db_callback("get_top_domains", limit=limit) or []
        return []

    async def _get_watchlist(self) -> List[Dict]:
        """관심 목록 조회"""
        if self.db_callback:
            return await self.db_callback("get_watchlist") or []
        return []

    async def _search_domains(self, keyword: str, limit: int = 10) -> List[Dict]:
        """도메인 검색"""
        if self.db_callback:
            return await self.db_callback("search_domains", keyword=keyword, limit=limit) or []
        return []


# 테스트
if __name__ == "__main__":
    async def test():
        print("=== Telegram Bot Handler Test ===")
        print("Note: This requires TELEGRAM_BOT_TOKEN to be set")

        if not settings.telegram_bot_token:
            print("TELEGRAM_BOT_TOKEN not set, skipping test")
            return

        handler = TelegramBotHandler()
        success = await handler.start()
        print(f"Bot started: {success}")

        if success:
            print("Bot is running. Press Ctrl+C to stop.")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                await handler.stop()
                print("Bot stopped.")

    asyncio.run(test())
