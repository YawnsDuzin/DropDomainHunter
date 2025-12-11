"""
Domain Sniper - 웹 대시보드
FastAPI + Jinja2 경량 웹 인터페이스
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING, List

from fastapi import FastAPI, Request, Form, HTTPException, Body, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import structlog

from database.models import Database
from config import settings
from crawler.state import crawl_state
from scorer.keyword import KeywordScorer

if TYPE_CHECKING:
    from main import DomainSniper

logger = structlog.get_logger()

# 템플릿 디렉토리
TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(db: Database, sniper: "DomainSniper" = None) -> FastAPI:
    """
    FastAPI 앱 생성

    Args:
        db: 데이터베이스 인스턴스

    Returns:
        FastAPI 앱
    """
    app = FastAPI(
        title="Domain Sniper",
        description="라즈베리파이4 도메인 스나이핑 대시보드",
        version="1.0.0"
    )

    # 템플릿 설정
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # 커스텀 필터 추가
    templates.env.filters["score_color"] = lambda score: (
        "danger" if score >= 80 else "warning" if score >= 60 else "success" if score >= 40 else "secondary"
    )

    # ===== 메인 페이지 =====

    @app.get("/", response_class=HTMLResponse)
    async def index(
        request: Request,
        page: int = 1,
        min_score: Optional[str] = Query(default=None),
        tld: Optional[str] = None,
        search: Optional[str] = None,
        expiry: Optional[str] = None,
        min_length: Optional[str] = Query(default=None),
        max_length: Optional[str] = Query(default=None),
        expiry_start: Optional[str] = Query(default=None),
        expiry_end: Optional[str] = Query(default=None),
        min_value: Optional[str] = Query(default=None),
        max_value: Optional[str] = Query(default=None),
        sort: str = "score_desc"
    ):
        """메인 페이지 - 도메인 목록"""
        per_page = 20
        offset = (page - 1) * per_page

        # 빈 문자열을 None으로, 유효한 값은 정수로 변환
        min_score_int = int(min_score) if min_score and min_score.strip() else None
        min_length_int = int(min_length) if min_length and min_length.strip() else None
        max_length_int = int(max_length) if max_length and max_length.strip() else None
        min_value_int = int(min_value) if min_value and min_value.strip() else None
        max_value_int = int(max_value) if max_value and max_value.strip() else None
        expiry_start_str = expiry_start.strip() if expiry_start and expiry_start.strip() else None
        expiry_end_str = expiry_end.strip() if expiry_end and expiry_end.strip() else None

        # 정렬 옵션
        sort_options = {
            "score_desc": "total_score DESC, expiry_date ASC",
            "score_asc": "total_score ASC",
            "expiry_asc": "expiry_date ASC, total_score DESC",
            "expiry_desc": "expiry_date DESC",
            "length_asc": "length ASC, total_score DESC",
            "length_desc": "length DESC, total_score DESC",
            "name_asc": "name ASC",
            "name_desc": "name DESC",
            "value_desc": "estimated_value DESC, total_score DESC",
            "value_asc": "estimated_value ASC",
        }
        order_by = sort_options.get(sort, "total_score DESC, expiry_date ASC")

        # 만료일 필터 (기존 단축 필터)
        days_until_expiry = None
        if expiry == "today":
            days_until_expiry = 0
        elif expiry == "week":
            days_until_expiry = 7
        elif expiry == "month":
            days_until_expiry = 30

        # 도메인 조회
        domains = await db.get_domains(
            limit=per_page,
            offset=offset,
            min_score=min_score_int,
            order_by=order_by,
            tld=tld if tld else None,
            search=search if search else None,
            days_until_expiry=days_until_expiry,
            min_length=min_length_int,
            max_length=max_length_int,
            expiry_start=expiry_start_str,
            expiry_end=expiry_end_str,
            min_value=min_value_int,
            max_value=max_value_int,
        )

        # 총 개수 (페이지네이션용)
        total_count = await db.get_total_count(
            min_score=min_score_int,
            tld=tld if tld else None,
            search=search if search else None,
            days_until_expiry=days_until_expiry,
            min_length=min_length_int,
            max_length=max_length_int,
            expiry_start=expiry_start_str,
            expiry_end=expiry_end_str,
            min_value=min_value_int,
            max_value=max_value_int,
        )
        total_pages = (total_count + per_page - 1) // per_page

        # 통계
        stats = await db.get_domain_stats()

        # 사용 가능한 TLD 목록
        available_tlds = await db.get_available_tlds()

        return templates.TemplateResponse("index.html", {
            "request": request,
            "domains": domains,
            "stats": stats,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "min_score": min_score_int,
            "tld": tld,
            "search": search,
            "expiry": expiry,
            "min_length": min_length_int,
            "max_length": max_length_int,
            "expiry_start": expiry_start_str,
            "expiry_end": expiry_end_str,
            "min_value": min_value_int,
            "max_value": max_value_int,
            "sort": sort,
            "available_tlds": available_tlds,
            "settings": settings
        })

    # ===== 워치리스트 =====

    @app.get("/watchlist", response_class=HTMLResponse)
    async def watchlist(request: Request):
        """워치리스트 페이지"""
        items = await db.get_watchlist()

        return templates.TemplateResponse("watchlist.html", {
            "request": request,
            "items": items,
            "settings": settings
        })

    @app.post("/watchlist/add")
    async def add_to_watchlist(domain_id: int = Form(...), note: str = Form("")):
        """워치리스트에 추가"""
        await db.add_to_watchlist(domain_id, note)
        return RedirectResponse(url="/watchlist", status_code=303)

    @app.post("/watchlist/remove/{item_id}")
    async def remove_from_watchlist(item_id: int):
        """워치리스트에서 제거"""
        await db.remove_from_watchlist(item_id)
        return RedirectResponse(url="/watchlist", status_code=303)

    # ===== 도메인 상세 =====

    @app.get("/domain/{domain_id}", response_class=HTMLResponse)
    async def domain_detail(request: Request, domain_id: int):
        """도메인 상세 페이지"""
        # ID로 도메인 조회
        domains = await db.get_domains(limit=1000)
        domain = next((d for d in domains if d.id == domain_id), None)

        if not domain:
            raise HTTPException(status_code=404, detail="Domain not found")

        return templates.TemplateResponse("domain_detail.html", {
            "request": request,
            "domain": domain,
            "settings": settings
        })

    @app.post("/domain/{domain_id}/status")
    async def update_domain_status(domain_id: int, status: str = Form(...)):
        """도메인 상태 업데이트"""
        await db.update_domain_status(domain_id, status)
        return RedirectResponse(url=f"/domain/{domain_id}", status_code=303)

    # ===== 설정 =====

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        """설정 페이지"""
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "settings": settings
        })

    # ===== 로그 =====

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request, limit: int = 50):
        """크롤링 로그 페이지"""
        logs = await db.get_crawl_logs(limit=limit)

        return templates.TemplateResponse("logs.html", {
            "request": request,
            "logs": logs,
            "settings": settings
        })

    # ===== API 엔드포인트 =====

    @app.get("/api/stats")
    async def api_stats():
        """통계 API"""
        stats = await db.get_domain_stats()
        return stats

    @app.get("/api/stats/charts")
    async def api_stats_charts():
        """차트용 통계 API"""
        stats = await db.get_domain_stats()
        tld_stats = await db.get_tld_stats()
        daily_stats = await db.get_daily_stats(days=7)

        return {
            "score_distribution": stats.get("score_distribution", {}),
            "tld_distribution": tld_stats,
            "daily_trend": daily_stats
        }

    @app.get("/api/domains")
    async def api_domains(
        limit: int = 20,
        offset: int = 0,
        min_score: Optional[int] = None
    ):
        """도메인 목록 API"""
        domains = await db.get_domains(
            limit=limit,
            offset=offset,
            min_score=min_score
        )
        return [d.to_dict() for d in domains]

    @app.get("/api/health")
    async def api_health():
        """헬스체크 API"""
        return {
            "status": "healthy",
            "database": "connected"
        }

    # ===== 크롤링 관리 API =====

    @app.get("/api/crawl/status")
    async def get_crawl_status():
        """크롤링 상태 조회"""
        return crawl_state.to_dict()

    @app.post("/api/crawl/trigger")
    async def trigger_crawl(crawl_type: str = Form("full")):
        """
        수동 크롤링 트리거

        자동 크롤링과 충돌 방지:
        - crawl_state를 통해 전역 잠금 관리
        - 이미 크롤링 중이면 거부
        """
        if sniper is None:
            return {"success": False, "message": "크롤링 서비스가 초기화되지 않았습니다."}

        if crawl_state.is_running:
            return {
                "success": False,
                "message": f"이미 크롤링이 진행 중입니다. ({crawl_state.status.crawl_type})",
                "status": crawl_state.to_dict()
            }

        # 백그라운드에서 크롤링 실행
        async def run_crawl():
            try:
                if crawl_type == "full":
                    await sniper.run_full_crawl(is_manual=True)
                elif crawl_type == "week":
                    await sniper.run_week_crawl(is_manual=True)
                elif crawl_type == "day":
                    await sniper.run_day_crawl(is_manual=True)
            except Exception as e:
                logger.error("manual_crawl_error", error=str(e))
                await crawl_state.finish(False, f"오류: {str(e)}")

        asyncio.create_task(run_crawl())

        return {
            "success": True,
            "message": f"{crawl_type} 크롤링이 시작되었습니다.",
            "type": crawl_type
        }

    # ===== 데이터 내보내기 =====

    @app.get("/api/export/csv")
    async def export_csv(
        min_score: Optional[int] = None,
        tld: Optional[str] = None,
    ):
        """도메인 목록 CSV 내보내기"""
        import io
        import csv

        # 최대 1000개까지 내보내기
        domains = await db.get_domains(
            limit=1000,
            min_score=min_score,
            tld=tld if tld else None,
            order_by="total_score DESC"
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # 헤더
        writer.writerow([
            "도메인", "TLD", "길이", "만료일", "점수",
            "길이점수", "키워드점수", "패턴점수", "예상가치", "소스"
        ])

        # 데이터
        for d in domains:
            writer.writerow([
                d.full_name, d.tld, d.length,
                d.expiry_date.isoformat() if d.expiry_date else "",
                d.total_score, d.length_score, d.keyword_score, d.pattern_score,
                d.estimated_value_str, d.source
            ])

        output.seek(0)

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=domains.csv"}
        )

    # ===== 키워드 관리 API =====

    # 커스텀 키워드 파일 경로
    CUSTOM_KEYWORDS_PATH = Path(__file__).parent.parent / "data" / "custom_keywords.json"

    def _load_custom_keywords() -> dict:
        """커스텀 키워드 로드"""
        if CUSTOM_KEYWORDS_PATH.exists():
            try:
                with open(CUSTOM_KEYWORDS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_custom_keywords(keywords: dict) -> bool:
        """커스텀 키워드 저장"""
        try:
            CUSTOM_KEYWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(CUSTOM_KEYWORDS_PATH, "w", encoding="utf-8") as f:
                json.dump(keywords, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("save_keywords_failed", error=str(e))
            return False

    @app.get("/api/keywords")
    async def get_keywords():
        """키워드 목록 조회"""
        scorer = KeywordScorer()
        custom_keywords = _load_custom_keywords()

        # 기본 키워드와 커스텀 키워드 분리
        default_keywords = []
        for keyword, score in KeywordScorer.DEFAULT_KEYWORDS.items():
            default_keywords.append({
                "keyword": keyword,
                "score": score,
                "category": scorer.get_keyword_category(keyword),
                "is_custom": False
            })

        custom_list = []
        for keyword, data in custom_keywords.items():
            # 기존 형식 호환: score만 있는 경우 vs {score, category} 형식
            if isinstance(data, dict):
                score = data.get("score", 0)
                category = data.get("category", "GENERIC")
            else:
                score = data
                category = "GENERIC"
            custom_list.append({
                "keyword": keyword,
                "score": score,
                "category": category,
                "is_custom": True
            })

        return {
            "default": sorted(default_keywords, key=lambda x: (-x["score"], x["keyword"])),
            "custom": sorted(custom_list, key=lambda x: (-x["score"], x["keyword"])),
            "total_count": len(default_keywords) + len(custom_list)
        }

    @app.post("/api/keywords")
    async def add_keyword(
        keyword: str = Form(...),
        score: int = Form(...),
        category: str = Form(default="GENERIC")
    ):
        """커스텀 키워드 추가"""
        keyword = keyword.lower().strip()

        if not keyword:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "키워드를 입력해주세요."}
            )

        if len(keyword) > 20:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "키워드는 20자 이내로 입력해주세요."}
            )

        score = min(100, max(0, score))

        # category 유효성 검사
        valid_categories = ["TECH", "FINANCE", "BUSINESS", "GENERIC"]
        if category not in valid_categories:
            category = "GENERIC"

        custom_keywords = _load_custom_keywords()
        custom_keywords[keyword] = {"score": score, "category": category}

        if _save_custom_keywords(custom_keywords):
            return {"success": True, "message": f"키워드 '{keyword}'가 추가되었습니다.", "keyword": keyword, "score": score, "category": category}
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "키워드 저장에 실패했습니다."}
            )

    @app.put("/api/keywords/{keyword}")
    async def update_keyword(
        keyword: str,
        score: int = Form(...),
        category: str = Form(default=None)
    ):
        """커스텀 키워드 수정"""
        keyword = keyword.lower().strip()
        score = min(100, max(0, score))

        custom_keywords = _load_custom_keywords()

        if keyword not in custom_keywords:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "커스텀 키워드를 찾을 수 없습니다."}
            )

        # category가 전달되지 않으면 기존 category 유지
        if category is None:
            old_data = custom_keywords[keyword]
            if isinstance(old_data, dict):
                category = old_data.get("category", "GENERIC")
            else:
                category = "GENERIC"
        else:
            # category 유효성 검사
            valid_categories = ["TECH", "FINANCE", "BUSINESS", "GENERIC"]
            if category not in valid_categories:
                category = "GENERIC"

        custom_keywords[keyword] = {"score": score, "category": category}

        if _save_custom_keywords(custom_keywords):
            return {"success": True, "message": f"키워드 '{keyword}'가 수정되었습니다.", "keyword": keyword, "score": score, "category": category}
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "키워드 저장에 실패했습니다."}
            )

    @app.delete("/api/keywords/{keyword}")
    async def delete_keyword(keyword: str):
        """커스텀 키워드 삭제"""
        keyword = keyword.lower().strip()

        custom_keywords = _load_custom_keywords()

        if keyword not in custom_keywords:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "커스텀 키워드를 찾을 수 없습니다."}
            )

        del custom_keywords[keyword]

        if _save_custom_keywords(custom_keywords):
            return {"success": True, "message": f"키워드 '{keyword}'가 삭제되었습니다."}
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "키워드 삭제에 실패했습니다."}
            )

    # ===== 키워드 관리 페이지 =====

    @app.get("/keywords", response_class=HTMLResponse)
    async def keywords_page(request: Request):
        """키워드 관리 페이지"""
        return templates.TemplateResponse("keywords.html", {
            "request": request,
            "settings": settings
        })

    # ===== 런타임 설정 관리 API =====

    RUNTIME_SETTINGS_PATH = Path(__file__).parent.parent / "data" / "runtime_settings.json"

    def _get_default_runtime_settings() -> dict:
        """기본 런타임 설정 반환 (.env 값 또는 하드코딩 기본값)"""
        return {
            # 크롤링 스케줄
            "crawl_full_enabled": True,
            "crawl_full_time": "06:00",
            "crawl_full_days": 30,  # 전체 스캔 만료 기간 (일)
            "crawl_week_enabled": True,
            "crawl_week_interval_hours": 3,
            "crawl_week_days": 7,  # 주간 스캔 만료 기간 (일)
            "crawl_day_enabled": True,
            "crawl_day_interval_minutes": 30,
            # 데이터 소스
            "use_expireddomains": settings.use_expireddomains,
            "use_alternative_sources": settings.use_alternative_sources,
            "alternative_sources": settings.alternative_sources,
            # 가용성 체크
            "check_availability": settings.check_availability,
            "availability_concurrency": 3,
            # 도메인 필터
            "min_domain_length": 3,
            "max_domain_length": 12,
            "allowed_tlds": "com,net,io,ai,co,kr",
            "allow_numbers": False,
            "allow_hyphens": False,
            # 알림 설정
            "min_score_alert": 70,
            "daily_report_time": "08:00",
            "heartbeat_interval_minutes": 0,
            # 시스템 정보
            "log_level": "INFO",
        }

    def _load_runtime_settings() -> dict:
        """런타임 설정 로드"""
        defaults = _get_default_runtime_settings()
        if RUNTIME_SETTINGS_PATH.exists():
            try:
                with open(RUNTIME_SETTINGS_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    # 기본값과 병합 (새로운 설정 항목이 추가되어도 대응)
                    defaults.update(saved)
            except Exception as e:
                logger.error("load_runtime_settings_failed", error=str(e))
        return defaults

    def _save_runtime_settings(settings_data: dict) -> bool:
        """런타임 설정 저장"""
        try:
            RUNTIME_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(RUNTIME_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("save_runtime_settings_failed", error=str(e))
            return False

    @app.get("/api/settings")
    async def get_runtime_settings():
        """런타임 설정 조회"""
        runtime = _load_runtime_settings()
        return {
            "success": True,
            "settings": runtime,
            # .env 기반 읽기 전용 설정
            "readonly": {
                "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
                "discord_configured": bool(settings.discord_webhook_url),
                "web_port": settings.web_port,
                "database_path": settings.database_path,
                "program_name": settings.program_name,
                "program_version": settings.program_version,
            }
        }

    @app.post("/api/settings")
    async def update_runtime_settings(
        # 크롤링 스케줄
        crawl_full_enabled: Optional[str] = Form(None),
        crawl_full_time: Optional[str] = Form(None),
        crawl_full_days: Optional[str] = Form(None),
        crawl_week_enabled: Optional[str] = Form(None),
        crawl_week_interval_hours: Optional[str] = Form(None),
        crawl_week_days: Optional[str] = Form(None),
        crawl_day_enabled: Optional[str] = Form(None),
        crawl_day_interval_minutes: Optional[str] = Form(None),
        # 데이터 소스
        use_expireddomains: Optional[str] = Form(None),
        use_alternative_sources: Optional[str] = Form(None),
        alternative_sources: Optional[str] = Form(None),
        # 가용성 체크
        check_availability: Optional[str] = Form(None),
        availability_concurrency: Optional[str] = Form(None),
        # 도메인 필터
        min_domain_length: Optional[str] = Form(None),
        max_domain_length: Optional[str] = Form(None),
        allowed_tlds: Optional[str] = Form(None),
        allow_numbers: Optional[str] = Form(None),
        allow_hyphens: Optional[str] = Form(None),
        # 알림 설정
        min_score_alert: Optional[str] = Form(None),
        daily_report_time: Optional[str] = Form(None),
        heartbeat_interval_minutes: Optional[str] = Form(None),
        # 시스템
        log_level: Optional[str] = Form(None),
    ):
        """런타임 설정 업데이트"""
        current = _load_runtime_settings()

        # 크롤링 스케줄 업데이트
        if crawl_full_enabled is not None:
            current["crawl_full_enabled"] = crawl_full_enabled == "true"
        if crawl_full_time is not None and crawl_full_time.strip():
            current["crawl_full_time"] = crawl_full_time.strip()
        if crawl_full_days is not None and crawl_full_days.strip():
            current["crawl_full_days"] = int(crawl_full_days)
        if crawl_week_enabled is not None:
            current["crawl_week_enabled"] = crawl_week_enabled == "true"
        if crawl_week_interval_hours is not None and crawl_week_interval_hours.strip():
            current["crawl_week_interval_hours"] = int(crawl_week_interval_hours)
        if crawl_week_days is not None and crawl_week_days.strip():
            current["crawl_week_days"] = int(crawl_week_days)
        if crawl_day_enabled is not None:
            current["crawl_day_enabled"] = crawl_day_enabled == "true"
        if crawl_day_interval_minutes is not None and crawl_day_interval_minutes.strip():
            current["crawl_day_interval_minutes"] = int(crawl_day_interval_minutes)

        # 데이터 소스 업데이트
        if use_expireddomains is not None:
            current["use_expireddomains"] = use_expireddomains == "true"
        if use_alternative_sources is not None:
            current["use_alternative_sources"] = use_alternative_sources == "true"
        if alternative_sources is not None:
            current["alternative_sources"] = alternative_sources.strip()

        # 가용성 체크 업데이트
        if check_availability is not None:
            current["check_availability"] = check_availability == "true"
        if availability_concurrency is not None and availability_concurrency.strip():
            current["availability_concurrency"] = max(1, min(5, int(availability_concurrency)))

        # 도메인 필터 업데이트
        if min_domain_length is not None and min_domain_length.strip():
            current["min_domain_length"] = int(min_domain_length)
        if max_domain_length is not None and max_domain_length.strip():
            current["max_domain_length"] = int(max_domain_length)
        if allowed_tlds is not None:
            current["allowed_tlds"] = allowed_tlds.strip()
        if allow_numbers is not None:
            current["allow_numbers"] = allow_numbers == "true"
        if allow_hyphens is not None:
            current["allow_hyphens"] = allow_hyphens == "true"

        # 알림 설정 업데이트
        if min_score_alert is not None and min_score_alert.strip():
            current["min_score_alert"] = int(min_score_alert)
        if daily_report_time is not None and daily_report_time.strip():
            current["daily_report_time"] = daily_report_time.strip()
        if heartbeat_interval_minutes is not None and heartbeat_interval_minutes.strip():
            current["heartbeat_interval_minutes"] = int(heartbeat_interval_minutes)

        # 시스템 설정 업데이트
        if log_level is not None and log_level.strip():
            current["log_level"] = log_level.strip().upper()

        if _save_runtime_settings(current):
            # 스케줄러 재설정 요청 (sniper 인스턴스가 있는 경우)
            if sniper is not None:
                try:
                    await sniper.reload_scheduler(current)
                except Exception as e:
                    logger.error("reload_scheduler_failed", error=str(e))

            return {"success": True, "message": "설정이 저장되었습니다.", "settings": current}
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "설정 저장에 실패했습니다."}
            )

    @app.post("/api/settings/reset")
    async def reset_runtime_settings():
        """런타임 설정 초기화"""
        defaults = _get_default_runtime_settings()
        if _save_runtime_settings(defaults):
            return {"success": True, "message": "설정이 초기화되었습니다.", "settings": defaults}
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "설정 초기화에 실패했습니다."}
            )

    logger.info("web_app_created")
    return app
