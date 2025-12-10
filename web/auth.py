"""
Domain Sniper - 웹 인증 모듈
HTTP Basic Auth 및 세션 기반 인증을 제공합니다.
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from functools import wraps

from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import RedirectResponse
import structlog

from config import settings

logger = structlog.get_logger()


# HTTP Basic Auth 보안 스키마
security = HTTPBasic(auto_error=False)


class AuthConfig:
    """인증 설정"""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        enabled: bool = True,
        session_timeout: int = 3600,  # 세션 타임아웃 (초)
        max_failed_attempts: int = 5,  # 최대 실패 시도
        lockout_duration: int = 300,   # 잠금 시간 (초)
    ):
        # 환경변수에서 읽거나 기본값 사용
        self.username = username or getattr(settings, 'web_username', None) or 'admin'
        self.password = password or getattr(settings, 'web_password', None) or ''
        self.enabled = enabled and bool(self.password)  # 비밀번호가 있어야 활성화
        self.session_timeout = session_timeout
        self.max_failed_attempts = max_failed_attempts
        self.lockout_duration = lockout_duration


class SessionStore:
    """세션 저장소 (메모리 기반)"""

    def __init__(self):
        self._sessions: Dict[str, Dict] = {}
        self._failed_attempts: Dict[str, Tuple[int, datetime]] = {}

    def create_session(self, username: str) -> str:
        """새 세션 생성"""
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = {
            "username": username,
            "created_at": datetime.now(),
            "last_access": datetime.now(),
        }
        logger.info("session_created", username=username)
        return session_id

    def validate_session(self, session_id: str, timeout: int = 3600) -> Optional[str]:
        """
        세션 유효성 검사

        Returns:
            유효하면 username, 아니면 None
        """
        if session_id not in self._sessions:
            return None

        session = self._sessions[session_id]
        elapsed = (datetime.now() - session["last_access"]).total_seconds()

        if elapsed > timeout:
            self.invalidate_session(session_id)
            return None

        # 마지막 접근 시간 업데이트
        session["last_access"] = datetime.now()
        return session["username"]

    def invalidate_session(self, session_id: str) -> None:
        """세션 무효화"""
        if session_id in self._sessions:
            username = self._sessions[session_id].get("username")
            del self._sessions[session_id]
            logger.info("session_invalidated", username=username)

    def cleanup_expired(self, timeout: int = 3600) -> int:
        """만료된 세션 정리"""
        now = datetime.now()
        expired = [
            sid for sid, session in self._sessions.items()
            if (now - session["last_access"]).total_seconds() > timeout
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def record_failed_attempt(self, ip: str) -> int:
        """실패 시도 기록"""
        if ip in self._failed_attempts:
            count, _ = self._failed_attempts[ip]
            count += 1
        else:
            count = 1

        self._failed_attempts[ip] = (count, datetime.now())
        return count

    def is_locked_out(self, ip: str, max_attempts: int, lockout_duration: int) -> bool:
        """잠금 상태 확인"""
        if ip not in self._failed_attempts:
            return False

        count, last_attempt = self._failed_attempts[ip]
        elapsed = (datetime.now() - last_attempt).total_seconds()

        # 잠금 시간 경과 시 리셋
        if elapsed > lockout_duration:
            del self._failed_attempts[ip]
            return False

        return count >= max_attempts

    def reset_failed_attempts(self, ip: str) -> None:
        """실패 시도 리셋"""
        if ip in self._failed_attempts:
            del self._failed_attempts[ip]


# 전역 세션 저장소
session_store = SessionStore()

# 기본 인증 설정
auth_config = AuthConfig()


def get_client_ip(request: Request) -> str:
    """클라이언트 IP 주소 가져오기"""
    # 프록시 뒤에 있는 경우
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def verify_credentials(username: str, password: str, config: AuthConfig = None) -> bool:
    """
    자격 증명 확인 (타이밍 공격 방지)

    Args:
        username: 사용자명
        password: 비밀번호
        config: 인증 설정

    Returns:
        인증 성공 여부
    """
    config = config or auth_config

    # 타이밍 공격 방지를 위해 상수 시간 비교
    username_correct = secrets.compare_digest(
        username.encode("utf-8"),
        config.username.encode("utf-8")
    )
    password_correct = secrets.compare_digest(
        password.encode("utf-8"),
        config.password.encode("utf-8")
    )

    return username_correct and password_correct


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security)
) -> Optional[str]:
    """
    현재 인증된 사용자 가져오기

    Returns:
        사용자명 또는 None
    """
    if not auth_config.enabled:
        return "anonymous"

    client_ip = get_client_ip(request)

    # 잠금 상태 확인
    if session_store.is_locked_out(
        client_ip,
        auth_config.max_failed_attempts,
        auth_config.lockout_duration
    ):
        logger.warning("auth_locked_out", ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please try again later."
        )

    # 세션 쿠키 확인
    session_id = request.cookies.get("session_id")
    if session_id:
        username = session_store.validate_session(session_id, auth_config.session_timeout)
        if username:
            return username

    # HTTP Basic Auth 확인
    if credentials:
        if verify_credentials(credentials.username, credentials.password):
            session_store.reset_failed_attempts(client_ip)
            return credentials.username
        else:
            count = session_store.record_failed_attempt(client_ip)
            logger.warning("auth_failed", ip=client_ip, attempts=count)

    return None


async def require_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security)
) -> str:
    """
    인증 필수 의존성

    Returns:
        인증된 사용자명

    Raises:
        HTTPException: 인증 실패 시
    """
    user = await get_current_user(request, credentials)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    return user


def login_required(func):
    """인증 필수 데코레이터 (라우트용)"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not auth_config.enabled:
            return await func(request, *args, **kwargs)

        user = await get_current_user(request)
        if user is None:
            # 로그인 페이지로 리다이렉트 또는 401 반환
            if request.headers.get("Accept", "").startswith("text/html"):
                return RedirectResponse(url="/login", status_code=302)
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Basic"},
                )

        request.state.user = user
        return await func(request, *args, **kwargs)

    return wrapper


