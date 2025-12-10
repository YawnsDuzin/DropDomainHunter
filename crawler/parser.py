"""
Domain Sniper - 도메인 파서
크롤링된 HTML에서 도메인 정보를 추출합니다.
다중 파싱 전략으로 사이트 변경에 강건하게 대응합니다.
"""

import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any, Callable
from bs4 import BeautifulSoup, Tag
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class ParsingStrategy(Enum):
    """파싱 전략 타입"""
    CLASS_BASED = "class_based"
    STRUCTURE_BASED = "structure_based"
    REGEX_BASED = "regex_based"
    HYBRID = "hybrid"


@dataclass
class ParsingResult:
    """파싱 결과"""
    domains: List[Dict[str, Any]]
    strategy_used: ParsingStrategy
    confidence: float  # 0.0 ~ 1.0
    warnings: List[str]


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

        # 1. 멤버 영역: class="base1" 테이블 (가장 일반적)
        table = soup.find("table", class_="base1")

        # 2. 멤버 영역: id="table" 또는 class="domainlist"
        if not table:
            table = soup.find("table", id="table")

        if not table:
            table = soup.find("table", class_="domainlist")

        # 3. tbody 내 도메인 테이블 찾기
        if not table:
            # content div 내 테이블 찾기
            content = soup.find("div", id="content")
            if content:
                table = content.find("table")

        # 4. 첫 번째 테이블에서 도메인 링크 찾기
        if not table:
            tables = soup.find_all("table")
            for t in tables:
                # 도메인 링크가 있는 테이블 찾기
                if t.find("a", class_="field_domain") or t.find("a", class_="namemark") or t.find("td", class_="field_domain"):
                    table = t
                    break

        if not table:
            # 디버그: 페이지에 로그인 필요 메시지가 있는지 확인
            page_text = soup.get_text().lower()
            if "login" in page_text and "please" in page_text:
                logger.warning("domain_table_not_found", reason="login_required")
            elif "no domains found" in page_text or "no results" in page_text:
                logger.info("domain_table_not_found", reason="no_results")
            else:
                logger.warning("domain_table_not_found", reason="table_not_found")
            return domains

        # 테이블 행 찾기 - 다양한 방식 시도
        rows = table.find_all("tr", class_="base1")
        if not rows:
            rows = table.find_all("tr", class_=re.compile(r"row"))  # row0, row1 등
        if not rows:
            rows = table.find_all("tr")[1:]  # 헤더 제외

        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                # 도메인 이름 추출 - 여러 방식 시도
                full_name = None

                # 방식 1: field_domain 클래스가 있는 td에서 찾기
                domain_cell = row.find("td", class_="field_domain")
                if domain_cell:
                    domain_link = domain_cell.find("a")
                    if domain_link:
                        full_name = domain_link.get_text(strip=True)

                # 방식 2: 첫 번째 td에서 a 태그 찾기
                if not full_name:
                    domain_cell = cells[0]
                    domain_link = domain_cell.find("a", class_="namemark")  # 원래 클래스
                    if not domain_link:
                        domain_link = domain_cell.find("a", class_="field_domain")
                    if not domain_link:
                        domain_link = domain_cell.find("a", title=True)
                    if not domain_link:
                        domain_link = domain_cell.find("a")
                    if domain_link:
                        full_name = domain_link.get_text(strip=True)

                # 방식 3: 행에서 .com, .net 등이 포함된 텍스트 찾기
                if not full_name:
                    row_text = row.get_text()
                    domain_match = re.search(r'([a-zA-Z0-9-]+\.(?:com|net|org|io|ai|co|kr|app|dev|info|biz))', row_text)
                    if domain_match:
                        full_name = domain_match.group(1)

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
        만료 텍스트를 날짜로 변환 (개선된 버전)

        Args:
            text: "2 days", "5 hours", "Jan 15, 2024" 등

        Returns:
            만료 예정일
        """
        if not text:
            return None

        text_clean = text.lower().strip()
        today = date.today()

        # "X days" 패턴
        days_match = re.search(r"(\d+)\s*day", text_clean)
        if days_match:
            days = int(days_match.group(1))
            return today + timedelta(days=days)

        # "X hours" 패턴 (오늘로 처리)
        hours_match = re.search(r"(\d+)\s*hour", text_clean)
        if hours_match:
            return today

        # "X weeks" 패턴
        weeks_match = re.search(r"(\d+)\s*week", text_clean)
        if weeks_match:
            weeks = int(weeks_match.group(1))
            return today + timedelta(weeks=weeks)

        # "X months" 패턴
        months_match = re.search(r"(\d+)\s*month", text_clean)
        if months_match:
            months = int(months_match.group(1))
            return today + timedelta(days=months * 30)

        # "today" 패턴
        if "today" in text_clean:
            return today

        # "tomorrow" 패턴
        if "tomorrow" in text_clean:
            return today + timedelta(days=1)

        # 날짜 형식 파싱 시도
        return cls._parse_date_string(text)

    @classmethod
    def _parse_date_string(cls, text: str) -> Optional[date]:
        """
        다양한 날짜 형식 파싱

        Args:
            text: 날짜 문자열

        Returns:
            date 객체 또는 None
        """
        if not text:
            return None

        # 공백 정규화
        text = " ".join(text.split())

        # 다양한 날짜 형식
        date_formats = [
            # ISO 형식
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",

            # 영문 형식
            "%b %d, %Y",      # Jan 15, 2024
            "%B %d, %Y",      # January 15, 2024
            "%d %b %Y",       # 15 Jan 2024
            "%d %B %Y",       # 15 January 2024
            "%b %d %Y",       # Jan 15 2024
            "%d-%b-%Y",       # 15-Jan-2024

            # 숫자 형식
            "%m/%d/%Y",       # 01/15/2024
            "%d/%m/%Y",       # 15/01/2024
            "%Y/%m/%d",       # 2024/01/15
            "%m-%d-%Y",       # 01-15-2024
            "%d.%m.%Y",       # 15.01.2024
            "%Y.%m.%d",       # 2024.01.15
        ]

        # 시간대 정보 제거
        text_clean = re.sub(r'\s*[+-]\d{2}:?\d{2}$', '', text)
        text_clean = text_clean.replace('Z', '').strip()

        for fmt in date_formats:
            try:
                return datetime.strptime(text_clean, fmt).date()
            except ValueError:
                continue

        # 날짜만 추출 시도 (YYYY-MM-DD 패턴)
        iso_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
        if iso_match:
            try:
                return date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3))
                )
            except ValueError:
                pass

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


class RobustParser:
    """
    강건한 도메인 파서
    여러 파싱 전략을 순차적으로 시도하여 HTML 구조 변경에 대응합니다.
    """

    # 도메인 패턴 (정규표현식)
    DOMAIN_PATTERN = re.compile(
        r'([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)'
        r'\.'
        r'(com|net|org|io|ai|co|kr|app|dev|info|biz|me|cc|tv|xyz|online|site|tech|store)',
        re.IGNORECASE
    )

    # 테이블 감지를 위한 클래스/ID 패턴
    TABLE_IDENTIFIERS = [
        # 클래스명
        {"class_": "base1"},
        {"class_": "domainlist"},
        {"class_": "domain-list"},
        {"class_": "results"},
        {"class_": "expired-domains"},
        {"class_": re.compile(r"domain.*table", re.I)},
        {"class_": re.compile(r"table.*domain", re.I)},
        # ID
        {"id": "table"},
        {"id": "domaintable"},
        {"id": "results"},
        {"id": "domain-list"},
    ]

    # 행 감지를 위한 클래스 패턴
    ROW_IDENTIFIERS = [
        {"class_": "base1"},
        {"class_": re.compile(r"row\d*")},
        {"class_": re.compile(r"domain.*row", re.I)},
        {"class_": re.compile(r"result.*row", re.I)},
    ]

    def __init__(self):
        self.basic_parser = DomainParser()
        self._last_strategy: Optional[ParsingStrategy] = None

    def parse(self, html: str, source: str = "unknown") -> ParsingResult:
        """
        다중 전략으로 HTML 파싱

        Args:
            html: HTML 문자열
            source: 데이터 소스명

        Returns:
            ParsingResult
        """
        warnings = []

        # 전략 1: 클래스 기반 파싱 (가장 정확)
        result = self._parse_by_class(html, source)
        if result and len(result) > 0:
            self._last_strategy = ParsingStrategy.CLASS_BASED
            return ParsingResult(
                domains=result,
                strategy_used=ParsingStrategy.CLASS_BASED,
                confidence=0.95,
                warnings=warnings
            )
        warnings.append("Class-based parsing failed")

        # 전략 2: HTML 구조 기반 파싱
        result = self._parse_by_structure(html, source)
        if result and len(result) > 0:
            self._last_strategy = ParsingStrategy.STRUCTURE_BASED
            return ParsingResult(
                domains=result,
                strategy_used=ParsingStrategy.STRUCTURE_BASED,
                confidence=0.8,
                warnings=warnings
            )
        warnings.append("Structure-based parsing failed")

        # 전략 3: 정규표현식 기반 파싱 (최후의 수단)
        result = self._parse_by_regex(html, source)
        if result and len(result) > 0:
            self._last_strategy = ParsingStrategy.REGEX_BASED
            return ParsingResult(
                domains=result,
                strategy_used=ParsingStrategy.REGEX_BASED,
                confidence=0.5,
                warnings=warnings
            )
        warnings.append("Regex-based parsing failed")

        # 모든 전략 실패
        logger.error("all_parsing_strategies_failed", source=source)
        return ParsingResult(
            domains=[],
            strategy_used=ParsingStrategy.HYBRID,
            confidence=0.0,
            warnings=warnings
        )

    def _parse_by_class(self, html: str, source: str) -> List[Dict[str, Any]]:
        """클래스명 기반 파싱"""
        soup = BeautifulSoup(html, "lxml")
        domains = []

        # 테이블 찾기
        table = None
        for identifier in self.TABLE_IDENTIFIERS:
            table = soup.find("table", identifier)
            if table:
                logger.debug("table_found_by_class", identifier=str(identifier))
                break

        if not table:
            return []

        # 행 찾기
        rows = []
        for identifier in self.ROW_IDENTIFIERS:
            rows = table.find_all("tr", identifier)
            if rows:
                break

        if not rows:
            rows = table.find_all("tr")[1:]  # 헤더 제외

        # 도메인 추출
        for row in rows:
            domain_data = self._extract_domain_from_row(row, source)
            if domain_data:
                domains.append(domain_data)

        return domains

    def _parse_by_structure(self, html: str, source: str) -> List[Dict[str, Any]]:
        """HTML 구조 기반 파싱"""
        soup = BeautifulSoup(html, "lxml")
        domains = []

        # 모든 테이블 검사
        tables = soup.find_all("table")

        for table in tables:
            # 도메인 링크가 있는 테이블인지 확인
            if self._looks_like_domain_table(table):
                rows = table.find_all("tr")[1:]  # 헤더 제외

                for row in rows:
                    domain_data = self._extract_domain_from_row(row, source)
                    if domain_data:
                        domains.append(domain_data)

                if domains:
                    break

        return domains

    def _parse_by_regex(self, html: str, source: str) -> List[Dict[str, Any]]:
        """정규표현식 기반 파싱"""
        domains = []
        seen = set()

        # HTML 태그 제거
        text = BeautifulSoup(html, "lxml").get_text()

        # 도메인 패턴 매칭
        matches = self.DOMAIN_PATTERN.findall(text)

        for name, tld in matches:
            name = name.lower()
            tld = tld.lower()
            full_name = f"{name}.{tld}"

            # 중복 제거
            if full_name in seen:
                continue
            seen.add(full_name)

            # 유효성 검사
            if self.basic_parser.is_valid_domain(name, tld):
                domains.append({
                    "name": name,
                    "tld": tld,
                    "full_name": full_name,
                    "length": len(name),
                    "expiry_date": None,
                    "source": source,
                })

        return domains

    def _looks_like_domain_table(self, table: Tag) -> bool:
        """테이블이 도메인 리스트인지 확인"""
        # 테이블 내 텍스트에서 도메인 패턴 검색
        text = table.get_text()
        matches = self.DOMAIN_PATTERN.findall(text)

        # 3개 이상의 도메인이 있으면 도메인 테이블로 판단
        if len(matches) >= 3:
            return True

        # 도메인 관련 클래스가 있는지 확인
        domain_classes = ["domain", "name", "field_domain", "namemark"]
        for cls in domain_classes:
            if table.find(class_=re.compile(cls, re.I)):
                return True

        return False

    def _extract_domain_from_row(self, row: Tag, source: str) -> Optional[Dict[str, Any]]:
        """테이블 행에서 도메인 정보 추출"""
        cells = row.find_all("td")
        if len(cells) < 1:
            return None

        full_name = None
        expiry_text = ""

        # 1. 링크에서 도메인 추출
        for cell in cells:
            link = cell.find("a")
            if link:
                text = link.get_text(strip=True)
                if self.DOMAIN_PATTERN.match(text):
                    full_name = text
                    break

        # 2. 도메인 클래스 셀에서 추출
        if not full_name:
            domain_cell = row.find("td", class_=re.compile(r"domain|name", re.I))
            if domain_cell:
                link = domain_cell.find("a")
                if link:
                    full_name = link.get_text(strip=True)
                else:
                    # 텍스트에서 직접 추출
                    text = domain_cell.get_text(strip=True)
                    match = self.DOMAIN_PATTERN.search(text)
                    if match:
                        full_name = f"{match.group(1)}.{match.group(2)}"

        # 3. 행 전체 텍스트에서 도메인 추출
        if not full_name:
            row_text = row.get_text()
            match = self.DOMAIN_PATTERN.search(row_text)
            if match:
                full_name = f"{match.group(1)}.{match.group(2)}"

        if not full_name:
            return None

        # 도메인 파싱
        parsed = self.basic_parser.parse_domain_name(full_name)
        if not parsed:
            return None

        name, tld = parsed

        # 유효성 검사
        if not self.basic_parser.is_valid_domain(name, tld):
            return None

        # 만료일 추출
        for cell in cells:
            text = cell.get_text(strip=True).lower()
            if any(kw in text for kw in ["day", "hour", "week", "month", "expire", "drop"]):
                expiry_text = text
                break

        expiry_date = self.basic_parser._parse_expiry_text(expiry_text)

        return {
            "name": name,
            "tld": tld,
            "full_name": f"{name}.{tld}",
            "length": len(name),
            "expiry_date": expiry_date,
            "source": source,
        }

    @property
    def last_strategy(self) -> Optional[ParsingStrategy]:
        """마지막 사용된 파싱 전략"""
        return self._last_strategy


class SmartKeywordMatcher:
    """
    향상된 키워드 매칭
    단순 포함 검사 대신 단어 경계를 고려한 매칭
    """

    # 오탐 방지를 위한 예외 목록 (키워드가 다른 단어의 일부인 경우)
    EXCEPTION_PATTERNS = {
        "ai": [r"again", r"rain", r"main", r"gain", r"fair", r"air", r"wait", r"tail"],
        "ass": [r"class", r"pass", r"mass", r"bass", r"assess", r"assist", r"asset"],
        "bit": [r"habit", r"rabbit", r"orbit"],
        "car": [r"scare", r"care", r"card", r"oscar"],
        "sex": [r"essex", r"sussex"],
    }

    @classmethod
    def is_keyword_match(cls, domain_name: str, keyword: str) -> bool:
        """
        키워드가 도메인에 의미있게 포함되어 있는지 확인

        Args:
            domain_name: 도메인 이름
            keyword: 검색 키워드

        Returns:
            매칭 여부
        """
        domain_lower = domain_name.lower()
        keyword_lower = keyword.lower()

        # 기본 포함 검사
        if keyword_lower not in domain_lower:
            return False

        # 예외 패턴 검사
        if keyword_lower in cls.EXCEPTION_PATTERNS:
            for exception in cls.EXCEPTION_PATTERNS[keyword_lower]:
                if re.search(exception, domain_lower):
                    return False

        # 단어 경계 검사 (선택적)
        # 키워드가 도메인 시작/끝에 있거나, 숫자/하이픈으로 구분되어 있으면 매칭
        patterns = [
            rf"^{re.escape(keyword_lower)}",  # 시작
            rf"{re.escape(keyword_lower)}$",  # 끝
            rf"{re.escape(keyword_lower)}[0-9-]",  # 키워드 뒤에 숫자/하이픈
            rf"[0-9-]{re.escape(keyword_lower)}",  # 키워드 앞에 숫자/하이픈
        ]

        # 3글자 이하 키워드는 경계 검사 필요
        if len(keyword_lower) <= 3:
            for pattern in patterns:
                if re.search(pattern, domain_lower):
                    return True
            # 경계에 없으면 매칭하지 않음
            return False

        # 4글자 이상 키워드는 포함만으로 매칭
        return True


# 테스트
if __name__ == "__main__":
    print("=== Domain Parser Test ===\n")

    # 기본 파싱 테스트
    test_domains = [
        "example.com",
        "www.test.net",
        "https://startup.io/path",
        "my-domain.co.kr",
        "12345.com",
        "bad-porn-site.com"
    ]

    print("1. Basic Domain Parsing:")
    for domain in test_domains:
        result = DomainParser.parse_domain_name(domain)
        if result:
            name, tld = result
            is_valid = DomainParser.is_valid_domain(name, tld)
            print(f"   {domain} -> {name}.{tld} (valid: {is_valid})")
        else:
            print(f"   {domain} -> 파싱 실패")

    # 날짜 파싱 테스트
    print("\n2. Date Parsing:")
    test_dates = [
        "2 days",
        "5 hours",
        "Jan 15, 2024",
        "2024-01-15",
        "15/01/2024",
        "3 weeks",
        "today",
    ]
    for date_str in test_dates:
        result = DomainParser._parse_expiry_text(date_str)
        print(f"   '{date_str}' -> {result}")

    # 키워드 매칭 테스트
    print("\n3. Smart Keyword Matching:")
    test_cases = [
        ("aicloud", "ai"),
        ("again", "ai"),
        ("classic", "ass"),
        ("asset", "ass"),
        ("sexshop", "sex"),
        ("essex", "sex"),
    ]
    for domain, keyword in test_cases:
        result = SmartKeywordMatcher.is_keyword_match(domain, keyword)
        print(f"   '{keyword}' in '{domain}' -> {result}")
