"""
Domain Sniper - 도메인 히스토리 확인
Archive.org 등을 통해 도메인의 과거 이력을 확인합니다.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, Any, List

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class ArchiveSnapshot:
    """아카이브 스냅샷 정보"""
    timestamp: str
    url: str
    status: Optional[str] = None

    @property
    def date(self) -> Optional[date]:
        """스냅샷 날짜"""
        try:
            # timestamp 형식: YYYYMMDDHHmmss
            return datetime.strptime(self.timestamp[:8], "%Y%m%d").date()
        except (ValueError, IndexError):
            return None


@dataclass
class DomainHistory:
    """도메인 히스토리 정보"""
    domain: str
    has_history: bool = False
    first_seen: Optional[date] = None
    last_seen: Optional[date] = None
    snapshot_count: int = 0
    snapshots: List[ArchiveSnapshot] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    previous_content_type: Optional[str] = None
    error: Optional[str] = None
    checked_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "domain": self.domain,
            "has_history": self.has_history,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "snapshot_count": self.snapshot_count,
            "categories": self.categories,
            "previous_content_type": self.previous_content_type,
            "error": self.error,
            "checked_at": self.checked_at.isoformat(),
        }

    @property
    def age_years(self) -> Optional[float]:
        """도메인 연령 (년)"""
        if not self.first_seen:
            return None
        delta = date.today() - self.first_seen
        return delta.days / 365.25


class DomainHistoryChecker:
    """
    도메인 히스토리 확인
    Archive.org (Wayback Machine) API 사용
    """

    WAYBACK_API = "https://archive.org/wayback/available"
    WAYBACK_CDX_API = "https://web.archive.org/cdx/search/cdx"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def check(self, domain: str) -> DomainHistory:
        """
        도메인 히스토리 확인

        Args:
            domain: 확인할 도메인

        Returns:
            DomainHistory
        """
        domain = domain.lower().strip()

        # www 없는 버전으로 통일
        if domain.startswith("www."):
            domain = domain[4:]

        result = DomainHistory(domain=domain)

        try:
            # 1. 기본 가용성 확인 (가장 가까운 스냅샷)
            availability = await self._check_availability(domain)

            if availability:
                result.has_history = True
                result.last_seen = availability.get("last_seen")

            # 2. CDX API로 상세 히스토리 조회
            cdx_data = await self._query_cdx(domain)

            if cdx_data:
                result.has_history = True
                result.snapshots = cdx_data["snapshots"]
                result.snapshot_count = len(cdx_data["snapshots"])
                result.first_seen = cdx_data.get("first_seen")
                result.last_seen = cdx_data.get("last_seen") or result.last_seen

                # 콘텐츠 타입 분석
                if cdx_data["snapshots"]:
                    result.previous_content_type = self._analyze_content_type(cdx_data["snapshots"])

            logger.info(
                "history_checked",
                domain=domain,
                has_history=result.has_history,
                snapshot_count=result.snapshot_count,
                age_years=result.age_years
            )

        except Exception as e:
            logger.error("history_check_error", domain=domain, error=str(e))
            result.error = str(e)

        return result

    async def _check_availability(self, domain: str) -> Optional[Dict]:
        """Wayback Machine 가용성 확인"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.WAYBACK_API,
                    params={"url": domain}
                )

                if response.status_code != 200:
                    return None

                data = response.json()
                snapshots = data.get("archived_snapshots", {})

                if snapshots.get("closest"):
                    closest = snapshots["closest"]
                    timestamp = closest.get("timestamp", "")

                    return {
                        "available": closest.get("available", False),
                        "url": closest.get("url"),
                        "timestamp": timestamp,
                        "last_seen": self._parse_timestamp(timestamp),
                    }

        except Exception as e:
            logger.debug("wayback_availability_error", domain=domain, error=str(e))

        return None

    async def _query_cdx(self, domain: str, limit: int = 100) -> Optional[Dict]:
        """
        CDX API로 모든 스냅샷 조회

        Args:
            domain: 도메인
            limit: 최대 결과 수

        Returns:
            스냅샷 정보
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.WAYBACK_CDX_API,
                    params={
                        "url": f"*.{domain}/*" if "." in domain else f"{domain}/*",
                        "output": "json",
                        "fl": "timestamp,original,statuscode",
                        "collapse": "timestamp:6",  # 월별로 그룹화
                        "limit": limit,
                    }
                )

                if response.status_code != 200:
                    return None

                data = response.json()

                if not data or len(data) < 2:  # 첫 번째는 헤더
                    return None

                # 헤더 제외하고 파싱
                snapshots = []
                first_timestamp = None
                last_timestamp = None

                for row in data[1:]:  # 헤더 제외
                    if len(row) >= 2:
                        timestamp = row[0]
                        original_url = row[1]
                        status = row[2] if len(row) > 2 else None

                        snapshot = ArchiveSnapshot(
                            timestamp=timestamp,
                            url=f"https://web.archive.org/web/{timestamp}/{original_url}",
                            status=status
                        )
                        snapshots.append(snapshot)

                        # 첫 번째/마지막 타임스탬프 추적
                        if first_timestamp is None or timestamp < first_timestamp:
                            first_timestamp = timestamp
                        if last_timestamp is None or timestamp > last_timestamp:
                            last_timestamp = timestamp

                return {
                    "snapshots": snapshots,
                    "first_seen": self._parse_timestamp(first_timestamp),
                    "last_seen": self._parse_timestamp(last_timestamp),
                }

        except Exception as e:
            logger.debug("cdx_query_error", domain=domain, error=str(e))

        return None

    def _parse_timestamp(self, timestamp: Optional[str]) -> Optional[date]:
        """Wayback Machine 타임스탬프 파싱"""
        if not timestamp or len(timestamp) < 8:
            return None
        try:
            return datetime.strptime(timestamp[:8], "%Y%m%d").date()
        except ValueError:
            return None

    def _analyze_content_type(self, snapshots: List[ArchiveSnapshot]) -> str:
        """스냅샷으로부터 이전 콘텐츠 타입 추론"""
        # 상태 코드 분석
        status_codes = [s.status for s in snapshots if s.status]

        if not status_codes:
            return "unknown"

        # 200 응답 비율
        ok_count = sum(1 for s in status_codes if s == "200")
        redirect_count = sum(1 for s in status_codes if s and s.startswith("3"))

        if ok_count > len(status_codes) * 0.7:
            return "active_website"
        elif redirect_count > len(status_codes) * 0.5:
            return "redirect/parked"
        else:
            return "mixed"

    async def check_batch(
        self,
        domains: List[str],
        concurrency: int = 3,
        delay: float = 1.0
    ) -> List[DomainHistory]:
        """
        여러 도메인 일괄 히스토리 확인

        Args:
            domains: 도메인 리스트
            concurrency: 동시 요청 수 (Archive.org는 rate limit이 엄격함)
            delay: 요청 간 딜레이

        Returns:
            DomainHistory 리스트
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

        final_results = []
        for domain, result in zip(domains, results):
            if isinstance(result, Exception):
                final_results.append(DomainHistory(
                    domain=domain,
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def get_screenshot_url(self, domain: str, timestamp: Optional[str] = None) -> Optional[str]:
        """
        스크린샷 URL 생성

        Args:
            domain: 도메인
            timestamp: 특정 시점 (없으면 최신)

        Returns:
            스크린샷 URL
        """
        if timestamp:
            return f"https://web.archive.org/web/{timestamp}im_/{domain}"
        else:
            return f"https://web.archive.org/web/2im_/{domain}"


class DomainAgeScorer:
    """도메인 연령 기반 추가 점수"""

    @staticmethod
    def calculate_score(history: DomainHistory) -> int:
        """
        도메인 히스토리 기반 점수 계산

        Args:
            history: DomainHistory

        Returns:
            추가 점수 (0-20)
        """
        score = 0

        if not history.has_history:
            return 0

        # 1. 연령 점수 (최대 10점)
        age_years = history.age_years
        if age_years:
            if age_years >= 15:
                score += 10
            elif age_years >= 10:
                score += 8
            elif age_years >= 5:
                score += 6
            elif age_years >= 3:
                score += 4
            elif age_years >= 1:
                score += 2

        # 2. 스냅샷 수 점수 (최대 5점)
        if history.snapshot_count >= 100:
            score += 5
        elif history.snapshot_count >= 50:
            score += 4
        elif history.snapshot_count >= 20:
            score += 3
        elif history.snapshot_count >= 10:
            score += 2
        elif history.snapshot_count >= 5:
            score += 1

        # 3. 콘텐츠 타입 점수 (최대 5점)
        if history.previous_content_type == "active_website":
            score += 5  # 활성 웹사이트였음
        elif history.previous_content_type == "redirect/parked":
            score += 2  # 파킹/리다이렉트
        elif history.previous_content_type == "mixed":
            score += 3

        return min(score, 20)  # 최대 20점


# 테스트
if __name__ == "__main__":
    async def test():
        print("=== Domain History Checker Test ===\n")

        checker = DomainHistoryChecker()
        scorer = DomainAgeScorer()

        # 테스트 도메인
        test_domains = ["example.com", "google.com"]

        for domain in test_domains:
            print(f"Checking history: {domain}")
            history = await checker.check(domain)

            print(f"  Has History: {history.has_history}")
            if history.has_history:
                print(f"  First Seen: {history.first_seen}")
                print(f"  Last Seen: {history.last_seen}")
                print(f"  Snapshot Count: {history.snapshot_count}")
                print(f"  Age (years): {history.age_years:.1f}" if history.age_years else "  Age: N/A")
                print(f"  Content Type: {history.previous_content_type}")
                print(f"  History Score: +{scorer.calculate_score(history)}")
            if history.error:
                print(f"  Error: {history.error}")
            print()

    asyncio.run(test())
