"""
Domain Sniper - 만료 도메인 크롤러
expireddomains.net 및 기타 소스에서 만료 도메인을 수집합니다.
"""

import asyncio
import random
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

from .parser import DomainParser
from config import settings

logger = structlog.get_logger()


class ExpiredDomainsCrawler:
    """만료 도메인 크롤러"""

    # expireddomains.net 기본 URL
    BASE_URL = "https://www.expireddomains.net"
    LOGIN_URL = "https://www.expireddomains.net/login/"

    # 검색 엔드포인트
    ENDPOINTS = {
        "deleted_com": "/domain-name-search/?q=&start=",
        "deleted_net": "/domain-name-search/?ftld[]=net&q=&start=",
        "deleted_io": "/domain-name-search/?ftld[]=io&q=&start=",
        "pending_delete": "/pendingdelete-domains/",
        "expired": "/expired-domains/",
    }

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.parser = DomainParser()
        self.logged_in = False

    async def __aenter__(self):
        await self.init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def init_client(self) -> None:
        """HTTP 클라이언트 초기화"""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout),
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            },
            follow_redirects=True,
        )
        logger.info("http_client_initialized")

        # 로그인 시도
        if settings.expired_domains_username and settings.expired_domains_password:
            await self._login()

    async def _login(self) -> bool:
        """ExpiredDomains.net 로그인"""
        try:
            # 로그인 페이지 먼저 방문 (쿠키 설정)
            login_page = await self.client.get(self.LOGIN_URL)

            # 로그인 요청 - ExpiredDomains.net 폼 필드명
            login_data = {
                "login": settings.expired_domains_username,
                "password": settings.expired_domains_password,
                "remember_me": "1",
            }

            response = await self.client.post(
                self.LOGIN_URL,
                data=login_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": self.LOGIN_URL,
                    "Origin": "https://www.expireddomains.net",
                }
            )

            # 로그인 성공 확인 방법들:
            # 1. 응답에 "logout" 링크가 있으면 성공
            # 2. 쿠키에 세션 정보가 있으면 성공
            # 3. 에러 메시지가 없으면 성공
            response_text = response.text.lower()

            # 로그인 실패 메시지 확인
            login_failed = (
                "invalid" in response_text or
                "incorrect" in response_text or
                "wrong" in response_text or
                "error" in response_text and "login" in response_text
            )

            # 로그인 성공 확인
            login_success = (
                "logout" in response_text or
                "my account" in response_text or
                "member" in response_text
            )

            # 쿠키 확인
            cookies = self.client.cookies
            has_session = any("sess" in name.lower() or "member" in name.lower() or "user" in name.lower()
                             for name in cookies.keys())

            if login_success or (has_session and not login_failed):
                self.logged_in = True
                logger.info("expireddomains_login_success", username=settings.expired_domains_username)
                return True
            else:
                logger.warning("expireddomains_login_failed",
                             username=settings.expired_domains_username,
                             has_session=has_session,
                             cookies=list(cookies.keys()))
                return False

        except Exception as e:
            logger.error("expireddomains_login_error", error=str(e))
            return False

    async def close(self) -> None:
        """클라이언트 종료"""
        if self.client:
            await self.client.aclose()
            logger.info("http_client_closed")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _fetch_page(self, url: str) -> str:
        """
        페이지 가져오기 (재시도 포함)

        Args:
            url: 요청 URL

        Returns:
            HTML 문자열
        """
        # 요청 간 딜레이 (서버 부하 방지)
        await asyncio.sleep(settings.request_delay + random.uniform(0, 1))

        response = await self.client.get(url)
        response.raise_for_status()

        logger.debug("page_fetched", url=url, status=response.status_code)
        return response.text

    async def crawl_expireddomains(
        self,
        tld: str = "com",
        days_until_expiry: int = 30,
        max_pages: int = 5
    ) -> List[Dict[str, Any]]:
        """
        expireddomains.net 크롤링

        Args:
            tld: 대상 TLD
            days_until_expiry: 만료 예정 일수
            max_pages: 최대 페이지 수

        Returns:
            도메인 정보 리스트
        """
        all_domains = []

        # TLD별 검색 파라미터
        params = {
            "fwhois": "22",  # WHOIS 가능
            "fbl": "0",  # 블랙리스트 제외
            "fstatuses[]": "1",  # 활성 상태
            "start": "0"
        }

        # TLD 필터
        if tld != "com":
            params["ftld[]"] = tld

        # 길이 필터
        params["fmaxchars"] = str(settings.max_domain_length)
        params["fminchars"] = str(settings.min_domain_length)

        # 하이픈/숫자 필터
        if not settings.allow_hyphens:
            params["fhyphens"] = "1"  # 하이픈 제외
        if not settings.allow_numbers:
            params["fnumbers"] = "1"  # 숫자 제외

        base_search_url = f"{self.BASE_URL}/expired-domains/"

        for page in range(max_pages):
            try:
                params["start"] = str(page * 25)
                url = f"{base_search_url}?{urlencode(params, doseq=True)}"

                logger.info("crawling_page", tld=tld, page=page + 1, url=url)

                html = await self._fetch_page(url)
                domains = self.parser.parse_expireddomains_html(html)

                if not domains:
                    logger.info("no_more_domains", page=page + 1)
                    break

                # 필터링 적용
                filtered = []
                for d in domains:
                    if self.parser.is_valid_domain(
                        d["name"],
                        d["tld"],
                        min_length=settings.min_domain_length,
                        max_length=settings.max_domain_length,
                        allowed_tlds=settings.tld_list,
                        allow_numbers=settings.allow_numbers,
                        allow_hyphens=settings.allow_hyphens
                    ):
                        # 만료일 필터
                        if d.get("expiry_date"):
                            days_left = (d["expiry_date"] - date.today()).days
                            if days_left <= days_until_expiry:
                                filtered.append(d)
                        else:
                            filtered.append(d)

                all_domains.extend(filtered)
                logger.info(
                    "page_crawled",
                    page=page + 1,
                    found=len(domains),
                    filtered=len(filtered)
                )

            except httpx.HTTPStatusError as e:
                logger.error("http_error", status=e.response.status_code, url=url)
                if e.response.status_code == 429:  # Rate limited
                    await asyncio.sleep(60)
                break
            except Exception as e:
                logger.error("crawl_error", error=str(e))
                break

        logger.info("crawl_completed", tld=tld, total=len(all_domains))
        return all_domains

    async def crawl_all_tlds(
        self,
        days_until_expiry: int = 30,
        max_pages_per_tld: int = 3
    ) -> List[Dict[str, Any]]:
        """
        모든 TLD 크롤링

        Args:
            days_until_expiry: 만료 예정 일수
            max_pages_per_tld: TLD당 최대 페이지 수

        Returns:
            도메인 정보 리스트
        """
        all_domains = []

        for tld in settings.tld_list:
            logger.info("crawling_tld", tld=tld)

            try:
                domains = await self.crawl_expireddomains(
                    tld=tld,
                    days_until_expiry=days_until_expiry,
                    max_pages=max_pages_per_tld
                )
                all_domains.extend(domains)

                # TLD 간 딜레이
                await asyncio.sleep(5)

            except Exception as e:
                logger.error("tld_crawl_error", tld=tld, error=str(e))
                continue

        return all_domains

    async def crawl_pending_delete(self, max_pages: int = 3) -> List[Dict[str, Any]]:
        """
        삭제 예정 도메인 크롤링 (1일 이내)

        Args:
            max_pages: 최대 페이지 수

        Returns:
            도메인 정보 리스트
        """
        all_domains = []

        params = {
            "fmaxchars": str(settings.max_domain_length),
            "fminchars": str(settings.min_domain_length),
        }

        if not settings.allow_hyphens:
            params["fhyphens"] = "1"
        if not settings.allow_numbers:
            params["fnumbers"] = "1"

        base_url = f"{self.BASE_URL}/pendingdelete-domains/"

        for page in range(max_pages):
            try:
                params["start"] = str(page * 25)
                url = f"{base_url}?{urlencode(params)}"

                html = await self._fetch_page(url)
                domains = self.parser.parse_expireddomains_html(html)

                if not domains:
                    break

                # 필터링
                filtered = []
                for d in domains:
                    if self.parser.is_valid_domain(
                        d["name"],
                        d["tld"],
                        min_length=settings.min_domain_length,
                        max_length=settings.max_domain_length,
                        allowed_tlds=settings.tld_list,
                        allow_numbers=settings.allow_numbers,
                        allow_hyphens=settings.allow_hyphens
                    ):
                        # 1일 이내 만료로 설정
                        d["expiry_date"] = date.today() + timedelta(days=1)
                        filtered.append(d)

                all_domains.extend(filtered)

            except Exception as e:
                logger.error("pending_delete_error", error=str(e))
                break

        return all_domains

    async def search_keyword(
        self,
        keyword: str,
        max_pages: int = 2
    ) -> List[Dict[str, Any]]:
        """
        키워드로 도메인 검색

        Args:
            keyword: 검색 키워드
            max_pages: 최대 페이지 수

        Returns:
            도메인 정보 리스트
        """
        all_domains = []

        params = {
            "q": keyword,
            "fmaxchars": str(settings.max_domain_length),
            "fminchars": str(settings.min_domain_length),
        }

        base_url = f"{self.BASE_URL}/domain-name-search/"

        for page in range(max_pages):
            try:
                params["start"] = str(page * 25)
                url = f"{base_url}?{urlencode(params)}"

                logger.info("keyword_search", keyword=keyword, page=page + 1)

                html = await self._fetch_page(url)
                domains = self.parser.parse_expireddomains_html(html)

                if not domains:
                    break

                # 필터링
                for d in domains:
                    if self.parser.is_valid_domain(
                        d["name"],
                        d["tld"],
                        min_length=settings.min_domain_length,
                        max_length=settings.max_domain_length,
                        allowed_tlds=settings.tld_list,
                        allow_numbers=settings.allow_numbers,
                        allow_hyphens=settings.allow_hyphens
                    ):
                        all_domains.append(d)

            except Exception as e:
                logger.error("keyword_search_error", keyword=keyword, error=str(e))
                break

        return all_domains


