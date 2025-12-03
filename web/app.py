"""
Domain Sniper - 웹 대시보드
FastAPI + Jinja2 경량 웹 인터페이스
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import structlog

from database.models import Database
from config import settings

logger = structlog.get_logger()

# 템플릿 디렉토리
TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app(db: Database) -> FastAPI:
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
    async def index(request: Request, page: int = 1, min_score: Optional[int] = None):
        """메인 페이지 - 도메인 목록"""
        per_page = 20
        offset = (page - 1) * per_page

        # 도메인 조회
        domains = await db.get_domains(
            limit=per_page,
            offset=offset,
            min_score=min_score,
            order_by="total_score DESC, expiry_date ASC"
        )

        # 통계
        stats = await db.get_domain_stats()

        return templates.TemplateResponse("index.html", {
            "request": request,
            "domains": domains,
            "stats": stats,
            "page": page,
            "min_score": min_score,
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

    logger.info("web_app_created")
    return app
