"""
Domain Sniper - 도메인 가용성 확인
WHOIS, RDAP 프로토콜을 사용하여 도메인 등록 가능 여부를 확인합니다.
"""

import asyncio
import socket
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from enum import Enum

import httpx
import structlog

logger = structlog.get_logger()


class DomainStatus(Enum):
    """도메인 상태"""
    AVAILABLE = "available"          # 등록 가능
    REGISTERED = "registered"        # 등록됨
    PENDING_DELETE = "pending_delete"  # 삭제 대기
    REDEMPTION = "redemption"        # 복구 기간
    RESERVED = "reserved"            # 예약됨
    UNKNOWN = "unknown"              # 알 수 없음
    ERROR = "error"                  # 조회 오류


@dataclass
class AvailabilityResult:
    """도메인 가용성 확인 결과"""
    domain: str
    available: Optional[bool] = None
    status: DomainStatus = DomainStatus.UNKNOWN
    registrar: Optional[str] = None
    creation_date: Optional[date] = None
    expiry_date: Optional[date] = None
    updated_date: Optional[date] = None
    name_servers: List[str] = field(default_factory=list)
    raw_data: Optional[Dict] = None
    error: Optional[str] = None
    source: str = "unknown"
    checked_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "domain": self.domain,
            "available": self.available,
            "status": self.status.value,
            "registrar": self.registrar,
            "creation_date": self.creation_date.isoformat() if self.creation_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "updated_date": self.updated_date.isoformat() if self.updated_date else None,
            "name_servers": self.name_servers,
            "error": self.error,
            "source": self.source,
            "checked_at": self.checked_at.isoformat(),
        }


class RDAPChecker:
    """
    RDAP (Registration Data Access Protocol) 기반 도메인 확인
    WHOIS보다 더 표준화되고 정확한 방법
    """

    # TLD별 RDAP 서버
    RDAP_SERVERS = {
        # Verisign (.com, .net)
        "com": "https://rdap.verisign.com/com/v1/domain/",
        "net": "https://rdap.verisign.com/net/v1/domain/",

        # PIR (.org)
        "org": "https://rdap.publicinterestregistry.org/rdap/domain/",

        # Identity Digital
        "io": "https://rdap.nic.io/domain/",
        "co": "https://rdap.nic.co/domain/",
        "ai": "https://rdap.nic.ai/domain/",

        # Others
        "info": "https://rdap.afilias.net/rdap/info/domain/",
        "biz": "https://rdap.nic.biz/domain/",

        # ccTLDs
        "kr": "https://rdap.kisa.or.kr/rdap/domain/",
        "de": "https://rdap.denic.de/domain/",
        "uk": "https://rdap.nominet.uk/uk/domain/",
    }

    # IANA 부트스트랩 서버 (알 수 없는 TLD용)
    BOOTSTRAP_URL = "https://rdap.org/domain/"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def check(self, domain: str) -> AvailabilityResult:
        """
        RDAP를 통한 도메인 확인

        Args:
            domain: 확인할 도메인

        Returns:
            AvailabilityResult
        """
        domain = domain.lower().strip()
        tld = domain.split(".")[-1]

        # RDAP 서버 URL 결정
        if tld in self.RDAP_SERVERS:
            base_url = self.RDAP_SERVERS[tld]
        else:
            base_url = self.BOOTSTRAP_URL

        url = f"{base_url}{domain}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    headers={"Accept": "application/rdap+json, application/json"},
                    follow_redirects=True
                )

                if response.status_code == 404:
                    # 404 = 도메인이 존재하지 않음 = 등록 가능
                    return AvailabilityResult(
                        domain=domain,
                        available=True,
                        status=DomainStatus.AVAILABLE,
                        source="rdap"
                    )

                elif response.status_code == 200:
                    # 200 = 도메인 정보 존재 = 등록됨
                    data = response.json()
                    return self._parse_rdap_response(domain, data)

                else:
                    return AvailabilityResult(
                        domain=domain,
                        available=None,
                        status=DomainStatus.ERROR,
                        error=f"HTTP {response.status_code}",
                        source="rdap"
                    )

        except httpx.TimeoutException:
            logger.warning("rdap_timeout", domain=domain)
            return AvailabilityResult(
                domain=domain,
                available=None,
                status=DomainStatus.ERROR,
                error="Timeout",
                source="rdap"
            )
        except Exception as e:
            logger.error("rdap_error", domain=domain, error=str(e))
            return AvailabilityResult(
                domain=domain,
                available=None,
                status=DomainStatus.ERROR,
                error=str(e),
                source="rdap"
            )

    def _parse_rdap_response(self, domain: str, data: Dict) -> AvailabilityResult:
        """RDAP 응답 파싱"""
        result = AvailabilityResult(
            domain=domain,
            available=False,
            status=DomainStatus.REGISTERED,
            raw_data=data,
            source="rdap"
        )

        # 상태 확인
        status_list = data.get("status", [])
        if any("pendingDelete" in s for s in status_list):
            result.status = DomainStatus.PENDING_DELETE
        elif any("redemptionPeriod" in s for s in status_list):
            result.status = DomainStatus.REDEMPTION

        # 이벤트 (날짜 정보) 파싱
        for event in data.get("events", []):
            action = event.get("eventAction", "")
            date_str = event.get("eventDate", "")

            if date_str:
                try:
                    event_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()

                    if action == "registration":
                        result.creation_date = event_date
                    elif action == "expiration":
                        result.expiry_date = event_date
                    elif action == "last changed":
                        result.updated_date = event_date
                except ValueError:
                    pass

        # 레지스트라 정보
        for entity in data.get("entities", []):
            roles = entity.get("roles", [])
            if "registrar" in roles:
                result.registrar = entity.get("vcardArray", [[]])[1][0][3] if entity.get("vcardArray") else None
                if not result.registrar:
                    result.registrar = entity.get("handle")
                break

        # 네임서버
        for ns in data.get("nameservers", []):
            ns_name = ns.get("ldhName")
            if ns_name:
                result.name_servers.append(ns_name)

        return result


