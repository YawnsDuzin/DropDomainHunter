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
    MEMBER_URL = "https://member.expireddomains.net"  # 로그인 후 사용하는 멤버 영역
    LOGIN_URL = "https://www.expireddomains.net/login/"
    LOGIN_CHECK_URL = "https://www.expireddomains.net/logincheck/"  # 폼 제출 URL

    # 검색 엔드포인트 (멤버 영역)
    # TLD별 삭제된 도메인 리스트
    TLD_ENDPOINTS = {
        "com": "/domains/expiredcom/",
        "net": "/domains/expirednet/",
        "org": "/domains/expiredorg/",
        "io": "/domains/expiredio/",
        "ai": "/domains/expiredai/",
        "co": "/domains/expiredco/",
        "kr": "/domains/expiredkr/",
        "info": "/domains/expiredinfo/",
        "biz": "/domains/expiredbiz/",
    }

    # 기타 엔드포인트
    ENDPOINTS = {
        "deleted_combined": "/domains/combinedexpired/",  # 모든 TLD 삭제 도메인
        "pending_delete": "/domains/pendingdelete/",
        "domain_search": "/domain-name-search/",
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
        # 쿠키 저장소 명시적 설정
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.http_timeout),
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=True,
            cookies=httpx.Cookies(),  # 쿠키 저장소 명시
        )
        logger.info("http_client_initialized")

        # 로그인 시도
        if settings.expired_domains_username and settings.expired_domains_password:
            await self._login()

    async def _login(self) -> bool:
        """ExpiredDomains.net 로그인"""
        try:
            # 로그인 페이지 먼저 방문 (쿠키 설정)
            logger.info("visiting_login_page")
            login_page = await self.client.get(self.LOGIN_URL)

            # 현재 쿠키 상태 로깅
            logger.info("cookies_after_login_page", cookies=list(self.client.cookies.keys()))

            # BeautifulSoup으로 폼 필드 추출
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(login_page.text, "lxml")
            form = soup.find("form", {"method": "post"})

            # 폼 필드 동적 추출
            login_data = {}
            if form:
                for inp in form.find_all("input"):
                    name = inp.get("name")
                    if not name:
                        continue
                    input_type = inp.get("type", "text")
                    if input_type == "hidden":
                        login_data[name] = inp.get("value", "")
                    elif "user" in name.lower() or "login" in name.lower() or "email" in name.lower():
                        login_data[name] = settings.expired_domains_username
                    elif "pass" in name.lower():
                        login_data[name] = settings.expired_domains_password
                    elif "remember" in name.lower():
                        login_data[name] = "1"

            # 폼을 찾지 못한 경우 기본값 사용
            if not login_data or len(login_data) < 2:
                login_data = {
                    "login": settings.expired_domains_username,
                    "password": settings.expired_domains_password,
                    "rememberme": "1",
                }

            logger.info("login_form_data", fields=list(login_data.keys()))

            # 폼 action에서 실제 로그인 체크 URL 추출
            login_action_url = self.LOGIN_CHECK_URL
            if form:
                action = form.get("action")
                if action:
                    if action.startswith("/"):
                        login_action_url = f"{self.BASE_URL}{action}"
                    elif action.startswith("http"):
                        login_action_url = action
                    logger.info("login_form_action", action=action, url=login_action_url)

            # 로그인 POST 요청 - follow_redirects=False로 설정하여 리다이렉트 수동 처리
            response = await self.client.post(
                login_action_url,
                data=login_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": self.LOGIN_URL,
                    "Origin": "https://www.expireddomains.net",
                },
                follow_redirects=False  # 리다이렉트 수동 처리
            )

            logger.info("login_response",
                       status=response.status_code,
                       cookies=list(self.client.cookies.keys()),
                       location=response.headers.get("location", ""))

            # 리다이렉트 처리 (302/303 응답)
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_url = response.headers.get("location", "")
                if redirect_url:
                    if redirect_url.startswith("/"):
                        redirect_url = f"{self.BASE_URL}{redirect_url}"
                    logger.info("following_redirect", url=redirect_url)
                    await asyncio.sleep(0.5)
                    response = await self.client.get(redirect_url)

            # 로그인 성공 확인
            response_text = response.text.lower()

            # 쿠키 확인 - ExpiredDomains는 PHPSESSID 사용
            cookies = self.client.cookies
            cookie_names = list(cookies.keys())
            has_session = any("php" in name.lower() or "sess" in name.lower() or "ed" in name.lower()
                             for name in cookie_names)

            logger.info("login_check",
                       has_session=has_session,
                       cookies=cookie_names,
                       has_logout="logout" in response_text,
                       has_login_form="inputlogin" in response_text or "inputpassword" in response_text)

            # 로그인 실패 메시지 확인
            login_failed = (
                "invalid" in response_text or
                "incorrect" in response_text or
                "wrong password" in response_text or
                "accountdeactivated" in str(response.url).lower() or
                "accountdeactivated" in response_text or
                "deactivated" in response_text
            )

            # 계정 비활성화 확인
            if "accountdeactivated" in str(response.url).lower():
                logger.error("account_deactivated",
                           username=settings.expired_domains_username,
                           message="ExpiredDomains.net 계정이 비활성화되었습니다. 웹사이트에서 확인하세요.")
                self.logged_in = False
                return False

            # 로그인 성공 확인 - username이 페이지에 표시되거나 logout 링크가 있으면 성공
            login_success = (
                "logout" in response_text or
                settings.expired_domains_username.lower() in response_text or
                "my account" in response_text or
                "deleted domains" in response_text  # 메인 페이지로 리다이렉트된 경우
            )

            if login_success or (has_session and not login_failed):
                self.logged_in = True
                logger.info("expireddomains_login_success",
                           username=settings.expired_domains_username,
                           cookies=cookie_names)

                # 로그인 후 멤버 영역 페이지 방문해서 세션 확인
                await asyncio.sleep(1)
                test_page = await self.client.get(
                    f"{self.MEMBER_URL}/",
                    headers={"Referer": self.BASE_URL}
                )

                # 디버그용 저장
                try:
                    import tempfile
                    import os
                    debug_dir = tempfile.gettempdir()
                    debug_file = os.path.join(debug_dir, "expireddomains_after_login.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(test_page.text)
                    logger.info("debug_html_saved", file=debug_file)
                except Exception:
                    pass

                test_text = test_page.text.lower()
                if "logout" in test_text or settings.expired_domains_username.lower() in test_text:
                    logger.info("session_verified_on_member_area")
                    return True
                elif "login to see" in test_text or "please login" in test_text:
                    # 세션이 유지되지 않음 - 다시 로그인 시도
                    logger.warning("session_lost_after_redirect",
                                  cookies=list(self.client.cookies.keys()))
                    # 페이지에서 다시 로그인 시도
                    return await self._retry_login_on_page(test_page.text)
                else:
                    logger.info("session_check_inconclusive")
                    return True

            else:
                logger.warning("expireddomains_login_failed",
                             username=settings.expired_domains_username,
                             has_session=has_session,
                             cookies=cookie_names,
                             login_failed=login_failed)
                return False

        except Exception as e:
            logger.error("expireddomains_login_error", error=str(e), exc_info=True)
            return False

    async def _retry_login_on_page(self, page_html: str) -> bool:
        """페이지 내 로그인 폼으로 재로그인 시도"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page_html, "lxml")
            form = soup.find("form", {"method": "post"})

            if not form:
                logger.warning("no_login_form_found_on_page")
                return False

            action = form.get("action", "/logincheck/")
            if action.startswith("/"):
                action = f"{self.BASE_URL}{action}"

            login_data = {
                "login": settings.expired_domains_username,
                "password": settings.expired_domains_password,
                "rememberme": "1",
            }

            # hidden 필드 추가
            for inp in form.find_all("input", {"type": "hidden"}):
                name = inp.get("name")
                if name:
                    login_data[name] = inp.get("value", "")

            response = await self.client.post(
                action,
                data=login_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"{self.BASE_URL}/expired-domains/",
                },
                follow_redirects=True
            )

            if "logout" in response.text.lower():
                logger.info("retry_login_success")
                self.logged_in = True
                return True
            else:
                logger.warning("retry_login_failed")
                return False

        except Exception as e:
            logger.error("retry_login_error", error=str(e))
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

        # Referer 결정 - member URL이면 member Referer 사용
        if "member.expireddomains.net" in url:
            referer = self.MEMBER_URL
        else:
            referer = self.BASE_URL

        response = await self.client.get(
            url,
            headers={"Referer": referer}
        )
        response.raise_for_status()

        # 세션 만료 확인 - 로그인 페이지로 리다이렉트되거나 로그인 필요 메시지가 있으면 재로그인
        response_text = response.text.lower()
        final_url = str(response.url)

        # 세션 만료 조건 확인
        session_expired = (
            ("login to see" in response_text or "please login" in response_text) or
            ("/login" in final_url and "member.expireddomains.net" not in final_url) or
            ("accountdeactivated" in final_url or "accountdeactivated" in response_text)
        )

        if session_expired and self.logged_in:
            logger.warning("session_expired_during_fetch", url=url, final_url=final_url)
            self.logged_in = False  # 세션 상태 초기화

            # 재로그인 전 대기 (rate limit 방지)
            await asyncio.sleep(3)

            # 재로그인 시도
            if await self._login():
                # 재로그인 성공 시 페이지 다시 요청
                await asyncio.sleep(2)
                response = await self.client.get(
                    url,
                    headers={"Referer": referer}
                )
                response.raise_for_status()
            else:
                logger.error("relogin_failed", url=url)
                raise Exception("세션 만료 및 재로그인 실패")

        logger.debug("page_fetched", url=url, status=response.status_code)
        return response.text

    async def crawl_expireddomains(
        self,
        tld: str = "com",
        days_until_expiry: int = 30,
        max_pages: int = 5
    ) -> List[Dict[str, Any]]:
        """
        expireddomains.net 크롤링 (멤버 영역 사용)

        Args:
            tld: 대상 TLD
            days_until_expiry: 만료 예정 일수
            max_pages: 최대 페이지 수

        Returns:
            도메인 정보 리스트
        """
        all_domains = []

        # TLD별 엔드포인트 결정
        tld_lower = tld.lower()
        if tld_lower in self.TLD_ENDPOINTS:
            endpoint = self.TLD_ENDPOINTS[tld_lower]
        else:
            # 지원되지 않는 TLD는 combined 리스트 사용
            endpoint = self.ENDPOINTS["deleted_combined"]

        # 필터 파라미터
        params = {}

        # 길이 필터
        params["fmaxchars"] = str(settings.max_domain_length)
        params["fminchars"] = str(settings.min_domain_length)

        # 하이픈/숫자 필터
        if not settings.allow_hyphens:
            params["fhyphens"] = "1"  # 하이픈 제외
        if not settings.allow_numbers:
            params["fnumbers"] = "1"  # 숫자 제외

        # TLD 필터 (combined 리스트 사용 시)
        if endpoint == self.ENDPOINTS["deleted_combined"] and tld_lower != "all":
            params["ftld[]"] = tld_lower

        # 멤버 영역 URL 사용
        base_search_url = f"{self.MEMBER_URL}{endpoint}"

        for page in range(max_pages):
            try:
                params["start"] = str(page * 25)
                url = f"{base_search_url}?{urlencode(params, doseq=True)}"

                logger.info("crawling_page", tld=tld, page=page + 1, url=url)

                html = await self._fetch_page(url)

                # 디버그: 첫 페이지 HTML 저장 (문제 진단용)
                if page == 0:
                    try:
                        debug_file = f"/tmp/expireddomains_debug_{tld}.html"
                        with open(debug_file, "w", encoding="utf-8") as f:
                            f.write(html)
                        logger.info("debug_html_saved", file=debug_file)
                    except Exception as e:
                        logger.warning("debug_html_save_failed", error=str(e))

                page_domains = self.parser.parse_expireddomains_html(html)

                if not page_domains:
                    logger.info("no_more_domains", page=page + 1)
                    break

                # 필터링 적용
                filtered = []
                for d in page_domains:
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
                    found=len(page_domains),
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

                # TLD 간 딜레이 (rate limit 방지를 위해 충분한 대기 시간)
                await asyncio.sleep(10)

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

        # 멤버 영역 URL 사용
        base_url = f"{self.MEMBER_URL}{self.ENDPOINTS['pending_delete']}"

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
