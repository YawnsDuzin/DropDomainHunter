#!/usr/bin/env python3
"""
Domain Sniper - 메인 엔트리포인트
라즈베리파이4 무중단 운영 도메인 스나이핑 시스템

사용법:
    python main.py              # 전체 서비스 시작
    python main.py --web-only   # 웹 대시보드만 시작
    python main.py --crawl-now  # 즉시 크롤링 실행
"""

import asyncio
import os
import signal
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

# uvloop는 Windows에서 지원되지 않음
try:
    import uvloop
    HAS_UVLOOP = True
except ImportError:
    HAS_UVLOOP = False


def notify_systemd(state: str) -> None:
    """
    systemd에 상태 알림 전송

    Args:
        state: 상태 문자열 (예: "READY=1", "WATCHDOG=1")
    """
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return

    try:
        if notify_socket.startswith("@"):
            # Abstract socket
            notify_socket = "\0" + notify_socket[1:]

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.connect(notify_socket)
            sock.sendall(state.encode())
        finally:
            sock.close()
    except Exception:
        pass  # systemd 알림 실패는 무시

# uvloop 설정 (비동기 성능 최적화) - Windows에서는 건너뜀
if HAS_UVLOOP:
    uvloop.install()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings, validate_settings
from database import init_database, Database
from crawler import ExpiredDomainsCrawler, MultiSourceCrawler
from crawler.state import crawl_state
from scorer import DomainEvaluator
from notifier import NotificationManager
from database.models import Domain, CrawlLog

