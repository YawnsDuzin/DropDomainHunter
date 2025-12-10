# 🔍 Domain Sniper 문제점 분석 및 개선 제안

## 목차

1. [현재 시스템의 문제점](#1-현재-시스템의-문제점)
2. [크롤링 차단 방지 전략](#2-크롤링-차단-방지-전략)
3. [필수 개선 사항](#3-필수-개선-사항)
4. [추가 기능 제안](#4-추가-기능-제안)
5. [성능 최적화](#5-성능-최적화)
6. [보안 강화](#6-보안-강화)
7. [구현 우선순위](#7-구현-우선순위)

---

## 1. 현재 시스템의 문제점

### 1.1 🚨 심각한 문제점

#### 1.1.1 도메인 등록 가능 여부 미확인

**현재 상태:**
- 크롤링된 도메인이 실제로 등록 가능한지 확인하지 않음
- 이미 다른 사람이 등록한 도메인도 알림 발송
- 사용자가 직접 각 도메인을 확인해야 함

**문제점:**
```
크롤링 → 평가 → 알림
         ↓
    등록 가능 여부 확인 없음 ❌
```

**영향:**
- 불필요한 알림 발생
- 사용자 시간 낭비
- 신뢰도 저하

---

#### 1.1.2 HTML 파서 취약성

**현재 상태:**
```python
# parser.py
table = soup.find("table", class_="base1")
rows = table.find_all("tr", class_="base1")
domain_link = domain_cell.find("a", class_="namemark")
```

**문제점:**
- expireddomains.net의 HTML 구조 변경 시 전체 파싱 실패
- 클래스명 하드코딩
- 사이트 업데이트에 취약

---

#### 1.1.3 단일 크롤링 소스 의존

**현재 상태:**
- expireddomains.net만 사용
- 해당 사이트 접근 불가 시 전체 서비스 중단

**리스크:**
- 사이트 차단 시 서비스 불가
- 데이터 다양성 부족
- 누락 도메인 발생

---

#### 1.1.4 Rate Limiting 취약

**현재 상태:**
```python
# 고정 딜레이만 사용
await asyncio.sleep(settings.request_delay + random.uniform(0, 1))
# 2~3초 고정 딜레이
```

**문제점:**
- 429 에러 발생 시 60초 대기 후 종료
- 동적 Rate Limiting 없음
- IP 차단 가능성

---

### 1.2 ⚠️ 중요한 문제점

#### 1.2.1 만료일 파싱 부정확

**현재 상태:**
```python
def _parse_expiry_text(text):
    # "X days" 또는 "X hours" 패턴만 처리
    days_match = re.search(r"(\d+)\s*day", text)
```

**문제점:**
- 다양한 날짜 형식 미지원 ("Jan 15, 2024" 등)
- 시간대 미고려
- 파싱 실패 시 None 반환

---

#### 1.2.2 점수 알고리즘 한계

**현재 상태:**
- 키워드 매칭이 단순 포함 검사
- 영어 키워드만 지원
- 트렌드/시장 데이터 미반영

**예시 문제:**
```python
# "assessment"에서 "ass" 키워드 매칭 → 차단됨 (오탐)
# "ai" 매칭은 "rain", "again" 등에서도 발생 (오탐)
```

---

#### 1.2.3 에러 핸들링 미흡

**현재 상태:**
```python
except Exception as e:
    logger.error("crawl_error", error=str(e))
    break  # 단순 종료
```

**문제점:**
- 상세 에러 분류 없음
- 복구 메커니즘 부재
- 부분 실패 처리 미흡

---

#### 1.2.4 Telegram 콜백 미구현

**현재 상태:**
```python
# 인라인 버튼은 생성되지만 콜백 핸들러 없음
InlineKeyboardButton("⭐ 관심등록", callback_data="watch:123")
```

**문제점:**
- 버튼 클릭 시 응답 없음
- 사용자 경험 저하

---

### 1.3 💡 개선 필요 사항

#### 1.3.1 WHOIS 정보 미활용

- 도메인 나이 정보 없음
- 이전 소유자 정보 없음
- 히스토리 데이터 없음

#### 1.3.2 백링크/SEO 데이터 없음

- Moz DA/PA 미확인
- 백링크 수 미확인
- Google 인덱스 상태 미확인

#### 1.3.3 가격 예측 정확도

- 실제 거래 데이터 기반 아님
- 단순 규칙 기반 추정
- 시장 상황 미반영

---

## 2. 크롤링 차단 방지 전략

### 2.1 현재 차단 위험 요소

| 요소 | 현재 상태 | 위험도 |
|-----|---------|-------|
| User-Agent | 고정값 | 🔴 높음 |
| 요청 간격 | 2~3초 고정 | 🟡 중간 |
| IP 주소 | 단일 IP | 🔴 높음 |
| 세션 관리 | 없음 | 🟡 중간 |
| 쿠키 처리 | 없음 | 🟡 중간 |
| Fingerprint | 고정 | 🔴 높음 |

### 2.2 개선 방안

#### 2.2.1 User-Agent 로테이션

```python
# 제안: 다양한 User-Agent 사용
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36...",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36...",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101...",
    # ... 20개 이상
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)
```

#### 2.2.2 동적 딜레이

```python
# 제안: 적응형 딜레이
class AdaptiveDelay:
    def __init__(self):
        self.base_delay = 2.0
        self.max_delay = 60.0
        self.current_delay = self.base_delay
        self.consecutive_errors = 0

    async def wait(self):
        # 랜덤 지터 추가
        jitter = random.uniform(0.5, 2.0)
        await asyncio.sleep(self.current_delay * jitter)

    def on_success(self):
        # 성공 시 딜레이 감소
        self.current_delay = max(self.base_delay, self.current_delay * 0.9)
        self.consecutive_errors = 0

    def on_error(self, status_code):
        # 에러 시 딜레이 증가
        if status_code == 429:
            self.current_delay = min(self.max_delay, self.current_delay * 3)
        else:
            self.current_delay = min(self.max_delay, self.current_delay * 1.5)
        self.consecutive_errors += 1
```

#### 2.2.3 프록시 로테이션

```python
# 제안: 프록시 풀 사용
class ProxyRotator:
    def __init__(self, proxy_list: List[str]):
        self.proxies = proxy_list
        self.current_index = 0
        self.failed_proxies = set()

    def get_proxy(self) -> Optional[str]:
        available = [p for p in self.proxies if p not in self.failed_proxies]
        if not available:
            self.failed_proxies.clear()  # 리셋
            available = self.proxies

        proxy = random.choice(available)
        return {"http://": proxy, "https://": proxy}

    def mark_failed(self, proxy: str):
        self.failed_proxies.add(proxy)

# 무료 프록시 소스
# - https://free-proxy-list.net/
# - https://www.sslproxies.org/
# 유료 프록시 서비스 권장
# - Bright Data, Oxylabs, SmartProxy
```

#### 2.2.4 세션 및 쿠키 관리

```python
# 제안: 브라우저처럼 동작
class BrowserSession:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.cookies = {}

    async def init_session(self, client: httpx.AsyncClient):
        # 먼저 메인 페이지 방문하여 쿠키 획득
        response = await client.get("https://www.expireddomains.net/")
        self.cookies = dict(response.cookies)

    def get_headers(self):
        return {
            "User-Agent": get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml...",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.expireddomains.net/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
```

#### 2.2.5 요청 패턴 자연화

```python
# 제안: 인간처럼 행동
class HumanBehavior:
    @staticmethod
    async def random_pause():
        """사람처럼 불규칙한 대기"""
        # 가끔 긴 휴식
        if random.random() < 0.1:
            await asyncio.sleep(random.uniform(30, 60))
        # 일반 대기
        else:
            await asyncio.sleep(random.uniform(2, 8))

    @staticmethod
    def should_take_break(requests_count: int) -> bool:
        """일정 요청 후 휴식"""
        # 20~30개 요청마다 5~10분 휴식
        if requests_count > 0 and requests_count % random.randint(20, 30) == 0:
            return True
        return False

    @staticmethod
    async def take_break():
        """긴 휴식"""
        await asyncio.sleep(random.uniform(300, 600))  # 5~10분
```

#### 2.2.6 분산 크롤링

```python
# 제안: 시간대 분산
class DistributedCrawling:
    @staticmethod
    def get_crawl_windows():
        """크롤링 시간대 분산"""
        return [
            (6, 8),    # 새벽 6-8시
            (12, 14),  # 점심 12-14시
            (20, 22),  # 저녁 20-22시
        ]

    @staticmethod
    def should_crawl_now() -> bool:
        hour = datetime.now().hour
        for start, end in DistributedCrawling.get_crawl_windows():
            if start <= hour < end:
                return True
        return False
```

---

## 3. 필수 개선 사항

### 3.1 도메인 등록 가능 여부 확인

#### 3.1.1 WHOIS 조회

```python
# 제안: python-whois 활용
import whois

class DomainAvailabilityChecker:
    async def is_available(self, domain: str) -> dict:
        """
        도메인 등록 가능 여부 확인

        Returns:
            {
                "available": bool,
                "status": str,  # available, registered, pending, reserved
                "registrar": str,
                "expiry_date": date,
                "creation_date": date,
            }
        """
        try:
            w = whois.whois(domain)

            if w.status is None or w.domain_name is None:
                return {"available": True, "status": "available"}

            return {
                "available": False,
                "status": "registered",
                "registrar": w.registrar,
                "expiry_date": w.expiration_date,
                "creation_date": w.creation_date,
            }
        except whois.parser.PywhoisError:
            return {"available": True, "status": "available"}
        except Exception as e:
            return {"available": None, "status": "error", "error": str(e)}
```

#### 3.1.2 RDAP 프로토콜 사용

```python
# 제안: RDAP API 활용 (더 정확하고 표준화됨)
import httpx

class RDAPChecker:
    RDAP_SERVERS = {
        "com": "https://rdap.verisign.com/com/v1/domain/",
        "net": "https://rdap.verisign.com/net/v1/domain/",
        "io": "https://rdap.nic.io/domain/",
        "co": "https://rdap.nic.co/domain/",
    }

    async def check(self, domain: str) -> dict:
        tld = domain.split(".")[-1]
        base_url = self.RDAP_SERVERS.get(tld)

        if not base_url:
            return {"available": None, "status": "unsupported_tld"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url}{domain}")

                if response.status_code == 404:
                    return {"available": True, "status": "available"}
                elif response.status_code == 200:
                    data = response.json()
                    return {
                        "available": False,
                        "status": "registered",
                        "events": data.get("events", []),
                    }
        except Exception as e:
            return {"available": None, "status": "error", "error": str(e)}
```

#### 3.1.3 레지스트라 API 활용

```python
# 제안: 레지스트라 API 직접 사용
class RegistrarAPI:
    """GoDaddy, Namecheap 등의 API 활용"""

    async def check_godaddy(self, domain: str, api_key: str) -> dict:
        """GoDaddy API"""
        url = f"https://api.godaddy.com/v1/domains/available?domain={domain}"
        headers = {"Authorization": f"sso-key {api_key}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            data = response.json()
            return {
                "available": data.get("available", False),
                "price": data.get("price"),
                "currency": data.get("currency"),
            }

    async def check_namecheap(self, domain: str, api_key: str, username: str) -> dict:
        """Namecheap API"""
        url = "https://api.namecheap.com/xml.response"
        params = {
            "ApiUser": username,
            "ApiKey": api_key,
            "UserName": username,
            "Command": "namecheap.domains.check",
            "DomainList": domain,
        }
        # ... XML 파싱
```

### 3.2 다중 크롤링 소스

```python
# 제안: 여러 소스 통합
class MultiSourceCrawler:
    def __init__(self):
        self.sources = [
            ExpiredDomainsCrawler(),
            ParkIOCrawler(),
            DropCatchCrawler(),
            NameJetCrawler(),
        ]

    async def crawl_all(self) -> List[Domain]:
        all_domains = []

        for source in self.sources:
            try:
                domains = await source.crawl()
                all_domains.extend(domains)
            except Exception as e:
                logger.error(f"Source {source.__class__.__name__} failed: {e}")
                continue

        # 중복 제거
        unique_domains = self._deduplicate(all_domains)
        return unique_domains

    def _deduplicate(self, domains: List[Domain]) -> List[Domain]:
        seen = set()
        unique = []
        for d in domains:
            if d.full_name not in seen:
                seen.add(d.full_name)
                unique.append(d)
        return unique
```

### 3.3 HTML 파서 강화

```python
# 제안: 다중 파싱 전략
class RobustParser:
    def parse(self, html: str) -> List[dict]:
        # 전략 1: 기존 클래스 기반
        result = self._parse_by_class(html)
        if result:
            return result

        # 전략 2: 테이블 구조 기반
        result = self._parse_by_structure(html)
        if result:
            return result

        # 전략 3: 정규표현식 기반
        result = self._parse_by_regex(html)
        if result:
            return result

        logger.error("All parsing strategies failed")
        return []

    def _parse_by_class(self, html: str) -> List[dict]:
        """클래스명 기반 파싱"""
        soup = BeautifulSoup(html, "lxml")
        # 여러 가능한 클래스명 시도
        for table_class in ["base1", "base2", "domain-table", "results"]:
            table = soup.find("table", class_=table_class)
            if table:
                return self._extract_from_table(table)
        return []

    def _parse_by_structure(self, html: str) -> List[dict]:
        """HTML 구조 기반 파싱"""
        soup = BeautifulSoup(html, "lxml")
        # 테이블 내 도메인 패턴 찾기
        tables = soup.find_all("table")
        for table in tables:
            if self._looks_like_domain_table(table):
                return self._extract_from_table(table)
        return []

    def _parse_by_regex(self, html: str) -> List[dict]:
        """정규표현식 기반 파싱"""
        # 도메인 패턴 매칭
        pattern = r'([a-z0-9-]+)\.(com|net|io|co|org|ai)'
        matches = re.findall(pattern, html.lower())
        return [{"name": m[0], "tld": m[1]} for m in matches]
```

---

## 4. 추가 기능 제안

### 4.1 🌟 핵심 추가 기능

#### 4.1.1 실시간 도메인 모니터링

```python
# 제안: 특정 도메인 감시
class DomainMonitor:
    """관심 도메인의 상태 변화 감시"""

    async def monitor_domain(self, domain: str):
        """도메인 상태 변화 감지"""
        current_status = await self.check_status(domain)

        # 이전 상태와 비교
        previous_status = await self.db.get_domain_status(domain)

        if current_status != previous_status:
            # 상태 변화 감지!
            await self.notify_status_change(domain, previous_status, current_status)

    async def check_status(self, domain: str) -> str:
        """
        상태 종류:
        - registered: 등록됨
        - pending_delete: 삭제 대기
        - redemption: 복구 기간
        - available: 등록 가능
        """
        pass
```

#### 4.1.2 자동 백오더

```python
# 제안: 자동 백오더 시스템
class AutoBackorder:
    """고점수 도메인 자동 백오더"""

    def __init__(self, api_credentials: dict):
        self.services = {
            "dropcatch": DropCatchAPI(api_credentials.get("dropcatch")),
            "namejet": NameJetAPI(api_credentials.get("namejet")),
            "snapnames": SnapNamesAPI(api_credentials.get("snapnames")),
        }

    async def place_backorder(self, domain: str, max_bid: float):
        """여러 서비스에 백오더 등록"""
        results = {}

        for service_name, api in self.services.items():
            try:
                result = await api.place_backorder(domain, max_bid)
                results[service_name] = result
            except Exception as e:
                results[service_name] = {"error": str(e)}

        return results
```

#### 4.1.3 가격 히스토리 및 예측

```python
# 제안: 머신러닝 기반 가격 예측
class PricePredictor:
    """도메인 가격 예측"""

    def __init__(self):
        self.model = self._load_model()
        self.historical_data = self._load_historical_sales()

    def predict_price(self, domain: Domain) -> dict:
        features = self._extract_features(domain)
        predicted_price = self.model.predict([features])[0]

        # 유사 도메인 판매 이력
        similar_sales = self._find_similar_sales(domain)

        return {
            "predicted_price": predicted_price,
            "confidence": self._calculate_confidence(features),
            "similar_sales": similar_sales,
            "price_range": {
                "min": predicted_price * 0.5,
                "max": predicted_price * 2.0,
            }
        }

    def _extract_features(self, domain: Domain) -> List[float]:
        """특성 추출"""
        return [
            len(domain.name),
            domain.length_score,
            domain.keyword_score,
            domain.pattern_score,
            self._tld_value(domain.tld),
            self._has_numbers(domain.name),
            self._has_hyphens(domain.name),
            # ... 더 많은 특성
        ]
```

#### 4.1.4 트렌드 분석

```python
# 제안: 키워드 트렌드 분석
class TrendAnalyzer:
    """키워드 트렌드 분석"""

    async def analyze_trends(self):
        """Google Trends, Twitter 등에서 트렌드 수집"""
        trends = []

        # Google Trends
        google_trends = await self._fetch_google_trends()
        trends.extend(google_trends)

        # Twitter/X 트렌드
        twitter_trends = await self._fetch_twitter_trends()
        trends.extend(twitter_trends)

        # 트렌드 키워드를 점수에 반영
        await self._update_keyword_scores(trends)

        return trends

    async def boost_trending_domains(self, domains: List[Domain]):
        """트렌드 키워드 포함 도메인 점수 상승"""
        trending_keywords = await self.get_trending_keywords()

        for domain in domains:
            for keyword in trending_keywords:
                if keyword.lower() in domain.name.lower():
                    domain.total_score = min(100, domain.total_score + 10)
                    domain.trend_boost = True
```

### 4.2 📊 분석 기능

#### 4.2.1 SEO 메트릭

```python
# 제안: SEO 데이터 통합
class SEOAnalyzer:
    """SEO 메트릭 분석"""

    async def analyze(self, domain: str) -> dict:
        results = {}

        # Moz API (유료)
        if self.moz_api_key:
            moz_data = await self._fetch_moz_data(domain)
            results["moz"] = {
                "domain_authority": moz_data.get("da"),
                "page_authority": moz_data.get("pa"),
                "spam_score": moz_data.get("spam_score"),
            }

        # Majestic API (유료)
        if self.majestic_api_key:
            majestic_data = await self._fetch_majestic_data(domain)
            results["majestic"] = {
                "trust_flow": majestic_data.get("tf"),
                "citation_flow": majestic_data.get("cf"),
                "backlinks": majestic_data.get("backlinks"),
            }

        # Archive.org (무료)
        archive_data = await self._fetch_archive_data(domain)
        results["archive"] = {
            "first_seen": archive_data.get("first_seen"),
            "snapshot_count": archive_data.get("count"),
        }

        return results
```

#### 4.2.2 도메인 히스토리

```python
# 제안: Wayback Machine 통합
class DomainHistory:
    """도메인 과거 이력 조회"""

    async def get_history(self, domain: str) -> dict:
        # Archive.org API
        url = f"https://archive.org/wayback/available?url={domain}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            data = response.json()

        if data.get("archived_snapshots"):
            snapshot = data["archived_snapshots"]["closest"]
            return {
                "has_history": True,
                "first_archive": snapshot.get("timestamp"),
                "snapshot_url": snapshot.get("url"),
            }

        return {"has_history": False}
```

### 4.3 🔔 알림 개선

#### 4.3.1 Telegram 콜백 핸들러

```python
# 제안: Telegram Bot 콜백 처리
from telegram.ext import Application, CallbackQueryHandler

class TelegramBotHandler:
    def __init__(self, token: str, db: Database):
        self.app = Application.builder().token(token).build()
        self.db = db

        # 콜백 핸들러 등록
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))

    async def handle_callback(self, update, context):
        query = update.callback_query
        data = query.data

        if data.startswith("watch:"):
            domain_id = int(data.split(":")[1])
            await self.db.add_to_watchlist(domain_id)
            await query.answer("✅ 관심 목록에 추가되었습니다!")

        elif data.startswith("ignore:"):
            domain_id = int(data.split(":")[1])
            await self.db.update_domain_status(domain_id, "ignored")
            await query.answer("🚫 무시 처리되었습니다.")

        elif data.startswith("detail:"):
            domain_id = int(data.split(":")[1])
            domain = await self.db.get_domain_by_id(domain_id)
            detail_msg = self._format_detail(domain)
            await query.message.reply_text(detail_msg, parse_mode="HTML")
```

#### 4.3.2 알림 우선순위

```python
# 제안: 알림 우선순위 시스템
class NotificationPriority:
    """알림 우선순위 관리"""

    PRIORITY_CRITICAL = 1   # 즉시 알림 (90점+, 오늘 만료)
    PRIORITY_HIGH = 2       # 높음 (80점+, 3일 내 만료)
    PRIORITY_MEDIUM = 3     # 중간 (70점+, 7일 내 만료)
    PRIORITY_LOW = 4        # 낮음 (그 외)

    def calculate_priority(self, domain: Domain) -> int:
        days_left = domain.days_until_expiry or 30

        if domain.total_score >= 90 or days_left <= 1:
            return self.PRIORITY_CRITICAL
        elif domain.total_score >= 80 or days_left <= 3:
            return self.PRIORITY_HIGH
        elif domain.total_score >= 70 or days_left <= 7:
            return self.PRIORITY_MEDIUM
        else:
            return self.PRIORITY_LOW

    async def send_with_priority(self, domain: Domain, notifier):
        priority = self.calculate_priority(domain)

        if priority == self.PRIORITY_CRITICAL:
            # 즉시 + 반복 알림
            await notifier.send_urgent_alert(domain)
            await self._schedule_reminder(domain, minutes=30)
        elif priority == self.PRIORITY_HIGH:
            await notifier.send_domain_alert(domain)
        elif priority == self.PRIORITY_MEDIUM:
            # 배치 알림 (1시간마다 모아서)
            await self._add_to_batch(domain)
```

### 4.4 🛡️ 보안 기능

#### 4.4.1 브랜드 보호

```python
# 제안: 브랜드 모니터링
class BrandProtection:
    """브랜드 침해 도메인 감지"""

    def __init__(self, protected_brands: List[str]):
        self.brands = protected_brands

    def check_infringement(self, domain: str) -> dict:
        domain_lower = domain.lower()

        for brand in self.brands:
            brand_lower = brand.lower()

            # 정확히 포함
            if brand_lower in domain_lower:
                return {
                    "infringement": True,
                    "brand": brand,
                    "type": "contains",
                }

            # 타이포스쿼팅 검사
            if self._is_typosquat(domain_lower, brand_lower):
                return {
                    "infringement": True,
                    "brand": brand,
                    "type": "typosquat",
                }

        return {"infringement": False}

    def _is_typosquat(self, domain: str, brand: str) -> bool:
        """레벤슈타인 거리 기반 타이포 감지"""
        distance = self._levenshtein_distance(domain, brand)
        threshold = max(1, len(brand) // 4)
        return distance <= threshold
```

---

## 5. 성능 최적화

### 5.1 비동기 최적화

```python
# 제안: 동시 크롤링 최적화
class OptimizedCrawler:
    async def crawl_with_semaphore(self, urls: List[str], max_concurrent: int = 5):
        """세마포어로 동시 요청 제한"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_limit(url):
            async with semaphore:
                return await self._fetch_page(url)

        tasks = [fetch_with_limit(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [r for r in results if not isinstance(r, Exception)]
```

### 5.2 캐싱

```python
# 제안: Redis 캐싱 (선택사항)
class DomainCache:
    def __init__(self):
        self.cache = {}  # 또는 Redis
        self.ttl = 3600  # 1시간

    async def get_or_fetch(self, domain: str, fetch_func):
        cache_key = f"domain:{domain}"

        # 캐시 확인
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if cached["expires"] > time.time():
                return cached["data"]

        # 새로 조회
        data = await fetch_func(domain)

        # 캐시 저장
        self.cache[cache_key] = {
            "data": data,
            "expires": time.time() + self.ttl,
        }

        return data
```

### 5.3 배치 처리

```python
# 제안: 배치 평가
class BatchProcessor:
    BATCH_SIZE = 100

    async def process_in_batches(self, domains: List[Domain]):
        """배치 단위로 처리"""
        for i in range(0, len(domains), self.BATCH_SIZE):
            batch = domains[i:i + self.BATCH_SIZE]

            # 배치 평가
            evaluated = await self._evaluate_batch(batch)

            # 배치 저장
            await self._save_batch(evaluated)

            # 메모리 정리
            del batch
            gc.collect()
```

---

## 6. 보안 강화

### 6.1 API 키 보호

```python
# 제안: 암호화된 설정
from cryptography.fernet import Fernet

class SecureConfig:
    def __init__(self, encryption_key: str):
        self.cipher = Fernet(encryption_key.encode())

    def encrypt_value(self, value: str) -> str:
        return self.cipher.encrypt(value.encode()).decode()

    def decrypt_value(self, encrypted: str) -> str:
        return self.cipher.decrypt(encrypted.encode()).decode()

    def load_secure_env(self):
        """암호화된 .env.encrypted 로드"""
        pass
```

### 6.2 접근 제어

```python
# 제안: 웹 대시보드 인증
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, settings.web_username)
    correct_password = secrets.compare_digest(credentials.password, settings.web_password)

    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return credentials.username
```

---

## 7. 구현 우선순위

### 7.1 Phase 1: 필수 (1주)

| 기능 | 중요도 | 난이도 | 설명 |
|-----|-------|-------|------|
| 도메인 등록 가능 확인 | 🔴 필수 | 중 | WHOIS/RDAP 조회 |
| User-Agent 로테이션 | 🔴 필수 | 하 | 차단 방지 |
| 적응형 딜레이 | 🔴 필수 | 중 | Rate Limit 대응 |
| HTML 파서 강화 | 🔴 필수 | 중 | 안정성 확보 |
| Telegram 콜백 | 🟡 높음 | 중 | UX 개선 |

### 7.2 Phase 2: 중요 (2주)

| 기능 | 중요도 | 난이도 | 설명 |
|-----|-------|-------|------|
| 프록시 로테이션 | 🟡 높음 | 중 | 차단 방지 강화 |
| 다중 크롤링 소스 | 🟡 높음 | 상 | 데이터 다양성 |
| 알림 우선순위 | 🟡 높음 | 중 | 중요 도메인 강조 |
| 웹 인증 | 🟡 높음 | 하 | 보안 강화 |

### 7.3 Phase 3: 확장 (1개월)

| 기능 | 중요도 | 난이도 | 설명 |
|-----|-------|-------|------|
| SEO 메트릭 통합 | 🟢 중간 | 상 | 가치 평가 정확도 |
| 자동 백오더 | 🟢 중간 | 상 | 자동화 |
| 가격 예측 ML | 🟢 중간 | 최상 | 정확한 가격 예측 |
| 트렌드 분석 | 🟢 중간 | 상 | 시장 트렌드 반영 |

### 7.4 Phase 4: 고급 (장기)

| 기능 | 중요도 | 난이도 | 설명 |
|-----|-------|-------|------|
| 브랜드 보호 | 🔵 선택 | 중 | 기업용 기능 |
| 도메인 히스토리 | 🔵 선택 | 중 | 상세 분석 |
| 경매 모니터링 | 🔵 선택 | 상 | 경매 추적 |
| API 서비스화 | 🔵 선택 | 상 | SaaS 확장 |

---

## 부록: 참고 리소스

### API 서비스

| 서비스 | 용도 | 가격 |
|-------|------|------|
| GoDaddy API | 도메인 확인, 등록 | 무료 |
| Namecheap API | 도메인 확인, 등록 | 무료 |
| Moz API | DA/PA 조회 | $99/월~ |
| Majestic API | 백링크 데이터 | $49/월~ |
| Archive.org | 히스토리 | 무료 |

### 프록시 서비스

| 서비스 | 특징 | 가격 |
|-------|------|------|
| Bright Data | 데이터센터/레지덴셜 | $0.6/GB~ |
| Oxylabs | 레지덴셜 | $10/GB~ |
| SmartProxy | 레지덴셜 | $4/GB~ |

### 도메인 백오더 서비스

| 서비스 | URL |
|-------|-----|
| DropCatch | dropcatch.com |
| NameJet | namejet.com |
| SnapNames | snapnames.com |
| Pool.com | pool.com |