class WHOISChecker:
    """
    WHOIS 프로토콜 기반 도메인 확인
    python-whois 없이 직접 소켓 통신
    """

    # TLD별 WHOIS 서버
    WHOIS_SERVERS = {
        "com": "whois.verisign-grs.com",
        "net": "whois.verisign-grs.com",
        "org": "whois.pir.org",
        "io": "whois.nic.io",
        "co": "whois.nic.co",
        "ai": "whois.nic.ai",
        "info": "whois.afilias.net",
        "biz": "whois.biz",
        "kr": "whois.kr",
    }

    # 도메인 미등록 표시 패턴
    NOT_FOUND_PATTERNS = [
        "no match",
        "not found",
        "no data found",
        "no entries found",
        "no object found",
        "domain not found",
        "no match for",
        "is available",
        "status: free",
        "status: available",
    ]

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def check(self, domain: str) -> AvailabilityResult:
        """
        WHOIS를 통한 도메인 확인

        Args:
            domain: 확인할 도메인

        Returns:
            AvailabilityResult
        """
        domain = domain.lower().strip()
        tld = domain.split(".")[-1]

        if tld not in self.WHOIS_SERVERS:
            return AvailabilityResult(
                domain=domain,
                available=None,
                status=DomainStatus.ERROR,
                error=f"Unsupported TLD: {tld}",
                source="whois"
            )

        whois_server = self.WHOIS_SERVERS[tld]

        try:
            # 비동기로 WHOIS 조회
            raw_response = await self._query_whois(domain, whois_server)

            if not raw_response:
                return AvailabilityResult(
                    domain=domain,
                    available=None,
                    status=DomainStatus.ERROR,
                    error="Empty response",
                    source="whois"
                )

            # 응답 파싱
            return self._parse_whois_response(domain, raw_response)

        except asyncio.TimeoutError:
            logger.warning("whois_timeout", domain=domain)
            return AvailabilityResult(
                domain=domain,
                available=None,
                status=DomainStatus.ERROR,
                error="Timeout",
                source="whois"
            )
        except Exception as e:
            logger.error("whois_error", domain=domain, error=str(e))
            return AvailabilityResult(
                domain=domain,
                available=None,
                status=DomainStatus.ERROR,
                error=str(e),
                source="whois"
            )

    async def _query_whois(self, domain: str, server: str, port: int = 43) -> str:
        """WHOIS 서버에 쿼리"""
        loop = asyncio.get_event_loop()

        def sync_query():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            try:
                sock.connect((server, port))
                sock.sendall(f"{domain}\r\n".encode())

                response = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk

                return response.decode("utf-8", errors="ignore")
            finally:
                sock.close()

        return await loop.run_in_executor(None, sync_query)

    def _parse_whois_response(self, domain: str, raw: str) -> AvailabilityResult:
        """WHOIS 응답 파싱"""
        raw_lower = raw.lower()

        # 미등록 여부 확인
        for pattern in self.NOT_FOUND_PATTERNS:
            if pattern in raw_lower:
                return AvailabilityResult(
                    domain=domain,
                    available=True,
                    status=DomainStatus.AVAILABLE,
                    raw_data={"raw": raw},
                    source="whois"
                )

        # 등록된 도메인 정보 파싱
        result = AvailabilityResult(
            domain=domain,
            available=False,
            status=DomainStatus.REGISTERED,
            raw_data={"raw": raw},
            source="whois"
        )

        # 라인별 파싱
        for line in raw.split("\n"):
            line = line.strip()
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if not value:
                continue

            # 레지스트라
            if key in ["registrar", "registrar name"]:
                result.registrar = value

            # 생성일
            elif key in ["creation date", "created", "created date", "registration date"]:
                result.creation_date = self._parse_date(value)

            # 만료일
            elif key in ["expiry date", "expiration date", "expires", "registry expiry date"]:
                result.expiry_date = self._parse_date(value)

            # 업데이트일
            elif key in ["updated date", "last updated", "last modified"]:
                result.updated_date = self._parse_date(value)

            # 네임서버
            elif key in ["name server", "nameserver", "nserver"]:
                result.name_servers.append(value.lower())

            # 상태
            elif key in ["status", "domain status"]:
                if "pendingdelete" in value.lower():
                    result.status = DomainStatus.PENDING_DELETE
                elif "redemption" in value.lower():
                    result.status = DomainStatus.REDEMPTION

        return result

    def _parse_date(self, date_str: str) -> Optional[date]:
        """날짜 문자열 파싱"""
        # 다양한 날짜 형식 시도
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d-%b-%Y",
            "%d %b %Y",
            "%Y.%m.%d",
            "%d.%m.%Y",
        ]

        # 시간대 제거
        date_str = date_str.split("+")[0].strip()

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None