class MockCrawler:
    """
    테스트/개발용 목업 크롤러
    실제 API 호출 없이 샘플 데이터 반환
    """

    SAMPLE_DOMAINS = [
        {"name": "startup", "tld": "io", "length": 7, "expiry_date": date.today() + timedelta(days=2)},
        {"name": "cloud", "tld": "com", "length": 5, "expiry_date": date.today() + timedelta(days=5)},
        {"name": "crypto", "tld": "net", "length": 6, "expiry_date": date.today() + timedelta(days=1)},
        {"name": "tech", "tld": "co", "length": 4, "expiry_date": date.today() + timedelta(days=7)},
        {"name": "data", "tld": "io", "length": 4, "expiry_date": date.today() + timedelta(days=3)},
        {"name": "pixel", "tld": "com", "length": 5, "expiry_date": date.today() + timedelta(days=10)},
        {"name": "stream", "tld": "io", "length": 6, "expiry_date": date.today() + timedelta(days=4)},
        {"name": "core", "tld": "ai", "length": 4, "expiry_date": date.today() + timedelta(days=6)},
    ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def crawl_all_tlds(self, days_until_expiry: int = 30, max_pages_per_tld: int = 3):
        """목업 크롤링"""
        await asyncio.sleep(0.5)  # 시뮬레이션
        return [
            {**d, "full_name": f"{d['name']}.{d['tld']}", "source": "mock"}
            for d in self.SAMPLE_DOMAINS
            if (d["expiry_date"] - date.today()).days <= days_until_expiry
        ]

    async def crawl_pending_delete(self, max_pages: int = 3):
        """목업 삭제 예정 크롤링"""
        await asyncio.sleep(0.3)
        return [
            {**d, "full_name": f"{d['name']}.{d['tld']}", "source": "mock"}
            for d in self.SAMPLE_DOMAINS[:3]
        ]


# 테스트
if __name__ == "__main__":
    async def test():
        # 목업 크롤러 테스트
        async with MockCrawler() as crawler:
            domains = await crawler.crawl_all_tlds(days_until_expiry=7)
            print(f"Found {len(domains)} domains:")
            for d in domains:
                print(f"  - {d['full_name']} (expires in {(d['expiry_date'] - date.today()).days} days)")

    asyncio.run(test())