def api_auth_required(func):
    """API 인증 필수 데코레이터"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not auth_config.enabled:
            return await func(request, *args, **kwargs)

        user = await get_current_user(request)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API authentication required",
                headers={"WWW-Authenticate": "Basic"},
            )

        request.state.user = user
        return await func(request, *args, **kwargs)

    return wrapper


class AuthMiddleware:
    """인증 미들웨어"""

    def __init__(
        self,
        app,
        config: AuthConfig = None,
        exclude_paths: list = None
    ):
        self.app = app
        self.config = config or auth_config
        self.exclude_paths = exclude_paths or [
            "/login",
            "/logout",
            "/health",
            "/static",
            "/favicon.ico",
        ]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # 제외 경로 확인
        for exclude in self.exclude_paths:
            if path.startswith(exclude):
                await self.app(scope, receive, send)
                return

        # 인증 비활성화 시 통과
        if not self.config.enabled:
            await self.app(scope, receive, send)
            return

        await self.app(scope, receive, send)


def create_auth_routes(app):
    """인증 관련 라우트 추가"""
    from fastapi import Form
    from fastapi.responses import HTMLResponse

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, error: str = None):
        """로그인 페이지"""
        if not auth_config.enabled:
            return RedirectResponse(url="/", status_code=302)

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Login - Domain Sniper</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }}
        .login-card {{ max-width: 400px; margin: 100px auto; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card login-card shadow">
            <div class="card-body p-5">
                <h3 class="text-center mb-4">🎯 Domain Sniper</h3>
                <p class="text-center text-muted mb-4">로그인이 필요합니다</p>

                {"<div class='alert alert-danger'>"+error+"</div>" if error else ""}

                <form method="post" action="/login">
                    <div class="mb-3">
                        <label class="form-label">사용자명</label>
                        <input type="text" name="username" class="form-control" required autofocus>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">비밀번호</label>
                        <input type="password" name="password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">로그인</button>
                </form>
            </div>
        </div>
    </div>
</body>
</html>
"""
        return HTMLResponse(content=html)

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...)
    ):
        """로그인 처리"""
        client_ip = get_client_ip(request)

        # 잠금 확인
        if session_store.is_locked_out(
            client_ip,
            auth_config.max_failed_attempts,
            auth_config.lockout_duration
        ):
            return RedirectResponse(
                url="/login?error=Too+many+attempts.+Please+wait.",
                status_code=302
            )

        # 인증 확인
        if verify_credentials(username, password):
            session_store.reset_failed_attempts(client_ip)
            session_id = session_store.create_session(username)

            response = RedirectResponse(url="/", status_code=302)
            response.set_cookie(
                key="session_id",
                value=session_id,
                max_age=auth_config.session_timeout,
                httponly=True,
                samesite="lax"
            )
            logger.info("login_success", username=username, ip=client_ip)
            return response
        else:
            count = session_store.record_failed_attempt(client_ip)
            logger.warning("login_failed", username=username, ip=client_ip, attempts=count)
            return RedirectResponse(
                url="/login?error=Invalid+credentials",
                status_code=302
            )

    @app.get("/logout")
    async def logout(request: Request):
        """로그아웃"""
        session_id = request.cookies.get("session_id")
        if session_id:
            session_store.invalidate_session(session_id)

        response = RedirectResponse(url="/login", status_code=302)
        response.delete_cookie("session_id")
        return response

    @app.get("/health")
    async def health_check():
        """헬스 체크 (인증 불필요)"""
        return {"status": "ok"}

    logger.info("auth_routes_registered")


# 설정 함수
def configure_auth(
    username: str = None,
    password: str = None,
    enabled: bool = True
):
    """인증 설정 구성"""
    global auth_config
    auth_config = AuthConfig(
        username=username,
        password=password,
        enabled=enabled
    )
    logger.info(
        "auth_configured",
        enabled=auth_config.enabled,
        username=auth_config.username if auth_config.enabled else None
    )


# 테스트
if __name__ == "__main__":
    print("=== Web Auth Module Test ===")

    # 설정 테스트
    configure_auth(username="admin", password="secret123", enabled=True)
    print(f"Auth enabled: {auth_config.enabled}")
    print(f"Username: {auth_config.username}")

    # 자격 증명 확인 테스트
    print(f"\nCredential test (correct): {verify_credentials('admin', 'secret123')}")
    print(f"Credential test (wrong): {verify_credentials('admin', 'wrong')}")

    # 세션 테스트
    session_id = session_store.create_session("admin")
    print(f"\nSession created: {session_id[:20]}...")
    print(f"Session valid: {session_store.validate_session(session_id) is not None}")

    session_store.invalidate_session(session_id)
    print(f"Session after invalidate: {session_store.validate_session(session_id)}")
