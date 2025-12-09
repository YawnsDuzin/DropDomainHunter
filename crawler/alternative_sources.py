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
    다중 소스 통합 크롤러
    ExpiredDomains.net + 대체 소스를 함께 사용
    """

    def __init__(self):
        from .expired_domains import ExpiredDomainsCrawler
        self.expired_domains = ExpiredDomainsCrawler()
        self.alternative = AlternativeSourcesCrawler()
        self.parser = DomainParser()

    async def __aenter__(self):
        await self.expired_domains.init_client()
        await self.alternative.init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.expired_domains.close()
        await self.alternative.close()

    async def crawl_all(
        self,
        use_expireddomains: bool = True,
        use_alternative: bool = True,
        days_until_expiry: int = 30,
        max_pages_per_tld: int = 3,
        alternative_sources: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        모든 소스에서 크롤링

        Args:
            use_expireddomains: ExpiredDomains.net 사용 여부
            use_alternative: 대체 소스 사용 여부
            days_until_expiry: 만료 예정 일수
            max_pages_per_tld: TLD당 최대 페이지 수
            alternative_sources: 사용할 대체 소스 리스트

        Returns:
            도메인 정보 리스트 (중복 제거됨)
        """
        all_domains = []
        seen = set()

        # ExpiredDomains.net 크롤링
        if use_expireddomains:
            try:
                logger.info("crawling_expireddomains")
                domains = await self.expired_domains.crawl_all_tlds(
                    days_until_expiry=days_until_expiry,
                    max_pages_per_tld=max_pages_per_tld
                )
                for d in domains:
                    key = d.get("full_name", f"{d['name']}.{d['tld']}")
                    if key not in seen:
                        seen.add(key)
                        d["source"] = d.get("source", "expireddomains")
                        all_domains.append(d)
                logger.info("expireddomains_done", count=len(domains))
            except Exception as e:
                logger.error("expireddomains_error", error=str(e))

        # 대체 소스 크롤링
        if use_alternative:
            try:
                logger.info("crawling_alternative_sources")
                domains = await self.alternative.crawl_all_sources(
                    sources=alternative_sources
                )
                for d in domains:
                    key = d["full_name"]
                    if key not in seen:
                        seen.add(key)
                        all_domains.append(d)
                logger.info("alternative_sources_done", count=len(domains))
            except Exception as e:
                logger.error("alternative_sources_error", error=str(e))

        logger.info("multi_source_crawl_complete", total=len(all_domains))
        return all_domains


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