class DomainAvailabilityChecker:
    """
    도메인 가용성 확인 통합 클래스
    RDAP를 우선 사용하고, 실패 시 WHOIS 사용
    """

    def __init__(self, timeout: float = 10.0, use_cache: bool = True, cache_ttl: int = 3600):
        self.rdap = RDAPChecker(timeout=timeout)
        self.whois = WHOISChecker(timeout=timeout)
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # {domain: (result, timestamp)}

    async def check(self, domain: str, force_refresh: bool = False) -> AvailabilityResult:
        """
        도메인 가용성 확인 (RDAP -> WHOIS 순서)

        Args:
            domain: 확인할 도메인
            force_refresh: 캐시 무시 여부

        Returns:
            AvailabilityResult
        """
        domain = domain.lower().strip()

        # 캐시 확인
        if self.use_cache and not force_refresh:
            cached = self._get_from_cache(domain)
            if cached:
                logger.debug("availability_cache_hit", domain=domain)
                return cached

        # RDAP 시도
        result = await self.rdap.check(domain)

        # RDAP 실패 시 WHOIS 시도
        if result.status == DomainStatus.ERROR:
            logger.debug("rdap_failed_trying_whois", domain=domain)
            result = await self.whois.check(domain)

        # 캐시 저장
        if self.use_cache and result.status != DomainStatus.ERROR:
            self._save_to_cache(domain, result)

        logger.info(
            "availability_checked",
            domain=domain,
            available=result.available,
            status=result.status.value,
            source=result.source
        )

        return result

    async def check_batch(
        self,
        domains: List[str],
        concurrency: int = 5,
        delay: float = 0.5
    ) -> List[AvailabilityResult]:
        """
        여러 도메인 일괄 확인

        Args:
            domains: 도메인 리스트
            concurrency: 동시 요청 수
            delay: 요청 간 딜레이

        Returns:
            AvailabilityResult 리스트
        """
        semaphore = asyncio.Semaphore(concurrency)
        results = []

        async def check_with_limit(domain: str):
            async with semaphore:
                result = await self.check(domain)
                await asyncio.sleep(delay)
                return result

        tasks = [check_with_limit(d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외 처리
        final_results = []
        for domain, result in zip(domains, results):
            if isinstance(result, Exception):
                final_results.append(AvailabilityResult(
                    domain=domain,
                    available=None,
                    status=DomainStatus.ERROR,
                    error=str(result),
                    source="batch"
                ))
            else:
                final_results.append(result)

        return final_results

    def _get_from_cache(self, domain: str) -> Optional[AvailabilityResult]:
        """캐시에서 결과 조회"""
        if domain not in self._cache:
            return None

        result, timestamp = self._cache[domain]
        if datetime.now().timestamp() - timestamp > self.cache_ttl:
            del self._cache[domain]
            return None

        return result

    def _save_to_cache(self, domain: str, result: AvailabilityResult) -> None:
        """캐시에 결과 저장"""
        self._cache[domain] = (result, datetime.now().timestamp())

    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._cache.clear()


# DNS 기반 빠른 확인 (보조 수단)
class DNSChecker:
    """DNS 조회 기반 빠른 확인 (참고용)"""

    @staticmethod
    async def has_dns_records(domain: str) -> bool:
        """
        도메인에 DNS 레코드가 있는지 확인
        주의: DNS 레코드가 없어도 등록된 도메인일 수 있음

        Args:
            domain: 확인할 도메인

        Returns:
            DNS 레코드 존재 여부
        """
        loop = asyncio.get_event_loop()

        def check():
            try:
                socket.gethostbyname(domain)
                return True
            except socket.gaierror:
                return False

        return await loop.run_in_executor(None, check)


# 테스트
if __name__ == "__main__":
    async def test():
        print("=== Domain Availability Checker Test ===\n")

        checker = DomainAvailabilityChecker()

        # 테스트 도메인
        test_domains = [
            "google.com",         # 확실히 등록됨
            "xyzabc123random.com",  # 아마 등록 가능
        ]

        for domain in test_domains:
            print(f"Checking: {domain}")
            result = await checker.check(domain)
            print(f"  Available: {result.available}")
            print(f"  Status: {result.status.value}")
            print(f"  Source: {result.source}")
            if result.registrar:
                print(f"  Registrar: {result.registrar}")
            if result.expiry_date:
                print(f"  Expiry: {result.expiry_date}")
            if result.error:
                print(f"  Error: {result.error}")
            print()

    asyncio.run(test())
