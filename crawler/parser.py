"""
Domain Sniper - 도메인 파서
크롤링된 HTML에서 도메인 정보를 추출합니다.
"""

import re
from datetime import date, timedelta
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


class DomainParser:
    """도메인 파싱 유틸리티"""

    # 지원하는 TLD
    SUPPORTED_TLDS = {"com", "net", "io", "co", "kr", "org", "ai", "app", "dev"}

    # 제외할 키워드 (성인/스팸)
    BLOCKED_KEYWORDS = {
        "porn", "xxx", "sex", "adult", "nude", "naked", "pussy", "cock",
        "fuck", "shit", "ass", "bitch", "damn", "cunt", "dick", "horny",
        "casino", "gambling", "bet", "poker", "slot", "viagra", "cialis",
        "pharmacy", "pills", "drug", "weed", "marijuana"
    }

    @classmethod
    def parse_domain_name(cls, full_domain: str) -> Optional[Tuple[str, str]]:
        """
        도메인 이름 파싱

        Args:
            full_domain: 전체 도메인 (예: example.com)

        Returns:
            (name, tld) 튜플 또는 None
        """
        if not full_domain:
            return None

        # 정규화
        full_domain = full_domain.lower().strip()

        # www. 제거
        if full_domain.startswith("www."):
            full_domain = full_domain[4:]

        # http(s):// 제거
        full_domain = re.sub(r"^https?://", "", full_domain)

        # 경로 제거
        full_domain = full_domain.split("/")[0]

        # 도메인과 TLD 분리
        parts = full_domain.rsplit(".", 1)
        if len(parts) != 2:
            return None

        name, tld = parts

        # 2단계 TLD 처리 (co.kr 등)
        if tld == "kr" and name.endswith(".co"):
            name = name[:-3]
            tld = "co.kr"

        return name, tld

    @classmethod
    def is_valid_domain(
        cls,
        name: str,
        tld: str,
        min_length: int = 3,
        max_length: int = 12,
        allowed_tlds: Optional[List[str]] = None,
        allow_numbers: bool = False,
        allow_hyphens: bool = False
    ) -> bool:
        """
        도메인 유효성 검사

        Args:
            name: 도메인 이름
            tld: TLD
            min_length: 최소 길이
            max_length: 최대 길이
            allowed_tlds: 허용 TLD 목록
            allow_numbers: 숫자 허용 여부
            allow_hyphens: 하이픈 허용 여부

        Returns:
            유효하면 True
        """
        # 길이 검사
        if len(name) < min_length or len(name) > max_length:
            return False

        # TLD 검사
        if allowed_tlds:
            if tld not in allowed_tlds:
                return False
        elif tld not in cls.SUPPORTED_TLDS:
            return False

        # 숫자 검사
        if not allow_numbers and any(c.isdigit() for c in name):
            return False

        # 하이픈 검사
        if not allow_hyphens and "-" in name:
            return False

        # 차단 키워드 검사
        name_lower = name.lower()
        for keyword in cls.BLOCKED_KEYWORDS:
            if keyword in name_lower:
                return False

        # 유효한 문자만 포함 (알파벳, 숫자, 하이픈)
        if not re.match(r"^[a-z0-9-]+$", name_lower):
            return False

        # 시작/끝 하이픈 금지
        if name.startswith("-") or name.endswith("-"):
            return False

        return True

    @classmethod
    def parse_expireddomains_html(cls, html: str) -> List[dict]:
        """
        expireddomains.net HTML 파싱

        Args:
            html: HTML 문자열

        Returns:
            도메인 정보 리스트
        """
        domains = []
        soup = BeautifulSoup(html, "lxml")

        # 다양한 테이블 구조 시도
        table = None

        # 1. 기존 방식: class="base1"
        table = soup.find("table", class_="base1")

        # 2. 새로운 방식: class 포함 "domain" 테이블
        if not table:
            table = soup.find("table", id="table")

        # 3. 첫 번째 테이블 시도
        if not table:
            tables = soup.find_all("table")
            for t in tables:
                # 도메인 링크가 있는 테이블 찾기
                if t.find("a", class_="namemark") or t.find("a", title=True):
                    table = t
                    break

        if not table:
            # 디버그: 페이지에 로그인 필요 메시지가 있는지 확인
            page_text = soup.get_text().lower()
            if "login" in page_text and "please" in page_text:
                logger.warning("domain_table_not_found", reason="login_required")
            else:
                logger.warning("domain_table_not_found", reason="table_not_found")
            return domains

        # 테이블 행 찾기 - 다양한 방식 시도
        rows = table.find_all("tr", class_="base1")
        if not rows:
            rows = table.find_all("tr")[1:]  # 헤더 제외

        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                # 도메인 이름 추출 - 여러 방식 시도
                domain_cell = cells[0]
                domain_link = domain_cell.find("a", class_="namemark")  # 원래 클래스
                if not domain_link:
                    domain_link = domain_cell.find("a", class_="field_domain")
                if not domain_link:
                    domain_link = domain_cell.find("a", title=True)
                if not domain_link:
                    domain_link = domain_cell.find("a")
                if not domain_link:
                    continue

                full_name = domain_link.get_text(strip=True)
                if not full_name or "." not in full_name:
                    continue
                parsed = cls.parse_domain_name(full_name)
                if not parsed:
                    continue

                name, tld = parsed

                # 만료일 추출 (예: "2 days" 형식)
                expiry_text = ""
                for cell in cells:
                    text = cell.get_text(strip=True)
                    if "day" in text.lower() or "hour" in text.lower():
                        expiry_text = text
                        break

                expiry_date = cls._parse_expiry_text(expiry_text)

                domains.append({
                    "name": name,
                    "tld": tld,
                    "full_name": f"{name}.{tld}",
                    "length": len(name),
                    "expiry_date": expiry_date,
                    "source": "expireddomains.net"
                })

            except Exception as e:
                logger.warning("row_parse_error", error=str(e))
                continue

        logger.info("html_parsed", domain_count=len(domains))
        return domains

    @classmethod
    def _parse_expiry_text(cls, text: str) -> Optional[date]:
        """
        만료 텍스트를 날짜로 변환

        Args:
            text: "2 days", "5 hours" 등

        Returns:
            만료 예정일
        """
        if not text:
            return None

        text = text.lower().strip()
        today = date.today()

        # "X days" 패턴
        days_match = re.search(r"(\d+)\s*day", text)
        if days_match:
            days = int(days_match.group(1))
            return today + timedelta(days=days)

        # "X hours" 패턴 (오늘로 처리)
        hours_match = re.search(r"(\d+)\s*hour", text)
        if hours_match:
            return today

        # "today" 패턴
        if "today" in text:
            return today

        # "tomorrow" 패턴
        if "tomorrow" in text:
            return today + timedelta(days=1)

        return None

    @classmethod
    def parse_parkio_json(cls, data: dict) -> List[dict]:
        """
        park.io API JSON 파싱

        Args:
            data: API 응답 JSON

        Returns:
            도메인 정보 리스트
        """
        domains = []

        if "domains" not in data:
            return domains

        for item in data["domains"]:
            try:
                full_name = item.get("name", "")
                parsed = cls.parse_domain_name(full_name)
                if not parsed:
                    continue

                name, tld = parsed

                # 만료일
                expiry_str = item.get("expiry_date") or item.get("drop_date")
                expiry_date = None
                if expiry_str:
                    try:
                        expiry_date = date.fromisoformat(expiry_str[:10])
                    except ValueError:
                        pass

                domains.append({
                    "name": name,
                    "tld": tld,
                    "full_name": f"{name}.{tld}",
                    "length": len(name),
                    "expiry_date": expiry_date,
                    "source": "park.io",
                    "auction_url": item.get("auction_url", "")
                })

            except Exception as e:
                logger.warning("parkio_parse_error", error=str(e))
                continue

        return domains


# 테스트
if __name__ == "__main__":
    # 파싱 테스트
    test_domains = [
        "example.com",
        "www.test.net",
        "https://startup.io/path",
        "my-domain.co.kr",
        "12345.com",
        "bad-porn-site.com"
    ]

    for domain in test_domains:
        result = DomainParser.parse_domain_name(domain)
        if result:
            name, tld = result
            is_valid = DomainParser.is_valid_domain(name, tld)
            print(f"{domain} -> {name}.{tld} (valid: {is_valid})")
        else:
            print(f"{domain} -> 파싱 실패")