# 로깅 설정
def setup_logging():
    """구조화 로깅 설정"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(colors=True)
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 로그 레벨 설정
    import logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper()),
    )

    # 파일 로깅 (선택)
    if settings.log_full_path:
        settings.log_full_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(settings.log_full_path)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        logging.getLogger().addHandler(file_handler)


logger = structlog.get_logger()


class DomainSniper:
    """도메인 스나이퍼 메인 애플리케이션"""

    def __init__(self):
        self.db: Optional[Database] = None
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.evaluator: Optional[DomainEvaluator] = None
        self.notifier: Optional[NotificationManager] = None
        self.running = False

    async def initialize(self) -> None:
        """애플리케이션 초기화"""
        logger.info("initializing_domain_sniper")

        # 설정 검증
        warnings = validate_settings()
        for warning in warnings:
            logger.warning("config_warning", message=warning)

        # 데이터베이스 초기화
        self.db = await init_database(settings.database_full_path)

        # 키워드 데이터 로드
        keywords_path = Path(__file__).parent / "data" / "keywords.json"
        self.evaluator = DomainEvaluator(
            custom_keywords_path=keywords_path if keywords_path.exists() else None
        )

        # 알림 관리자 초기화
        self.notifier = NotificationManager(self.db)

        # 스케줄러 초기화
        self.scheduler = AsyncIOScheduler()
        self._setup_schedules()

        logger.info("domain_sniper_initialized")

    def _setup_schedules(self) -> None:
        """스케줄러 작업 설정"""
        # 1. 전체 스캔 (매일 06:00)
        self.scheduler.add_job(
            self.run_full_crawl,
            CronTrigger(hour=6, minute=0),
            id="full_crawl",
            name="Full domain crawl",
            replace_existing=True
        )

        # 2. 7일 이내 만료 도메인 스캔 (매 3시간)
        self.scheduler.add_job(
            self.run_week_crawl,
            IntervalTrigger(hours=settings.crawl_week_interval_hours),
            id="week_crawl",
            name="7-day expiry crawl",
            replace_existing=True
        )

        # 3. 1일 이내 만료 도메인 스캔 (매 30분)
        self.scheduler.add_job(
            self.run_day_crawl,
            IntervalTrigger(minutes=settings.crawl_day_interval_minutes),
            id="day_crawl",
            name="1-day expiry crawl",
            replace_existing=True
        )

        # 4. 일일 리포트 (설정된 시간)
        self.scheduler.add_job(
            self.send_daily_report,
            CronTrigger(
                hour=settings.daily_report_hour,
                minute=settings.daily_report_minute
            ),
            id="daily_report",
            name="Daily report",
            replace_existing=True
        )

        # 5. 하트비트 (설정된 경우)
        if settings.heartbeat_interval_minutes > 0:
            self.scheduler.add_job(
                self.send_heartbeat,
                IntervalTrigger(minutes=settings.heartbeat_interval_minutes),
                id="heartbeat",
                name="Heartbeat",
                replace_existing=True
            )

        # 6. systemd watchdog (매 60초)
        self.scheduler.add_job(
            self._notify_watchdog,
            IntervalTrigger(seconds=60),
            id="watchdog",
            name="Systemd Watchdog",
            replace_existing=True
        )

        logger.info("schedules_configured")

    async def reload_scheduler(self, runtime_settings: dict = None) -> None:
        """
        런타임 설정에 따라 스케줄러 재설정

        Args:
            runtime_settings: 런타임 설정 딕셔너리 (None이면 파일에서 로드)
        """
        import json
        from pathlib import Path

        # 런타임 설정 로드
        if runtime_settings is None:
            settings_path = Path(__file__).parent / "data" / "runtime_settings.json"
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    runtime_settings = json.load(f)
            else:
                runtime_settings = {}

        logger.info("reloading_scheduler", settings=runtime_settings)

        # 기존 크롤링 작업 제거
        for job_id in ["full_crawl", "week_crawl", "day_crawl", "daily_report", "heartbeat"]:
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass

        # 전체 스캔 재설정
        if runtime_settings.get("crawl_full_enabled", True):
            crawl_time = runtime_settings.get("crawl_full_time", "06:00")
            hour, minute = map(int, crawl_time.split(":"))
            self.scheduler.add_job(
                self.run_full_crawl,
                CronTrigger(hour=hour, minute=minute),
                id="full_crawl",
                name="Full domain crawl",
                replace_existing=True
            )
            logger.info("full_crawl_scheduled", time=crawl_time)

        # 7일 스캔 재설정
        if runtime_settings.get("crawl_week_enabled", True):
            interval = runtime_settings.get("crawl_week_interval_hours", 3)
            self.scheduler.add_job(
                self.run_week_crawl,
                IntervalTrigger(hours=interval),
                id="week_crawl",
                name="7-day expiry crawl",
                replace_existing=True
            )
            logger.info("week_crawl_scheduled", interval_hours=interval)

        # 1일 스캔 재설정
        if runtime_settings.get("crawl_day_enabled", True):
            interval = runtime_settings.get("crawl_day_interval_minutes", 30)
            self.scheduler.add_job(
                self.run_day_crawl,
                IntervalTrigger(minutes=interval),
                id="day_crawl",
                name="1-day expiry crawl",
                replace_existing=True
            )
            logger.info("day_crawl_scheduled", interval_minutes=interval)

        # 일일 리포트 재설정
        daily_report_time = runtime_settings.get("daily_report_time", "08:00")
        hour, minute = map(int, daily_report_time.split(":"))
        self.scheduler.add_job(
            self.send_daily_report,
            CronTrigger(hour=hour, minute=minute),
            id="daily_report",
            name="Daily report",
            replace_existing=True
        )

        # 하트비트 재설정
        heartbeat_interval = runtime_settings.get("heartbeat_interval_minutes", 0)
        if heartbeat_interval > 0:
            self.scheduler.add_job(
                self.send_heartbeat,
                IntervalTrigger(minutes=heartbeat_interval),
                id="heartbeat",
                name="Heartbeat",
                replace_existing=True
            )
            logger.info("heartbeat_scheduled", interval_minutes=heartbeat_interval)

        logger.info("scheduler_reloaded")

    async def run_full_crawl(self, is_manual: bool = False) -> bool:
        """전체 크롤링 실행 (다중 소스 통합)"""
        # 크롤링 상태 확인 및 시작
        if not await crawl_state.try_start("full", is_manual=is_manual):
            logger.warning("full_crawl_skipped", reason="already_running")
            return False

        logger.info("starting_full_crawl", is_manual=is_manual)
        start_time = datetime.now()

        try:
            await crawl_state.update_progress(5, "크롤러 초기화 중...")

            # 런타임 설정 로드
            runtime_settings = self._load_runtime_settings()
            use_expireddomains = runtime_settings.get("use_expireddomains", settings.use_expireddomains)
            use_alternative = runtime_settings.get("use_alternative_sources", settings.use_alternative_sources)
            alt_sources = runtime_settings.get("alternative_sources", settings.alternative_sources)
            if isinstance(alt_sources, str):
                alt_sources = [s.strip() for s in alt_sources.split(",") if s.strip()]
            parallel_crawl = runtime_settings.get("parallel_crawl", False)
            crawl_full_days = runtime_settings.get("crawl_full_days", 30)

            # 도메인 필터 설정 추출
            filter_settings = self._get_filter_settings(runtime_settings)

            # 모든 소스가 비활성화된 경우 경고
            if not use_expireddomains and not use_alternative:
                logger.warning("full_crawl_skipped", reason="no_sources_enabled")
                await crawl_state.finish(False, "모든 데이터 소스가 비활성화되어 있습니다.")
                return False

            # 진행 상황 콜백
            async def progress_callback(percent: int, message: str):
                await crawl_state.update_progress(percent, message)

            # MultiSourceCrawler 사용 (필터 설정 전달)
            async with MultiSourceCrawler(use_anti_blocking=True, filter_settings=filter_settings) as crawler:
                all_domains = await crawler.crawl_all(
                    use_expireddomains=use_expireddomains,
                    use_alternative=use_alternative,
                    days_until_expiry=crawl_full_days,
                    max_pages_per_tld=5,
                    alternative_sources=alt_sources if alt_sources else None,
                    parallel=parallel_crawl,
                    progress_callback=progress_callback
                )

                # 소스별 통계 가져오기
                stats = crawler.get_stats()
                sources_used = [
                    source for source, data in stats["sources"].items()
                    if data["domains"] > 0
                ]

            logger.info("multi_source_crawl_complete", total=len(all_domains), sources=sources_used)

            await crawl_state.update_progress(70, "도메인 평가 및 저장 중...")
            # 평가 및 저장
            result = await self._process_domains(all_domains, "full_crawl")

            # 로그 기록
            duration = (datetime.now() - start_time).total_seconds()
            source_str = ",".join(sources_used) if sources_used else "none"
            await self._log_crawl(source_str, "full", result, duration)

            await crawl_state.update_progress(90, "알림 발송 중...")
            # 고점수 도메인 알림
            notified_count = await self.notifier.notify_high_score_domains()

            # 크롤링 완료 알림 발송
            await self.notifier.send_crawl_summary(
                source=f"전체 스캔 ({source_str})",
                total_found=result['total_found'],
                new_domains=result['new_domains'],
                high_score_count=result['high_score_count'],
                duration=duration
            )

            await crawl_state.finish(True, f"완료: {result['total_found']}개 발견, {result['new_domains']}개 신규, {notified_count}개 알림")
            return True

        except Exception as e:
            logger.error("full_crawl_error", error=str(e))
            await self.notifier.send_error_alert("full_crawl", str(e))
            await crawl_state.finish(False, f"오류: {str(e)}")
            return False

    def _load_runtime_settings(self) -> dict:
        """런타임 설정 로드"""
        import json
        settings_path = Path(__file__).parent / "data" / "runtime_settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _get_filter_settings(self, runtime_settings: dict) -> dict:
        """
        런타임 설정에서 도메인 필터 설정 추출

        Args:
            runtime_settings: 런타임 설정 딕셔너리

        Returns:
            도메인 필터 설정 딕셔너리
        """
        # TLD 리스트 파싱
        allowed_tlds_str = runtime_settings.get("allowed_tlds", "")
        if isinstance(allowed_tlds_str, str) and allowed_tlds_str.strip():
            allowed_tlds = [t.strip().lower() for t in allowed_tlds_str.split(",") if t.strip()]
        else:
            allowed_tlds = settings.tld_list  # 기본값 사용

        filter_settings = {
            "min_domain_length": runtime_settings.get("min_domain_length", settings.min_domain_length),
            "max_domain_length": runtime_settings.get("max_domain_length", settings.max_domain_length),
            "allowed_tlds": allowed_tlds,
            "allow_numbers": runtime_settings.get("allow_numbers", settings.allow_numbers),
            "allow_hyphens": runtime_settings.get("allow_hyphens", settings.allow_hyphens),
        }

        logger.info(
            "domain_filter_settings_loaded",
            min_length=filter_settings["min_domain_length"],
            max_length=filter_settings["max_domain_length"],
            tlds=filter_settings["allowed_tlds"],
            allow_numbers=filter_settings["allow_numbers"],
            allow_hyphens=filter_settings["allow_hyphens"]
        )

        return filter_settings

    async def run_week_crawl(self, is_manual: bool = False) -> bool:
        """7일 이내 만료 도메인 크롤링 (다중 소스 통합)"""
        if not await crawl_state.try_start("week", is_manual=is_manual):
            logger.warning("week_crawl_skipped", reason="already_running")
            return False

        logger.info("starting_week_crawl", is_manual=is_manual)
        start_time = datetime.now()

        try:
            await crawl_state.update_progress(10, "크롤러 초기화 중...")

            # 런타임 설정 로드
            runtime_settings = self._load_runtime_settings()
            use_expireddomains = runtime_settings.get("use_expireddomains", settings.use_expireddomains)
            use_alternative = runtime_settings.get("use_alternative_sources", settings.use_alternative_sources)
            alt_sources = runtime_settings.get("alternative_sources", settings.alternative_sources)
            if isinstance(alt_sources, str):
                alt_sources = [s.strip() for s in alt_sources.split(",") if s.strip()]
            crawl_week_days = runtime_settings.get("crawl_week_days", 7)

            # 도메인 필터 설정 추출
            filter_settings = self._get_filter_settings(runtime_settings)

            # 모든 소스가 비활성화된 경우 경고
            if not use_expireddomains and not use_alternative:
                logger.warning("week_crawl_skipped", reason="no_sources_enabled")
                await crawl_state.finish(False, "모든 데이터 소스가 비활성화되어 있습니다.")
                return False

            # 진행 상황 콜백
            async def progress_callback(percent: int, message: str):
                await crawl_state.update_progress(percent, message)

            # MultiSourceCrawler 사용 (필터 설정 전달)
            async with MultiSourceCrawler(use_anti_blocking=True, filter_settings=filter_settings) as crawler:
                await crawl_state.update_progress(20, f"{crawl_week_days}일 이내 만료 도메인 크롤링 중...")
                raw_domains = await crawler.crawl_all(
                    use_expireddomains=use_expireddomains,
                    use_alternative=use_alternative,
                    days_until_expiry=crawl_week_days,
                    max_pages_per_tld=3,
                    alternative_sources=alt_sources if alt_sources else None,
                    progress_callback=progress_callback
                )

                # 소스별 통계
                stats = crawler.get_stats()
                sources_used = [
                    source for source, data in stats["sources"].items()
                    if data["domains"] > 0
                ]

            await crawl_state.update_progress(70, "도메인 평가 및 저장 중...")
            result = await self._process_domains(raw_domains, "week_crawl")

            duration = (datetime.now() - start_time).total_seconds()
            source_str = ",".join(sources_used) if sources_used else "expireddomains"
            await self._log_crawl(source_str, "week", result, duration)

            await crawl_state.update_progress(90, "알림 발송 중...")
            notified_count = await self.notifier.notify_high_score_domains()

            # 크롤링 완료 알림 발송
            await self.notifier.send_crawl_summary(
                source=f"{crawl_week_days}일 이내 스캔 ({source_str})",
                total_found=result['total_found'],
                new_domains=result['new_domains'],
                high_score_count=result['high_score_count'],
                duration=duration
            )

            await crawl_state.finish(True, f"완료: {result['total_found']}개 발견, {result['new_domains']}개 신규, {notified_count}개 알림")
            return True

        except Exception as e:
            logger.error("week_crawl_error", error=str(e))
            await self.notifier.send_error_alert("week_crawl", str(e))
            await crawl_state.finish(False, f"오류: {str(e)}")
            return False

    async def run_day_crawl(self, is_manual: bool = False) -> bool:
        """1일 이내 만료 도메인 크롤링 (다중 소스 통합)"""
        if not await crawl_state.try_start("day", is_manual=is_manual):
            logger.warning("day_crawl_skipped", reason="already_running")
            return False

        logger.info("starting_day_crawl", is_manual=is_manual)
        start_time = datetime.now()

        try:
            await crawl_state.update_progress(10, "크롤러 초기화 중...")

            # 런타임 설정 로드
            runtime_settings = self._load_runtime_settings()
            use_expireddomains = runtime_settings.get("use_expireddomains", settings.use_expireddomains)
            use_alternative = runtime_settings.get("use_alternative_sources", settings.use_alternative_sources)

            # 도메인 필터 설정 추출
            filter_settings = self._get_filter_settings(runtime_settings)

            # 모든 소스가 비활성화된 경우 경고
            if not use_expireddomains and not use_alternative:
                logger.warning("day_crawl_skipped", reason="no_sources_enabled")
                await crawl_state.finish(False, "모든 데이터 소스가 비활성화되어 있습니다.")
                return False

            # MultiSourceCrawler 사용 (필터 설정 전달)
            async with MultiSourceCrawler(use_anti_blocking=True, filter_settings=filter_settings) as crawler:
                await crawl_state.update_progress(20, "1일 이내 만료 도메인 크롤링 중...")
                # PendingDelete 크롤링 (EstiBot 포함)
                raw_domains = await crawler.crawl_pending_delete(
                    max_pages=3 if use_expireddomains else 0,
                    use_alternative=use_alternative,
                    alternative_sources=["estibot"] if use_alternative else None
                )

                # 소스별 통계
                stats = crawler.get_stats()
                sources_used = [
                    source for source, data in stats["sources"].items()
                    if data["domains"] > 0
                ]

            await crawl_state.update_progress(70, "도메인 평가 및 저장 중...")
            result = await self._process_domains(raw_domains, "day_crawl")

            duration = (datetime.now() - start_time).total_seconds()
            source_str = ",".join(sources_used) if sources_used else "expireddomains"
            await self._log_crawl(source_str, "day", result, duration)

            await crawl_state.update_progress(90, "알림 발송 중...")
            # 긴급 알림 (1일 이내는 즉시)
            notified_count = await self.notifier.notify_high_score_domains()

            # 크롤링 완료 알림 발송
            await self.notifier.send_crawl_summary(
                source=f"1일 이내 긴급 스캔 ({source_str})",
                total_found=result['total_found'],
                new_domains=result['new_domains'],
                high_score_count=result['high_score_count'],
                duration=duration
            )

            await crawl_state.finish(True, f"완료: {result['total_found']}개 발견, {result['new_domains']}개 신규, {notified_count}개 알림")
            return True

        except Exception as e:
            logger.error("day_crawl_error", error=str(e))
            await self.notifier.send_error_alert("day_crawl", str(e))
            await crawl_state.finish(False, f"오류: {str(e)}")
            return False

    async def _process_domains(self, raw_domains: list, source: str) -> dict:
        """
        도메인 처리 (가용성 체크 → 평가 → 저장)

        Args:
            raw_domains: 크롤링된 원시 데이터
            source: 크롤링 소스

        Returns:
            처리 결과 통계
        """
        from datetime import date
        from checker.availability import DomainAvailabilityChecker

        # 런타임 설정에서 가용성 체크 옵션 확인
        runtime_settings = self._load_runtime_settings()
        check_availability = runtime_settings.get("check_availability", settings.check_availability)
        availability_concurrency = runtime_settings.get("availability_concurrency", 3)

        original_count = len(raw_domains)
        filtered_domains = raw_domains

        # 가용성 체크가 활성화된 경우
        if check_availability and raw_domains:
            logger.info("availability_check_enabled", total_domains=original_count)
            await crawl_state.update_progress(72, f"도메인 가용성 체크 중 (0/{original_count})...")

            checker = DomainAvailabilityChecker(
                timeout=15.0,
                use_cache=True,
                cache_ttl=3600,  # 1시간 캐시
                base_delay=1.0,
                max_concurrency=availability_concurrency
            )

            # 진행 상황 콜백
            async def availability_progress(checked: int, total: int, domain: str):
                percent = 72 + int((checked / total) * 15)  # 72% ~ 87%
                await crawl_state.update_progress(
                    percent,
                    f"도메인 가용성 체크 중 ({checked}/{total})..."
                )

            # 등록 가능한 도메인만 필터링
            filtered_domains = await checker.filter_available_domains(
                raw_domains,
                concurrency=availability_concurrency,
                progress_callback=availability_progress
            )

            # 통계 로깅
            stats = checker.get_stats()
            logger.info(
                "availability_check_complete",
                original=original_count,
                available=len(filtered_domains),
                filtered_out=original_count - len(filtered_domains),
                stats=stats
            )

            await crawl_state.update_progress(88, f"가용성 체크 완료: {len(filtered_domains)}개 등록 가능")

        # Domain 객체 변환
        domains = []
        for raw in filtered_domains:
            domain = Domain(
                name=raw["name"],
                tld=raw["tld"],
                full_name=raw["full_name"],
                length=raw["length"],
                expiry_date=raw.get("expiry_date"),
                source=raw.get("source", source),
                auction_url=raw.get("auction_url", "")
            )
            domains.append(domain)

        # 평가
        evaluated_domains = self.evaluator.bulk_evaluate(domains)

        # 저장
        new_count = await self.db.bulk_insert_domains(evaluated_domains)

        # 고점수 도메인 수
        high_score_count = sum(1 for d in evaluated_domains if d.total_score >= settings.min_score_alert)

        logger.info(
            "domains_processed",
            total=original_count,
            available=len(filtered_domains),
            new=new_count,
            high_score=high_score_count
        )

        return {
            "total_found": original_count,
            "available_count": len(filtered_domains),
            "new_domains": new_count,
            "high_score_count": high_score_count
        }

    async def _log_crawl(self, source: str, crawl_type: str, result: dict, duration: float) -> None:
        """크롤링 로그 기록"""
        log = CrawlLog(
            source=source,
            crawl_type=crawl_type,
            total_found=result["total_found"],
            new_domains=result["new_domains"],
            high_score_count=result["high_score_count"],
            status="success",
            duration_seconds=duration
        )
        await self.db.add_crawl_log(log)

    async def send_daily_report(self) -> None:
        """일일 리포트 발송"""
        logger.info("sending_daily_report")
        await self.notifier.send_daily_report()

    async def send_heartbeat(self) -> None:
        """하트비트 발송"""
        logger.debug("sending_heartbeat")
        await self.notifier.send_heartbeat()

    async def _notify_watchdog(self) -> None:
        """systemd watchdog에 상태 알림"""
        notify_systemd("WATCHDOG=1")

    async def start(self) -> None:
        """애플리케이션 시작"""
        await self.initialize()

        self.running = True
        self.scheduler.start()

        logger.info("domain_sniper_started")

        # systemd에 준비 완료 알림
        notify_systemd("READY=1")

        # 시작 알림
        await self.notifier.telegram.send_message(
            "🚀 <b>Domain Sniper 시작됨</b>\n\n"
            f"⏰ 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🔄 전체 스캔: 매일 06:00\n"
            f"🔄 7일 스캔: {settings.crawl_week_interval_hours}시간마다\n"
            f"🔄 1일 스캔: {settings.crawl_day_interval_minutes}분마다"
        )

        # 웹 대시보드 시작 (옵션)
        if settings.web_enabled:
            asyncio.create_task(self._start_web_server())

        # 메인 루프
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _start_web_server(self) -> None:
        """웹 서버 시작"""
        try:
            import uvicorn
            from web.app import create_app

            app = create_app(self.db, self)

            config = uvicorn.Config(
                app=app,
                host=settings.web_host,
                port=settings.web_port,
                log_level="warning"
            )
            server = uvicorn.Server(config)

            logger.info("web_server_starting", host=settings.web_host, port=settings.web_port)
            await server.serve()

        except ImportError:
            logger.warning("web_server_not_available", reason="FastAPI/uvicorn not installed")
        except Exception as e:
            logger.error("web_server_error", error=str(e))

    async def stop(self) -> None:
        """애플리케이션 종료"""
        logger.info("stopping_domain_sniper")
        notify_systemd("STOPPING=1")
        self.running = False

        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        if self.db:
            await self.db.close()

        logger.info("domain_sniper_stopped")

    async def run_crawl_now(self) -> None:
        """즉시 크롤링 실행"""
        await self.initialize()
        logger.info("running_immediate_crawl")
        await self.run_full_crawl()
        await self.stop()


async def main():
    """메인 함수"""
    setup_logging()

    # 명령행 인자 처리
    args = sys.argv[1:]

    sniper = DomainSniper()

    # 시그널 핸들러
    def signal_handler(sig, frame):
        logger.info("received_shutdown_signal", signal=sig)
        asyncio.create_task(sniper.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if "--crawl-now" in args:
        # 즉시 크롤링 모드
        await sniper.run_crawl_now()
    elif "--web-only" in args:
        # 웹 서버만 실행
        await sniper.initialize()
        await sniper._start_web_server()
    else:
        # 전체 서비스 실행
        await sniper.start()


if __name__ == "__main__":
    asyncio.run(main())
