# 📖 Domain Sniper 시스템 상세 기술 문서

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [모듈별 상세 로직](#2-모듈별-상세-로직)
3. [데이터 흐름](#3-데이터-흐름)
4. [스케줄링 시스템](#4-스케줄링-시스템)
5. [점수 평가 알고리즘](#5-점수-평가-알고리즘)
6. [데이터베이스 구조](#6-데이터베이스-구조)
7. [알림 시스템](#7-알림-시스템)
8. [웹 대시보드](#8-웹-대시보드)

---

## 1. 시스템 개요

### 1.1 목적
만료 예정인 도메인을 자동으로 수집하고, 가치를 평가하여 고가치 도메인을 실시간으로 알림받는 시스템

### 1.2 기술 스택

| 구성요소 | 기술 | 버전 | 역할 |
|---------|------|------|------|
| 런타임 | Python | 3.11+ | 메인 언어 |
| 이벤트 루프 | uvloop | 0.19.0 | asyncio 성능 최적화 |
| HTTP 클라이언트 | httpx | 0.27.0 | 비동기 HTTP 요청 |
| HTML 파서 | BeautifulSoup4 | 4.12.3 | HTML 파싱 |
| 데이터베이스 | SQLite + aiosqlite | 0.19.0 | 비동기 DB 접근 |
| 스케줄러 | APScheduler | 3.10.4 | 작업 스케줄링 |
| 웹 프레임워크 | FastAPI | 0.109.2 | REST API + 웹 UI |
| 템플릿 | Jinja2 | 3.1.3 | HTML 렌더링 |
| 알림 | python-telegram-bot | 21.0.1 | Telegram Bot |
| 알림 | aiohttp | 3.9.3 | Discord Webhook |

### 1.3 아키텍처 다이어그램

```
┌────────────────────────────────────────────────────────────────┐
│                        main.py (DomainSniper)                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                   APScheduler                            │  │
│  │  ┌──────────────┬──────────────┬──────────────────────┐ │  │
│  │  │ full_crawl   │ week_crawl   │ day_crawl            │ │  │
│  │  │ (06:00 daily)│ (every 3h)   │ (every 30min)        │ │  │
│  │  └──────┬───────┴──────┬───────┴──────────┬───────────┘ │  │
│  └─────────┴──────────────┴──────────────────┴─────────────┘  │
│                           │                                    │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │              ExpiredDomainsCrawler                       │  │
│  │  - httpx.AsyncClient (비동기 HTTP)                       │  │
│  │  - DomainParser (BeautifulSoup)                          │  │
│  │  - tenacity 재시도 로직                                   │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                    │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │                  DomainEvaluator                         │  │
│  │  ┌─────────────┬─────────────┬─────────────────────────┐│  │
│  │  │LengthScorer │KeywordScorer│PatternScorer            ││  │
│  │  │   (35%)     │    (40%)    │    (25%)                ││  │
│  │  └─────────────┴─────────────┴─────────────────────────┘│  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                    │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │                    Database (SQLite)                     │  │
│  │  - aiosqlite (비동기)                                     │  │
│  │  - WAL 모드 활성화                                        │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                    │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │               NotificationManager                        │  │
│  │  ┌─────────────────────┬─────────────────────────────┐  │  │
│  │  │ TelegramNotifier    │ DiscordNotifier             │  │  │
│  │  │ (python-telegram-bot)│ (aiohttp webhook)          │  │  │
│  │  └─────────────────────┴─────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │              FastAPI Web Dashboard (:8000)               │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. 모듈별 상세 로직

### 2.1 메인 모듈 (main.py)

#### 2.1.1 DomainSniper 클래스

```python
class DomainSniper:
    """메인 애플리케이션 클래스"""

    # 속성
    - db: Database               # SQLite 데이터베이스 인스턴스
    - scheduler: AsyncIOScheduler # APScheduler 인스턴스
    - evaluator: DomainEvaluator # 도메인 평가기
    - notifier: NotificationManager # 알림 관리자
    - running: bool              # 실행 상태 플래그
```

#### 2.1.2 초기화 프로세스

```
initialize() 호출 순서:
1. validate_settings() - 환경변수 검증
2. init_database() - SQLite 연결 및 스키마 생성
3. DomainEvaluator() - 키워드 JSON 로드
4. NotificationManager() - Telegram/Discord 초기화
5. _setup_schedules() - APScheduler 작업 등록
```

#### 2.1.3 실행 모드

| 모드 | 명령어 | 동작 |
|-----|-------|------|
| 전체 서비스 | `python main.py` | 스케줄러 + 웹서버 실행 |
| 웹만 | `python main.py --web-only` | 웹 대시보드만 실행 |
| 즉시 크롤링 | `python main.py --crawl-now` | 크롤링 1회 실행 후 종료 |

### 2.2 크롤러 모듈 (crawler/)

#### 2.2.1 ExpiredDomainsCrawler 클래스

**HTTP 클라이언트 설정:**
```python
httpx.AsyncClient(
    timeout=30초,
    headers={
        "User-Agent": "Mozilla/5.0 ...",
        "Accept": "text/html,application/xhtml+xml...",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    },
    follow_redirects=True
)
```

**재시도 로직 (tenacity):**
```python
@retry(
    stop=stop_after_attempt(3),      # 최대 3회 시도
    wait=wait_exponential(           # 지수 백오프
        multiplier=1,
        min=2,                       # 최소 2초
        max=10                       # 최대 10초
    )
)
```

**요청 딜레이:**
```python
await asyncio.sleep(settings.request_delay + random.uniform(0, 1))
# 기본 2초 + 랜덤 0~1초 = 2~3초 딜레이
```

#### 2.2.2 크롤링 URL 구조

**expireddomains.net 파라미터:**

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `fwhois` | 22 | WHOIS 가능 도메인만 |
| `fbl` | 0 | 블랙리스트 제외 |
| `fstatuses[]` | 1 | 활성 상태 |
| `ftld[]` | com/net/io... | TLD 필터 |
| `fmaxchars` | 12 | 최대 길이 |
| `fminchars` | 3 | 최소 길이 |
| `fhyphens` | 1 | 하이픈 제외 |
| `fnumbers` | 1 | 숫자 제외 |
| `start` | 0/25/50... | 페이지 오프셋 |

**엔드포인트:**
- `/expired-domains/` - 만료된 도메인
- `/pendingdelete-domains/` - 삭제 대기 도메인
- `/domain-name-search/` - 키워드 검색

#### 2.2.3 DomainParser 클래스

**HTML 파싱 로직:**
```python
def parse_expireddomains_html(html):
    1. BeautifulSoup(html, "lxml")로 파싱
    2. table.base1 클래스 테이블 찾기
    3. tr.base1 행들 순회
    4. td 셀에서 도메인명 추출 (a.namemark)
    5. 만료일 텍스트 파싱 ("X days", "today" 등)
    6. 도메인 딕셔너리 리스트 반환
```

**도메인 검증 규칙:**
```python
def is_valid_domain(name, tld, ...):
    1. 길이 검사: min_length <= len(name) <= max_length
    2. TLD 검사: tld in allowed_tlds
    3. 숫자 검사: allow_numbers or not any(c.isdigit())
    4. 하이픈 검사: allow_hyphens or "-" not in name
    5. 금지 키워드 검사: BLOCKED_KEYWORDS와 매칭
    6. 유효 문자 검사: ^[a-z0-9-]+$ 패턴
    7. 시작/끝 하이픈 금지
```

**금지 키워드 목록:**
```python
BLOCKED_KEYWORDS = {
    "porn", "xxx", "sex", "adult", "nude", "naked",
    "casino", "gambling", "bet", "poker", "slot",
    "viagra", "cialis", "pharmacy", "pills", "drug"
    # ... 총 30개 이상
}
```

### 2.3 스코어러 모듈 (scorer/)

#### 2.3.1 LengthScorer

**길이별 기본 점수:**
```
길이  | 점수 | 등급
------+------+--------
1-3자 | 100  | PREMIUM
4자   | 90   | ULTRA
5자   | 80   | HIGH
6자   | 70   | MEDIUM
7자   | 60   | MEDIUM
8자   | 50   | LOW
9자   | 40   | LOW
10자  | 30   | VERY_LOW
11자  | 20   | VERY_LOW
12자+ | 10   | VERY_LOW
```

**TLD 가중치:**
```python
TLD_MULTIPLIERS = {
    "com": 1.0,   # 100%
    "io": 0.95,   # 95%
    "ai": 1.0,    # 100%
    "co": 0.9,    # 90%
    "net": 0.85,  # 85%
    "kr": 0.7,    # 70%
    ...
}
```

**계산 공식:**
```
최종_길이점수 = 기본점수 × TLD_가중치
```

#### 2.3.2 KeywordScorer

**키워드 카테고리 및 점수:**

| 카테고리 | 키워드 예시 | 점수 범위 |
|---------|-----------|----------|
| Tech | ai, ml, api, cloud, crypto | 90-100 |
| Finance | pay, bank, coin, wallet | 85-95 |
| Business | pro, hub, lab, market | 80-90 |
| Startup | startup, launch, scale | 85-95 |
| Generic | best, top, go, get | 70-85 |
| Action | find, create, build | 70-80 |

**매칭 알고리즘:**
```python
def calculate(domain_name):
    1. 정확히 일치하는 키워드 찾기
       - "ai" == domain_name → 100점

    2. 포함된 키워드 찾기
       - "cloud" in "cloudpay" → 95점

    3. 여러 키워드 조합 보너스
       - 2개 이상 매칭 시 +10점

    4. 최고 점수 반환
```

#### 2.3.3 PatternScorer

**CV 패턴 분석:**
```
C = 자음 (b, c, d, f, g, h, j, k, l, m, n, p, q, r, s, t, v, w, x, y, z)
V = 모음 (a, e, i, o, u)

예시:
- "meta" → CVCV (이상적)
- "google" → CVVCVV
- "apple" → VCCVV
```

**이상적인 패턴:**
```python
ideal_patterns = [
    "CVCV",    # 4자: 코코, 라라
    "CVCVC",   # 5자: 애플
    "CVCCV",   # 5자: 테슬라
    "CVCVCV",  # 6자: 토요타
    "CVCCVC",  # 6자: 넷플릭스
]
```

**자음 조합 분석:**
```python
# 발음하기 좋은 조합 (보너스)
GOOD_CONSONANT_PAIRS = {"bl", "br", "ch", "cl", "cr", "dr", "fl", ...}

# 발음하기 어려운 조합 (감점)
BAD_CONSONANT_PAIRS = {"bk", "bz", "cf", "dk", "fk", "gk", ...}
```

**점수 계산:**
```
기본점수 = 50
+ CV 패턴 점수 (최대 +30)
- 자음 조합 감점 (최대 -20)
+ 반복 패턴 점수 (최대 +10)
+ 시작/끝 문자 점수 (최대 +10)
= 최종 패턴 점수 (0-100)
```

#### 2.3.4 DomainEvaluator (통합)

**가중치:**
```python
WEIGHT_LENGTH = 0.35   # 35%
WEIGHT_KEYWORD = 0.40  # 40%
WEIGHT_PATTERN = 0.25  # 25%
```

**총점 계산:**
```python
total_score = int(
    length_score * 0.35 +
    keyword_score * 0.40 +
    pattern_score * 0.25
)
```

**예상 가치 계산:**
```python
# 1단계: 점수 기반 기본 가치
점수 90+: $5,000 ~ $50,000
점수 80-89: $1,000 ~ $10,000
점수 70-79: $500 ~ $5,000
점수 60-69: $100 ~ $1,000
점수 50-59: $50 ~ $500
점수 50미만: $10 ~ $100

# 2단계: 길이 보정
3자 이하: 기본값 × 5~10
4자: 기본값 × 3~5
5자: 기본값 × 2~3

# 3단계: TLD 보정
com: × 1.0
io: × 0.8
net: × 0.6
...
```

---

## 3. 데이터 흐름

### 3.1 크롤링 파이프라인

```
┌─────────────────────────────────────────────────────────────────┐
│                         크롤링 시작                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. HTTP 요청                                                     │
│    - URL: https://expireddomains.net/expired-domains/?...       │
│    - 딜레이: 2~3초                                               │
│    - 재시도: 3회 (지수 백오프)                                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. HTML 파싱                                                     │
│    - BeautifulSoup으로 테이블 파싱                               │
│    - 도메인명, TLD, 만료일 추출                                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. 필터링                                                        │
│    - 길이 필터 (3~12자)                                          │
│    - TLD 필터 (com, net, io, co, kr)                            │
│    - 숫자/하이픈 필터                                            │
│    - 금지 키워드 필터                                            │
│    - 만료일 필터 (지정 일수 이내)                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. 평가                                                          │
│    - 길이 점수 계산 (35%)                                        │
│    - 키워드 점수 계산 (40%)                                      │
│    - 패턴 점수 계산 (25%)                                        │
│    - 예상 가치 계산                                              │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. 저장                                                          │
│    - SQLite INSERT OR IGNORE                                     │
│    - 중복 도메인 건너뛰기                                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. 알림                                                          │
│    - 미알림 고점수 도메인 조회                                    │
│    - Telegram/Discord 발송                                       │
│    - notified_at 업데이트                                        │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 데이터 변환 과정

```python
# 1. 크롤링 원시 데이터
raw_domain = {
    "name": "startup",
    "tld": "io",
    "full_name": "startup.io",
    "length": 7,
    "expiry_date": date(2024, 1, 15),
    "source": "expireddomains.net"
}

# 2. Domain 객체 생성
domain = Domain(
    name="startup",
    tld="io",
    full_name="startup.io",
    length=7,
    expiry_date=date(2024, 1, 15),
    source="expireddomains.net"
)

# 3. 평가 후 Domain 객체
domain.length_score = 60      # 7자 = 60점
domain.keyword_score = 95     # "startup" 키워드
domain.pattern_score = 75     # CVCVCVC 패턴
domain.total_score = 78       # 60*0.35 + 95*0.40 + 75*0.25
domain.estimated_value_min = 400   # $400
domain.estimated_value_max = 4000  # $4,000

# 4. DB 저장
INSERT INTO domains (name, tld, full_name, length, expiry_date,
    length_score, keyword_score, pattern_score, total_score, ...)
VALUES ('startup', 'io', 'startup.io', 7, '2024-01-15',
    60, 95, 75, 78, ...);
```

---

## 4. 스케줄링 시스템

### 4.1 APScheduler 구성

```python
scheduler = AsyncIOScheduler()

# 작업 목록
┌────────────────┬─────────────────────┬────────────────────────────┐
│ Job ID         │ Trigger             │ 설명                       │
├────────────────┼─────────────────────┼────────────────────────────┤
│ full_crawl     │ CronTrigger(6:00)   │ 매일 06시 전체 크롤링       │
│ week_crawl     │ Interval(3시간)      │ 7일 이내 만료 도메인        │
│ day_crawl      │ Interval(30분)       │ 1일 이내 만료 도메인        │
│ daily_report   │ CronTrigger(8:00)   │ 일일 요약 리포트            │
│ heartbeat      │ Interval(설정값)     │ 시스템 상태 확인 (선택)     │
└────────────────┴─────────────────────┴────────────────────────────┘
```

### 4.2 크롤링 범위

| 작업 | 만료 일수 | 페이지/TLD | 예상 도메인 수 |
|-----|---------|-----------|--------------|
| full_crawl | 30일 | 5페이지 | 500~1000개 |
| week_crawl | 7일 | 3페이지 | 200~400개 |
| day_crawl | 1일 | 3페이지 | 50~150개 |

---

## 5. 점수 평가 알고리즘

### 5.1 점수 계산 예시

**예시 1: "ai.com"**
```
길이: 2자 → 100점
TLD 가중치: com × 1.0 → 100점
키워드: "ai" → 100점
패턴: CV → 70점 (짧아서 보너스 제한)

총점 = 100×0.35 + 100×0.40 + 70×0.25 = 92점
예상가치: $25,000 ~ $500,000 (2자 .com 프리미엄)
```

**예시 2: "cloudpay.com"**
```
길이: 8자 → 50점
TLD 가중치: com × 1.0 → 50점
키워드: "cloud"(95) + "pay"(95) → 100점 (다중 매칭 보너스)
패턴: CVVCCVC → 55점

총점 = 50×0.35 + 100×0.40 + 55×0.25 = 71점
예상가치: $500 ~ $5,000
```

**예시 3: "xyzabc.net"**
```
길이: 6자 → 70점
TLD 가중치: net × 0.85 → 60점
키워드: 없음 → 0점
패턴: CVCCVC → 60점

총점 = 60×0.35 + 0×0.40 + 60×0.25 = 36점
예상가치: $6 ~ $60
```

### 5.2 점수 분포 기준

| 점수 | 등급 | 액션 |
|-----|------|------|
| 90+ | 프리미엄 | 즉시 알림 + 긴급 표시 |
| 80-89 | 고가치 | 즉시 알림 |
| 70-79 | 좋음 | 알림 (설정에 따라) |
| 60-69 | 보통 | DB 저장만 |
| 60 미만 | 낮음 | DB 저장만 |

---

## 6. 데이터베이스 구조

### 6.1 테이블 스키마

```sql
-- 메인 도메인 테이블
domains (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE,        -- 도메인명 (TLD 제외)
    tld             TEXT,               -- TLD
    full_name       TEXT,               -- 전체 도메인
    length          INTEGER,            -- 길이
    expiry_date     DATE,               -- 만료 예정일

    -- 점수
    length_score    INTEGER,
    keyword_score   INTEGER,
    pattern_score   INTEGER,
    total_score     INTEGER,

    -- 메타
    source          TEXT,               -- 수집 소스
    auction_url     TEXT,               -- 경매 URL
    estimated_value_min INTEGER,
    estimated_value_max INTEGER,
    status          TEXT,               -- pending/notified/watched/ignored

    -- 타임스탬프
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,
    notified_at     TIMESTAMP,

    -- 정렬용
    score_date      TEXT                -- "087_2024-01-15" 형식
)
```

### 6.2 인덱스

```sql
idx_domains_full_name    -- 도메인명 검색
idx_domains_expiry_date  -- 만료일 정렬
idx_domains_total_score  -- 점수 정렬
idx_domains_status       -- 상태 필터
idx_domains_score_date   -- 점수+날짜 복합 정렬
idx_domains_created_at   -- 생성일 정렬
```

### 6.3 SQLite 최적화

```sql
PRAGMA journal_mode=WAL;     -- Write-Ahead Logging
PRAGMA synchronous=NORMAL;   -- 쓰기 성능 향상
PRAGMA cache_size=10000;     -- 캐시 10MB
PRAGMA temp_store=MEMORY;    -- 임시 테이블 메모리
```

---

## 7. 알림 시스템

### 7.1 Telegram 메시지 형식

```
🔥🔥 고가치 도메인 발견!

📌 startup.io
⏰ 만료: 2일 후
📊 점수: 87/100

━━━ 점수 상세 ━━━
• 길이: 7자 (85점)
• 키워드: 95점
• 패턴: 80점

💰 예상가: $1,000~$5,000
📍 소스: expireddomains.net

[🔍 상세보기] [⭐ 관심등록] [🚫 무시]
[🔗 GoDaddy] [🔗 Namecheap]
```

### 7.2 인라인 키보드

```python
keyboard = [
    [InlineKeyboardButton("🔍 상세보기", callback_data="detail:123"),
     InlineKeyboardButton("⭐ 관심등록", callback_data="watch:123")],
    [InlineKeyboardButton("🔗 GoDaddy", url="https://godaddy.com/..."),
     InlineKeyboardButton("🔗 Namecheap", url="https://namecheap.com/...")],
    [InlineKeyboardButton("🚫 무시", callback_data="ignore:123")]
]
```

### 7.3 Discord Embed

```python
embed = {
    "title": "🔥 고가치 도메인 발견: startup.io",
    "color": 0xFF6600,  # 주황색 (80점대)
    "fields": [
        {"name": "📊 총점", "value": "87/100", "inline": True},
        {"name": "⏰ 만료", "value": "2일 후", "inline": True},
        {"name": "💰 예상가", "value": "$1,000~$5,000", "inline": True},
    ],
    "footer": {"text": "Domain Sniper"},
    "timestamp": "2024-01-13T10:00:00Z"
}
```

---

## 8. 웹 대시보드

### 8.1 라우트 구조

| 경로 | 메서드 | 설명 |
|-----|--------|------|
| `/` | GET | 메인 페이지 (도메인 목록) |
| `/watchlist` | GET | 관심 도메인 목록 |
| `/watchlist/add` | POST | 관심 등록 |
| `/watchlist/remove/{id}` | POST | 관심 해제 |
| `/domain/{id}` | GET | 도메인 상세 |
| `/domain/{id}/status` | POST | 상태 변경 |
| `/logs` | GET | 크롤링 로그 |
| `/settings` | GET | 설정 확인 |
| `/api/stats` | GET | 통계 JSON |
| `/api/domains` | GET | 도메인 목록 JSON |
| `/api/health` | GET | 헬스체크 |

### 8.2 템플릿 구조

```
web/templates/
├── base.html          # 기본 레이아웃 (네비게이션, 푸터)
├── index.html         # 메인 페이지
├── watchlist.html     # 관심 목록
├── domain_detail.html # 도메인 상세
├── logs.html          # 크롤링 로그
└── settings.html      # 설정 확인
```

### 8.3 UI 기능

- **점수 색상**: 90+(빨강), 80+(주황), 70+(노랑), 60+(초록)
- **만료 표시**: 1일 이내(깜빡임), 7일 이내(경고색)
- **페이지네이션**: 20개씩 표시
- **필터**: 최소 점수 필터
- **반응형**: 모바일/태블릿 지원
