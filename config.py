"""
Domain Sniper - 설정 모듈
환경 변수를 로드하고 애플리케이션 설정을 관리합니다.
"""

from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # ----- 프로그램 정보 -----
    program_name: str = Field(default="Domain Sniper", description="프로그램 이름")
    program_version: str = Field(default="1.0.0", description="프로그램 버전")

    # ----- Telegram 설정 -----
    telegram_bot_token: str = Field(default="", description="Telegram Bot API 토큰")
    telegram_chat_id: str = Field(default="", description="Telegram 채팅방 ID")

    # ----- Discord 설정 -----
    discord_webhook_url: str = Field(default="", description="Discord Webhook URL")

    # ----- ExpiredDomains.net 로그인 -----
    expired_domains_username: str = Field(default="", description="ExpiredDomains.net 사용자명")
    expired_domains_password: str = Field(default="", description="ExpiredDomains.net 비밀번호")

    # ----- 크롤링 설정 -----
    crawl_full_interval_hours: int = Field(default=24, description="전체 스캔 주기 (시간)")
    crawl_week_interval_hours: int = Field(default=3, description="7일 이내 스캔 주기 (시간)")
    crawl_day_interval_minutes: int = Field(default=30, description="1일 이내 스캔 주기 (분)")

    # ----- 데이터 소스 설정 -----
    use_expireddomains: bool = Field(default=True, description="ExpiredDomains.net 사용")
    use_alternative_sources: bool = Field(default=True, description="대체 소스 사용")
    alternative_sources: str = Field(
        default="snapnames,estibot",
        description="사용할 대체 소스 (쉼표로 구분)"
    )

    # ----- 도메인 필터 -----
    min_domain_length: int = Field(default=3, description="최소 도메인 길이")
    max_domain_length: int = Field(default=12, description="최대 도메인 길이")
    allowed_tlds: str = Field(default="com,net,io,co,kr", description="허용 TLD")
    allow_numbers: bool = Field(default=False, description="숫자 포함 허용")
    allow_hyphens: bool = Field(default=False, description="하이픈 포함 허용")

    # ----- 알림 설정 -----
    min_score_alert: int = Field(default=70, description="알림 최소 점수")
    daily_report_time: str = Field(default="08:00", description="일일 리포트 시간")
    heartbeat_interval_minutes: int = Field(default=0, description="하트비트 간격 (분)")

    # ----- 웹 대시보드 설정 -----
    web_enabled: bool = Field(default=True, description="웹 대시보드 활성화")
    web_port: int = Field(default=8000, description="웹 포트")
    web_host: str = Field(default="0.0.0.0", description="웹 호스트")
    web_username: str = Field(default="admin", description="웹 로그인 사용자명")
    web_password: str = Field(default="", description="웹 로그인 비밀번호 (비어있으면 인증 비활성화)")

    # ----- 프록시 설정 -----
    use_proxy: bool = Field(default=False, description="프록시 사용 여부")
    proxy_list: str = Field(default="", description="프록시 목록 (쉼표로 구분)")

    # ----- 도메인 확인 설정 -----
    check_availability: bool = Field(default=True, description="도메인 가용성 자동 확인")
    check_history: bool = Field(default=True, description="도메인 히스토리 자동 확인")

    # ----- 데이터베이스 설정 -----
    database_path: str = Field(default="domains.db", description="DB 파일 경로")

    # ----- 로깅 설정 -----
    log_level: str = Field(default="INFO", description="로그 레벨")
    log_file_path: str = Field(default="logs/domain-sniper.log", description="로그 파일 경로")

    # ----- HTTP 설정 -----
    http_timeout: int = Field(default=30, description="HTTP 타임아웃 (초)")
    http_retry_count: int = Field(default=3, description="HTTP 재시도 횟수")
    request_delay: float = Field(default=2.0, description="요청 간 딜레이 (초)")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="User-Agent"
    )

    @property
    def tld_list(self) -> List[str]:
        """TLD 목록 반환"""
        return [tld.strip().lower() for tld in self.allowed_tlds.split(",")]

    @property
    def database_full_path(self) -> Path:
        """데이터베이스 전체 경로"""
        return Path(__file__).parent / self.database_path

    @property
    def log_full_path(self) -> Optional[Path]:
        """로그 파일 전체 경로"""
        if not self.log_file_path:
            return None
        return Path(__file__).parent / self.log_file_path

    @property
    def daily_report_hour(self) -> int:
        """일일 리포트 시간 (시)"""
        return int(self.daily_report_time.split(":")[0])

    @property
    def daily_report_minute(self) -> int:
        """일일 리포트 시간 (분)"""
        return int(self.daily_report_time.split(":")[1])

    @property
    def alternative_sources_list(self) -> List[str]:
        """대체 소스 목록 반환"""
        return [s.strip().lower() for s in self.alternative_sources.split(",") if s.strip()]

    @property
    def proxy_list_items(self) -> List[str]:
        """프록시 목록 반환"""
        return [p.strip() for p in self.proxy_list.split(",") if p.strip()]

    @property
    def web_auth_enabled(self) -> bool:
        """웹 인증 활성화 여부"""
        return bool(self.web_password)

    @property
    def program_full_name(self) -> str:
        """프로그램 전체 이름 (이름/버전)"""
        return f"{self.program_name} v{self.program_version}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 전역 설정 인스턴스
settings = Settings()


# 상수 정의
ADULT_KEYWORDS = [
    "porn", "xxx", "sex", "adult", "nude", "naked", "pussy", "cock",
    "fuck", "shit", "ass", "bitch", "damn", "cunt", "dick", "horny",
    "casino", "gambling", "bet", "poker", "slot"
]

HIGH_VALUE_TLDS = {
    "com": 1.0,
    "net": 0.7,
    "io": 0.9,
    "co": 0.8,
    "kr": 0.6,
    "org": 0.6,
    "ai": 0.95,
    "app": 0.8,
    "dev": 0.85,
}


def validate_settings() -> List[str]:
    """설정 검증 및 경고 메시지 반환"""
    warnings = []

    if not settings.telegram_bot_token:
        warnings.append("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다. Telegram 알림이 비활성화됩니다.")

    if not settings.telegram_chat_id:
        warnings.append("TELEGRAM_CHAT_ID가 설정되지 않았습니다. Telegram 알림이 비활성화됩니다.")

    if settings.min_score_alert < 0 or settings.min_score_alert > 100:
        warnings.append("MIN_SCORE_ALERT는 0-100 사이여야 합니다.")

    if settings.min_domain_length < 1:
        warnings.append("MIN_DOMAIN_LENGTH는 1 이상이어야 합니다.")

    return warnings


if __name__ == "__main__":
    # 설정 테스트
    print("=== Domain Sniper 설정 ===")
    print(f"Telegram Token: {'설정됨' if settings.telegram_bot_token else '미설정'}")
    print(f"Discord Webhook: {'설정됨' if settings.discord_webhook_url else '미설정'}")
    print(f"TLD 목록: {settings.tld_list}")
    print(f"웹 대시보드: {'활성화' if settings.web_enabled else '비활성화'} (:{settings.web_port})")
    print(f"DB 경로: {settings.database_full_path}")

    warnings = validate_settings()
    if warnings:
        print("\n⚠️  경고:")
        for w in warnings:
            print(f"  - {w}")
