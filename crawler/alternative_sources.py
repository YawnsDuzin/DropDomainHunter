"""
Domain Sniper - 대체 데이터 소스 크롤러
ExpiredDomains.net 외의 무료 데이터 소스에서 만료 도메인을 수집합니다.

지원하는 소스:
- DesktopCatcher: COM/NET/ORG PendingDelete 리스트
- EstiBot: Verisign PendingDelete 원본 리스트
- SnapNames: 삭제 예정 도메인 CSV
- Dynadot: 백오더 도메인 CSV
"""

import asyncio
import csv
import io
import random
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import structlog

from .parser import DomainParser
from config import settings

logger = structlog.get_logger()


class AlternativeSourcesCrawler:
    """대체 소스 크롤러 - 여러 무료 데이터 소스 통합"""

    # 데이터 소스 URL
    SOURCES = {
        "estibot": {
            "name": "EstiBot",
            "url": "https://www.estibot.com/drops",
            "type": "html",
            "description": "Verisign PendingDelete 원본 리스트",
        },
        "snapnames": {
            "name": "SnapNames",
            "url": "https://www.snapnames.com/file_dl.sn?file=deletinglist.csv",
            "type": "csv",
            "description": "삭제 예정 도메인 CSV",
        },
        "dynadot": {
            "name": "Dynadot",
            "url": "https://www.dynadot.com/market/backorder/backorders.csv",
            "type": "csv",
            "description": "백오더 도메인 CSV",
        },
        "namejet": {
            "name": "NameJet",
            "url": "https://www.namejet.com/download/",
            "type": "html",
            "description": "도메인 리스트 다운로드",
        },
    }

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.parser = DomainParser()

    async def __aenter__(self):
        await self.init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def init_client(self) -> None:
        """HTTP 클라이언트 초기화"""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            follow_redirects=True,
        )
        logger.info("alternative_sources_client_initialized")

    async def close(self) -> None:
        """클라이언트 종료"""
        if self.client:
            await self.client.aclose()
            logger.info("alternative_sources_client_closed")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _fetch(self, url: str) -> str:
        """URL에서 데이터 가져오기"""
        await asyncio.sleep(random.uniform(1, 3))  # Rate limit 방지
        response = await self.client.get(url)
        response.raise_for_status()
        return response.text

    async def _fetch_binary(self, url: str) -> bytes:
        """바이너리 데이터 가져오기"""
        await asyncio.sleep(random.uniform(1, 3))
        response = await self.client.get(url)
        response.raise_for_status()
        return response.content

    def _filter_domain(self, name: str, tld: str) -> bool:
        """도메인 필터링"""
        return self.parser.is_valid_domain(
            name,
            tld,
            min_length=settings.min_domain_length,
            max_length=settings.max_domain_length,
            allowed_tlds=settings.tld_list,
            allow_numbers=settings.allow_numbers,
            allow_hyphens=settings.allow_hyphens
        )

    async def crawl_snapnames(self) -> List[Dict[str, Any]]:
        """
        SnapNames 삭제 예정 도메인 크롤링

        Returns:
            도메인 정보 리스트
        """
        domains = []

        try:
            logger.info("crawling_snapnames")
            content = await self._fetch(self.SOURCES["snapnames"]["url"])

            # CSV 파싱
            reader = csv.reader(io.StringIO(content))
            for row in reader:
                if not row or len(row) < 1:
                    continue

                full_domain = row[0].strip().lower()
                if not full_domain or "." not in full_domain:
                    continue

                # 도메인 파싱
                parts = full_domain.rsplit(".", 1)
                if len(parts) != 2:
                    continue

                name, tld = parts[0], parts[1]

                # 필터링
                if not self._filter_domain(name, tld):
                    continue

                # 만료일 추출 (있는 경우)
                expiry_date = date.today() + timedelta(days=5)  # 기본값
                if len(row) > 1:
                    try:
                        # 날짜 형식 파싱 시도
                        date_str = row[1].strip()
                        if date_str:
                            from dateutil import parser as date_parser
                            expiry_date = date_parser.parse(date_str).date()
                    except Exception:
                        pass

                domains.append({
                    "name": name,
                    "tld": tld,
                    "full_name": full_domain,
                    "length": len(name),
                    "expiry_date": expiry_date,
                    "source": "snapnames",
                })

            logger.info("snapnames_crawled", count=len(domains))

        except Exception as e:
            logger.error("snapnames_crawl_error", error=str(e))

        return domains

    async def crawl_dynadot(self) -> List[Dict[str, Any]]:
        """
        Dynadot 백오더 도메인 크롤링

        Returns:
            도메인 정보 리스트
        """
        domains = []

        try:
            logger.info("crawling_dynadot")
            content = await self._fetch(self.SOURCES["dynadot"]["url"])

            # CSV 파싱
            reader = csv.reader(io.StringIO(content))
            header = None

            for row in reader:
                if not row:
                    continue

                # 헤더 행 스킵
                if header is None:
                    if any("domain" in col.lower() for col in row):
                        header = [col.lower() for col in row]
                        continue
                    header = []

                # 도메인 추출 (첫 번째 컬럼 또는 domain 컬럼)
                full_domain = row[0].strip().lower()
                if not full_domain or "." not in full_domain:
                    continue

                # 도메인 파싱
                parts = full_domain.rsplit(".", 1)
                if len(parts) != 2:
                    continue

                name, tld = parts[0], parts[1]

                # 필터링
                if not self._filter_domain(name, tld):
                    continue

                # 만료일 (Dynadot은 보통 5일 이내)
                expiry_date = date.today() + timedelta(days=5)

                domains.append({
                    "name": name,
                    "tld": tld,
                    "full_name": full_domain,
                    "length": len(name),
                    "expiry_date": expiry_date,
                    "source": "dynadot",
                })

            logger.info("dynadot_crawled", count=len(domains))

        except Exception as e:
            logger.error("dynadot_crawl_error", error=str(e))

        return domains

    async def crawl_estibot(self) -> List[Dict[str, Any]]:
        """
        EstiBot Drops 페이지 크롤링

        Returns:
            도메인 정보 리스트
        """
        domains = []

        try:
            logger.info("crawling_estibot")
            html = await self._fetch(self.SOURCES["estibot"]["url"])

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")

            # EstiBot 페이지에서 텍스트 파일 링크 찾기
            download_links = []
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if ".txt" in href or "pendingdelete" in href.lower():
                    download_links.append(href)

            # 텍스트 파일 다운로드 및 파싱
            for link in download_links[:3]:  # 최대 3개 파일
                try:
                    if not link.startswith("http"):
                        link = f"https://www.estibot.com{link}"

                    content = await self._fetch(link)

                    # 도메인 리스트 파싱 (한 줄에 하나씩)
                    for line in content.split("\n"):
                        full_domain = line.strip().lower()
                        if not full_domain or "." not in full_domain:
                            continue

                        parts = full_domain.rsplit(".", 1)
                        if len(parts) != 2:
                            continue

                        name, tld = parts[0], parts[1]

                        if not self._filter_domain(name, tld):
                            continue

                        domains.append({
                            "name": name,
                            "tld": tld,
                            "full_name": full_domain,
                            "length": len(name),
                            "expiry_date": date.today() + timedelta(days=1),
                            "source": "estibot",
                        })

                except Exception as e:
                    logger.warning("estibot_file_error", link=link, error=str(e))
                    continue

            logger.info("estibot_crawled", count=len(domains))

        except Exception as e:
            logger.error("estibot_crawl_error", error=str(e))

        return domains

    async def crawl_all_sources(
        self,
        sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        모든 활성화된 소스에서 크롤링

        Args:
            sources: 크롤링할 소스 리스트 (None이면 모든 소스)

        Returns:
            도메인 정보 리스트 (중복 제거됨)
        """
        all_domains = []
        seen = set()

        # 크롤링할 소스 결정
        if sources is None:
            sources = ["snapnames", "dynadot", "estibot"]

        crawl_methods = {
            "snapnames": self.crawl_snapnames,
            "dynadot": self.crawl_dynadot,
            "estibot": self.crawl_estibot,
        }

        for source in sources:
            if source not in crawl_methods:
                logger.warning("unknown_source", source=source)
                continue

            try:
                logger.info("crawling_source", source=source)
                domains = await crawl_methods[source]()

                # 중복 제거하면서 추가
                for d in domains:
                    key = d["full_name"]
                    if key not in seen:
                        seen.add(key)
                        all_domains.append(d)

                # 소스 간 딜레이
                await asyncio.sleep(5)

            except Exception as e:
                logger.error("source_crawl_error", source=source, error=str(e))
                continue

        logger.info("all_sources_crawled", total=len(all_domains), sources=sources)
        return all_domains


class VerisignZoneFileCrawler:
    """
    Verisign Zone File 직접 접근 크롤러
    참고: Verisign에서 Zone File 접근 권한이 필요합니다.
    https://www.verisign.com/en_US/channel-resources/domain-registry-products/zone-file/index.xhtml
    """

    PENDING_DELETE_URL = "https://www.verisign.com/en_US/channel-resources/domain-registry-products/zone-file/index.xhtml"

    def __init__(self):
        self.client: Optional[httpx.AsyncClient] = None
        self.parser = DomainParser()

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def get_info(self) -> Dict[str, Any]:
        """Zone File 접근 정보 반환"""
        return {
            "name": "Verisign Zone File",
            "description": "공식 Verisign PendingDelete Zone File",
            "access": "신청 필요 (무료, 약 5일 소요)",
            "url": self.PENDING_DELETE_URL,
            "instructions": [
                "1. Verisign Zone File 페이지 방문",
                "2. Zone File Access 신청",
                "3. 승인 후 FTP/SFTP 접근 정보 수신",
                "4. 매일 업데이트되는 PendingDelete 파일 다운로드",
            ]
        }


# 통합 크롤러 - 기존 ExpiredDomainsCrawler와 함께 사용
class MultiSourceCrawler:
    """
    다중 소스 통합 크롤러 (강화 버전)
    ExpiredDomains.net + 대체 소스를 함께 사용

    특징:
    - 병렬/순차 크롤링 선택
    - 소스별 통계 및 상태 추적
    - 개별 소스 실패 시 다른 소스 계속 실행
    - Anti-blocking 시스템 통합
    - 재시도 로직
    """

    def __init__(self, use_anti_blocking: bool = True):
        from .expired_domains import ExpiredDomainsCrawler
        self.expired_domains = ExpiredDomainsCrawler()
        self.alternative = AlternativeSourcesCrawler()
        self.parser = DomainParser()
        self.use_anti_blocking = use_anti_blocking

        # Anti-blocking 매니저 (선택적)
        self.anti_blocking = None
        if use_anti_blocking:
            try:
                from .anti_blocking import AntiBlockingManager
                self.anti_blocking = AntiBlockingManager()
            except ImportError:
                logger.warning("anti_blocking_not_available")

        # 소스별 통계
        self._stats = {
            "expireddomains": {"success": 0, "failed": 0, "domains": 0, "last_error": None},
            "snapnames": {"success": 0, "failed": 0, "domains": 0, "last_error": None},
            "dynadot": {"success": 0, "failed": 0, "domains": 0, "last_error": None},
            "estibot": {"success": 0, "failed": 0, "domains": 0, "last_error": None},
        }

        # 소스 건강 상태
        self._source_health = {
            "expireddomains": True,
            "snapnames": True,
            "dynadot": True,
            "estibot": True,
        }

        self._initialized = False

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def init(self) -> None:
        """크롤러 초기화"""
        if self._initialized:
            return

        await self.expired_domains.init_client()
        await self.alternative.init_client()
        self._initialized = True
        logger.info("multi_source_crawler_initialized")

    async def close(self) -> None:
        """크롤러 종료"""
        await self.expired_domains.close()
        await self.alternative.close()
        self._initialized = False
        logger.info("multi_source_crawler_closed")

    def get_stats(self) -> Dict[str, Any]:
        """소스별 통계 반환"""
        return {
            "sources": self._stats.copy(),
            "health": self._source_health.copy(),
        }

    def get_healthy_sources(self) -> List[str]:
        """건강한 소스 목록 반환"""
        return [s for s, healthy in self._source_health.items() if healthy]

    def _update_stats(self, source: str, success: bool, domain_count: int = 0, error: str = None):
        """통계 업데이트"""
        if source not in self._stats:
            self._stats[source] = {"success": 0, "failed": 0, "domains": 0, "last_error": None}

        if success:
            self._stats[source]["success"] += 1
            self._stats[source]["domains"] += domain_count
            # 성공 시 건강 상태 복구
            self._source_health[source] = True
        else:
            self._stats[source]["failed"] += 1
            self._stats[source]["last_error"] = error
            # 연속 3회 실패 시 건강 상태 비정상
            if self._stats[source]["failed"] >= 3:
                self._source_health[source] = False

    async def _crawl_expireddomains(
        self,
        days_until_expiry: int,
        max_pages_per_tld: int,
        progress_callback: callable = None
    ) -> List[Dict[str, Any]]:
        """ExpiredDomains.net 크롤링 (내부)"""
        try:
            if progress_callback:
                await progress_callback(10, "ExpiredDomains.net 크롤링 시작...")

            domains = await self.expired_domains.crawl_all_tlds(
                days_until_expiry=days_until_expiry,
                max_pages_per_tld=max_pages_per_tld
            )

            # 소스 태그 추가
            for d in domains:
                d["source"] = d.get("source", "expireddomains")
                if "full_name" not in d:
                    d["full_name"] = f"{d['name']}.{d['tld']}"

            self._update_stats("expireddomains", True, len(domains))
            logger.info("expireddomains_crawled", count=len(domains))
            return domains

        except Exception as e:
            self._update_stats("expireddomains", False, error=str(e))
            logger.error("expireddomains_error", error=str(e))
            return []

    async def _crawl_alternative_source(
        self,
        source: str,
        progress_callback: callable = None
    ) -> List[Dict[str, Any]]:
        """개별 대체 소스 크롤링 (내부)"""
        crawl_methods = {
            "snapnames": self.alternative.crawl_snapnames,
            "dynadot": self.alternative.crawl_dynadot,
            "estibot": self.alternative.crawl_estibot,
        }

        if source not in crawl_methods:
            logger.warning("unknown_source", source=source)
            return []

        # 건강하지 않은 소스 스킵 (선택적)
        if not self._source_health.get(source, True):
            logger.warning("skipping_unhealthy_source", source=source)
            return []

        try:
            if progress_callback:
                await progress_callback(0, f"{source} 크롤링 중...")

            # Anti-blocking 딜레이 적용
            if self.anti_blocking:
                await self.anti_blocking.delay.wait()

            domains = await crawl_methods[source]()

            if self.anti_blocking:
                self.anti_blocking.delay.on_success()

            self._update_stats(source, True, len(domains))
            logger.info(f"{source}_crawled", count=len(domains))
            return domains

        except Exception as e:
            if self.anti_blocking:
                # HTTP 에러 코드 추출 시도
                error_str = str(e)
                if "429" in error_str:
                    self.anti_blocking.delay.on_error(429)
                elif "403" in error_str:
                    self.anti_blocking.delay.on_error(403)
                else:
                    self.anti_blocking.delay.on_error(500)

            self._update_stats(source, False, error=str(e))
            logger.error(f"{source}_error", error=str(e))
            return []

    async def crawl_all(
        self,
        use_expireddomains: bool = True,
        use_alternative: bool = True,
        days_until_expiry: int = 30,
        max_pages_per_tld: int = 3,
        alternative_sources: Optional[List[str]] = None,
        parallel: bool = False,
        progress_callback: callable = None
    ) -> List[Dict[str, Any]]:
        """
        모든 소스에서 크롤링

        Args:
            use_expireddomains: ExpiredDomains.net 사용 여부
            use_alternative: 대체 소스 사용 여부
            days_until_expiry: 만료 예정 일수
            max_pages_per_tld: TLD당 최대 페이지 수
            alternative_sources: 사용할 대체 소스 리스트
            parallel: 대체 소스 병렬 크롤링 여부
            progress_callback: 진행 상황 콜백 (progress_percent, message)

        Returns:
            도메인 정보 리스트 (중복 제거됨)
        """
        all_domains = []
        seen = set()
        sources_results = {}

        # 초기화 확인
        if not self._initialized:
            await self.init()

        # 1. ExpiredDomains.net 크롤링
        if use_expireddomains:
            logger.info("crawling_expireddomains")
            domains = await self._crawl_expireddomains(
                days_until_expiry=days_until_expiry,
                max_pages_per_tld=max_pages_per_tld,
                progress_callback=progress_callback
            )
            sources_results["expireddomains"] = len(domains)

            for d in domains:
                key = d.get("full_name", f"{d['name']}.{d['tld']}")
                if key not in seen:
                    seen.add(key)
                    all_domains.append(d)

        # 2. 대체 소스 크롤링
        if use_alternative:
            if alternative_sources is None:
                alternative_sources = ["snapnames", "dynadot", "estibot"]

            if progress_callback:
                await progress_callback(40, "대체 소스 크롤링 시작...")

            if parallel:
                # 병렬 크롤링
                tasks = [
                    self._crawl_alternative_source(source, None)
                    for source in alternative_sources
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for source, result in zip(alternative_sources, results):
                    if isinstance(result, Exception):
                        logger.error(f"{source}_parallel_error", error=str(result))
                        sources_results[source] = 0
                    else:
                        sources_results[source] = len(result)
                        for d in result:
                            key = d["full_name"]
                            if key not in seen:
                                seen.add(key)
                                all_domains.append(d)
            else:
                # 순차 크롤링
                for i, source in enumerate(alternative_sources):
                    if progress_callback:
                        progress = 40 + (i * 20 // len(alternative_sources))
                        await progress_callback(progress, f"{source} 크롤링 중...")

                    domains = await self._crawl_alternative_source(source, None)
                    sources_results[source] = len(domains)

                    for d in domains:
                        key = d["full_name"]
                        if key not in seen:
                            seen.add(key)
                            all_domains.append(d)

                    # 소스 간 딜레이
                    if self.anti_blocking:
                        await asyncio.sleep(3)
                    else:
                        await asyncio.sleep(5)

        if progress_callback:
            await progress_callback(60, "중복 제거 완료...")

        logger.info(
            "multi_source_crawl_complete",
            total=len(all_domains),
            sources=sources_results
        )

        return all_domains

    async def crawl_pending_delete(
        self,
        max_pages: int = 3,
        use_alternative: bool = True,
        alternative_sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        삭제 예정 도메인 크롤링 (1일 이내)

        Args:
            max_pages: 최대 페이지 수
            use_alternative: 대체 소스 사용 여부
            alternative_sources: 사용할 대체 소스 리스트

        Returns:
            도메인 정보 리스트 (중복 제거됨)
        """
        all_domains = []
        seen = set()

        # 초기화 확인
        if not self._initialized:
            await self.init()

        # ExpiredDomains.net pending delete
        try:
            domains = await self.expired_domains.crawl_pending_delete(max_pages=max_pages)
            for d in domains:
                d["source"] = d.get("source", "expireddomains")
                if "full_name" not in d:
                    d["full_name"] = f"{d['name']}.{d['tld']}"
                key = d["full_name"]
                if key not in seen:
                    seen.add(key)
                    all_domains.append(d)
            self._update_stats("expireddomains", True, len(domains))
        except Exception as e:
            self._update_stats("expireddomains", False, error=str(e))
            logger.error("pending_delete_expireddomains_error", error=str(e))

        # 대체 소스 (EstiBot은 pending delete 전문)
        if use_alternative:
            if alternative_sources is None:
                alternative_sources = ["estibot"]  # EstiBot은 PendingDelete 전문

            for source in alternative_sources:
                domains = await self._crawl_alternative_source(source)
                for d in domains:
                    key = d["full_name"]
                    if key not in seen:
                        seen.add(key)
                        all_domains.append(d)

        logger.info("pending_delete_crawl_complete", total=len(all_domains))
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
        if not self._initialized:
            await self.init()

        try:
            return await self.expired_domains.search_keyword(keyword, max_pages)
        except Exception as e:
            logger.error("keyword_search_error", keyword=keyword, error=str(e))
            return []

    def reset_stats(self) -> None:
        """통계 초기화"""
        for source in self._stats:
            self._stats[source] = {"success": 0, "failed": 0, "domains": 0, "last_error": None}
        for source in self._source_health:
            self._source_health[source] = True
        logger.info("stats_reset")

    def reset_source_health(self, source: str = None) -> None:
        """소스 건강 상태 초기화"""
        if source:
            if source in self._source_health:
                self._source_health[source] = True
                self._stats[source]["failed"] = 0
        else:
            for s in self._source_health:
                self._source_health[s] = True
                self._stats[s]["failed"] = 0
        logger.info("source_health_reset", source=source or "all")


# 테스트
if __name__ == "__main__":
    async def test():
        print("=== Alternative Sources Crawler Test ===\n")

        async with AlternativeSourcesCrawler() as crawler:
            # 각 소스별 테스트
            print("Testing SnapNames...")
            domains = await crawler.crawl_snapnames()
            print(f"  Found {len(domains)} domains from SnapNames")
            if domains:
                print(f"  Sample: {domains[0]}")

            print("\nTesting Dynadot...")
            domains = await crawler.crawl_dynadot()
            print(f"  Found {len(domains)} domains from Dynadot")
            if domains:
                print(f"  Sample: {domains[0]}")

            print("\nTesting EstiBot...")
            domains = await crawler.crawl_estibot()
            print(f"  Found {len(domains)} domains from EstiBot")
            if domains:
                print(f"  Sample: {domains[0]}")

            print("\n=== All Sources Combined ===")
            all_domains = await crawler.crawl_all_sources()
            print(f"Total unique domains: {len(all_domains)}")

            # 소스별 통계
            source_counts = {}
            for d in all_domains:
                source = d.get("source", "unknown")
                source_counts[source] = source_counts.get(source, 0) + 1
            print(f"By source: {source_counts}")

    asyncio.run(test())
