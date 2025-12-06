# 🏗️ Domain Sniper 아키텍처 문서

## 시스템 개요

Domain Sniper는 라즈베리파이4에서 24/7 무중단 운영되는 경량화된 도메인 스나이핑 시스템입니다.

```
┌─────────────────────────────────────────────────────────────┐
│                    Raspberry Pi 4                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              domain-sniper.service (systemd)          │ │
│  └───────────────────────┬───────────────────────────────┘ │
│                          │                                  │
│  ┌───────────────────────▼───────────────────────────────┐ │
│  │                     main.py                           │ │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │              APScheduler (인프로세스)            │  │ │
│  │  │                                                 │  │ │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │  │ │
│  │  │  │ 06:00   │  │ 매 3시간 │  │ 매 30분         │ │  │ │
│  │  │  │ 전체    │  │ 7일이내  │  │ 1일이내         │ │  │ │
│  │  │  │ 스캔    │  │ 스캔    │  │ 스캔            │ │  │ │
│  │  │  └────┬────┘  └────┬────┘  └───────┬─────────┘ │  │ │
│  │  │       │            │               │           │  │ │
│  │  └───────┴────────────┴───────────────┴───────────┘  │ │
│  │                       │                               │ │
│  │  ┌────────────────────▼────────────────────────────┐  │ │
│  │  │                 Crawler                          │  │ │
│  │  │  ┌──────────────────┐  ┌─────────────────────┐  │  │ │
│  │  │  │ ExpiredDomains   │  │ DomainParser        │  │  │ │
│  │  │  │ Crawler (httpx)  │  │ (BeautifulSoup)     │  │  │ │
│  │  │  └────────┬─────────┘  └──────────┬──────────┘  │  │ │
│  │  └───────────┴───────────────────────┴─────────────┘  │ │
│  │                       │                               │ │
│  │  ┌────────────────────▼────────────────────────────┐  │ │
│  │  │                  Scorer                          │  │ │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │  │ │
│  │  │  │ Length   │ │ Keyword  │ │ Pattern          │ │  │ │
│  │  │  │ (35%)    │ │ (40%)    │ │ (25%)            │ │  │ │
│  │  │  └────┬─────┘ └────┬─────┘ └────────┬─────────┘ │  │ │
│  │  │       └────────────┼────────────────┘           │  │ │
│  │  │                    │                             │  │ │
│  │  │              ┌─────▼─────┐                       │  │ │
│  │  │              │ Evaluator │                       │  │ │
│  │  │              │ 총점 계산  │                       │  │ │
│  │  │              └─────┬─────┘                       │  │ │
│  │  └────────────────────┴─────────────────────────────┘  │ │
│  │                       │                               │ │
│  │  ┌────────────────────▼────────────────────────────┐  │ │
│  │  │              Database (SQLite)                   │  │ │
│  │  │                 domains.db                       │  │ │
│  │  └────────────────────┬─────────────────────────────┘  │ │
│  │                       │                               │ │
│  │  ┌────────────────────▼────────────────────────────┐  │ │
│  │  │               Notifier                           │  │ │
│  │  │  ┌──────────────┐  ┌───────────────────────────┐│  │ │
│  │  │  │ Telegram Bot │  │ Discord Webhook           ││  │ │
│  │  │  └──────┬───────┘  └─────────────┬─────────────┘│  │ │
│  │  └─────────┴────────────────────────┴──────────────┘  │ │
│  │                                                       │ │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │            FastAPI Web Dashboard                 │  │ │
│  │  │                  :8000                           │  │ │
│  │  └─────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
              │                              │
              ▼                              ▼
     ┌────────────────┐             ┌─────────────────┐
     │   Telegram     │             │    Discord      │
     │   Bot API      │             │    Webhook      │
     └────────────────┘             └─────────────────┘
```

---

## 모듈 상세

### 1. Main (main.py)

**역할**: 애플리케이션 진입점 및 전체 오케스트레이션

```python
class DomainSniper:
    - initialize()      # 시스템 초기화
    - run_full_crawl()  # 전체 크롤링
    - run_week_crawl()  # 7일 이내 크롤링
    - run_day_crawl()   # 1일 이내 크롤링
    - start()           # 서비스 시작
    - stop()            # 서비스 종료
```

**스케줄러 작업**:
| 작업 | 주기 | 설명 |
|-----|------|------|
| full_crawl | 매일 06:00 | 30일 이내 만료 도메인 전체 스캔 |
| week_crawl | 매 3시간 | 7일 이내 만료 도메인 스캔 |
| day_crawl | 매 30분 | 1일 이내 만료 도메인 스캔 |
| daily_report | 매일 08:00 | 일일 요약 리포트 |
| heartbeat | 설정에 따라 | 시스템 정상 작동 확인 |

---

### 2. Crawler 모듈

#### 2.1 ExpiredDomainsCrawler

**역할**: expireddomains.net에서 도메인 정보 수집

```python
class ExpiredDomainsCrawler:
    - crawl_expireddomains(tld, days_until_expiry, max_pages)
    - crawl_all_tlds(days_until_expiry, max_pages_per_tld)
    - crawl_pending_delete(max_pages)
    - search_keyword(keyword, max_pages)
```

**URL 구조**:
| URL | 용도 |
|-----|------|
| `www.expireddomains.net` | 메인 사이트, 로그인 |
| `member.expireddomains.net` | 멤버 영역 (로그인 후 크롤링) |

**TLD별 엔드포인트** (멤버 영역):
- `/domains/expiredcom/` - .com 도메인
- `/domains/expirednet/` - .net 도메인
- `/domains/expiredio/` - .io 도메인
- `/domains/combinedexpired/` - 전체 TLD 통합
- `/domains/pendingdelete/` - 삭제 예정

**로그인 흐름**:
1. `/login/` 페이지 방문 → 쿠키 설정
2. 폼 필드 동적 추출 (BeautifulSoup)
3. `/logincheck/`로 POST 요청
4. 리다이렉트 수동 처리 (302/303)
5. `member.expireddomains.net` 세션 확인
6. 세션 만료 시 자동 재로그인

**기술 스택**:
- `httpx`: 비동기 HTTP 클라이언트 (쿠키 기반 세션 유지)
- `tenacity`: 재시도 로직
- Rate limiting: 요청 간 2초 딜레이, TLD 간 10초 딜레이

#### 2.2 DomainParser

**역할**: HTML/JSON 파싱 및 도메인 검증

```python
class DomainParser:
    - parse_domain_name(full_domain)
    - is_valid_domain(name, tld, filters...)
    - parse_expireddomains_html(html)
    - parse_parkio_json(data)
```

**HTML 파싱 전략** (다양한 테이블 구조 지원):
1. `table.base1` - 멤버 영역 기본 테이블
2. `table#table` 또는 `table.domainlist`
3. `div#content` 내부 테이블
4. `a.field_domain` 또는 `a.namemark` 링크 포함 테이블

**도메인 추출 방식**:
- `td.field_domain > a` 태그
- `a.namemark` 또는 `a.field_domain` 클래스
- 정규식 폴백: `.com`, `.net` 등 패턴 매칭

**필터링 규칙**:
- 길이: 3-12자 (설정 가능)
- TLD: com, net, io, co, kr (설정 가능)
- 제외: 숫자, 하이픈, 성인 키워드

---

### 3. Scorer 모듈

#### 3.1 LengthScorer

**역할**: 도메인 길이 기반 점수 산정

| 길이 | 점수 | 등급 |
|-----|------|------|
| 2-3자 | 100 | PREMIUM |
| 4자 | 90 | ULTRA |
| 5자 | 80 | HIGH |
| 6자 | 70 | MEDIUM |
| 7자 | 60 | MEDIUM |
| 8자 | 50 | LOW |
| 9자 | 40 | LOW |
| 10자+ | 30-10 | VERY_LOW |

#### 3.2 KeywordScorer

**역할**: 고가치 키워드 매칭

**키워드 카테고리**:
- Tech (90-100점): ai, ml, api, cloud, crypto...
- Finance (85-95점): pay, bank, coin, wallet...
- Business (80-90점): pro, hub, lab, market...
- Generic (70-85점): best, top, go, get...

#### 3.3 PatternScorer

**역할**: 발음 패턴 분석 (CVCV 패턴)

**분석 요소**:
- CV 패턴: 자음-모음 배치
- 자음 조합: 발음 용이성
- 반복 패턴: 운율
- 시작/끝 문자: 브랜딩 적합성

#### 3.4 DomainEvaluator

**역할**: 통합 점수 계산

```
총점 = (길이점수 × 0.35) + (키워드점수 × 0.40) + (패턴점수 × 0.25)
```

**예상 가치 계산**:
| 점수 | 기본 가치 |
|-----|----------|
| 90+ | $5,000 - $50,000 |
| 80-89 | $1,000 - $10,000 |
| 70-79 | $500 - $5,000 |
| 60-69 | $100 - $1,000 |
| 50-59 | $50 - $500 |

---

### 4. Database 모듈

#### 스키마

```sql
-- 도메인 정보
domains (
    id, name, tld, full_name, length, expiry_date,
    length_score, keyword_score, pattern_score, total_score,
    source, auction_url, estimated_value_min, estimated_value_max,
    status, created_at, notified_at
)

-- 워치리스트
watchlist (
    id, domain_id, note, priority, added_at
)

-- 크롤링 로그
crawl_logs (
    id, source, crawl_type, total_found, new_domains,
    high_score_count, status, duration_seconds, created_at
)

-- 설정
settings (key, value, updated_at)

-- 키워드
keywords (word, category, score)
```

#### 최적화

```sql
PRAGMA journal_mode=WAL;      -- 동시 읽기/쓰기
PRAGMA synchronous=NORMAL;    -- 쓰기 성능 향상
PRAGMA cache_size=10000;      -- 캐시 증가
PRAGMA temp_store=MEMORY;     -- 임시 테이블 메모리 사용
```

---

### 5. Notifier 모듈

#### 5.1 TelegramNotifier

**기능**:
- 도메인 알림 (인라인 키보드 포함)
- 일일 리포트
- 하트비트
- 에러 알림

**메시지 형식**:
```
🔥 고가치 도메인 발견!

📌 startup.io
⏰ 만료: 2일 후
📊 점수: 87/100

━━━ 점수 상세 ━━━
• 길이: 7자 (85점)
• 키워드: 95점
• 패턴: 80점

💰 예상가: $1,000~$5,000
```

#### 5.2 DiscordNotifier

**기능**:
- Embed 형식 알림
- 버튼 링크 (GoDaddy, Namecheap)
- 일일 리포트
- 에러 알림

---

### 6. Web 모듈

#### FastAPI 앱

**페이지 엔드포인트**:
| 경로 | 메서드 | 설명 |
|-----|--------|------|
| `/` | GET | 메인 페이지 (도메인 목록, 필터링, 정렬) |
| `/watchlist` | GET | 워치리스트 |
| `/domain/{id}` | GET | 도메인 상세 |
| `/logs` | GET | 크롤링 로그 |
| `/keywords` | GET | 키워드 관리 페이지 |
| `/settings` | GET | 시스템 설정 페이지 |

**API 엔드포인트**:
| 경로 | 메서드 | 설명 |
|-----|--------|------|
| `/api/stats` | GET | 통계 API (차트 데이터) |
| `/api/domains` | GET | 도메인 목록 API |
| `/api/health` | GET | 헬스체크 |
| `/api/watchlist/add` | POST | 워치리스트 추가 |
| `/api/watchlist/{id}` | DELETE | 워치리스트 삭제 |
| `/api/keywords` | GET | 키워드 목록 (기본+커스텀) |
| `/api/keywords` | POST | 커스텀 키워드 추가 |
| `/api/keywords/{keyword}` | PUT | 커스텀 키워드 수정 |
| `/api/keywords/{keyword}` | DELETE | 커스텀 키워드 삭제 |
| `/api/settings` | GET | 런타임 설정 조회 |
| `/api/settings` | POST | 런타임 설정 저장 |
| `/api/settings/reset` | POST | 런타임 설정 초기화 |
| `/api/crawl/trigger` | POST | 수동 크롤링 트리거 |
| `/api/crawl/status` | GET | 크롤링 상태 조회 |
| `/api/export/csv` | GET | CSV 내보내기 |

#### 런타임 설정 시스템

웹 대시보드에서 변경 가능한 설정은 `data/runtime_settings.json`에 저장됩니다.

```json
{
  "crawl_full_enabled": true,
  "crawl_full_time": "06:00",
  "crawl_week_enabled": true,
  "crawl_week_interval_hours": 3,
  "crawl_day_enabled": true,
  "crawl_day_interval_minutes": 30,
  "min_domain_length": 3,
  "max_domain_length": 12,
  "allowed_tlds": "com,net,io,ai,co,kr",
  "allow_numbers": false,
  "allow_hyphens": false,
  "min_score_alert": 70,
  "daily_report_time": "08:00",
  "heartbeat_interval_minutes": 0,
  "log_level": "INFO"
}
```

설정 변경 시 스케줄러가 자동으로 재설정됩니다 (`reload_scheduler` 메서드).

#### 키워드 분류

커스텀 키워드는 4가지 분류를 지원합니다:
- **TECH**: 기술 관련 (ai, api, cloud 등)
- **FINANCE**: 금융 관련 (pay, bank, coin 등)
- **BUSINESS**: 비즈니스 관련 (pro, hub, market 등)
- **GENERIC**: 일반 (best, top, go 등)

커스텀 키워드는 `data/keywords.json`에 저장됩니다:
```json
{
  "keyword": {"score": 90, "category": "TECH"}
}
```

#### 템플릿

- Jinja2 기반
- Bootstrap 5 (CDN)
- 다크/라이트 테마 토글
- 반응형 디자인
- Chart.js 차트 (TLD 분포, 점수 분포)

---

## 데이터 흐름

```
1. 크롤링
   ExpiredDomains.net → httpx → BeautifulSoup → Raw Domain List

2. 파싱 & 필터링
   Raw Domain List → DomainParser → Filtered Domains

3. 평가
   Filtered Domains → Scorer (Length + Keyword + Pattern) → Scored Domains

4. 저장
   Scored Domains → SQLite (aiosqlite) → domains.db

5. 알림
   High Score Domains → NotificationManager → Telegram / Discord

6. 표시
   domains.db → FastAPI → Web Dashboard
```

---

## 리소스 관리

### 메모리 제한 (systemd)

```ini
MemoryMax=512M      # 최대 메모리
MemoryHigh=400M     # 경고 임계값
CPUQuota=50%        # CPU 사용률 제한
```

### 예상 리소스 사용량

| 상태 | CPU | RAM | 네트워크 |
|-----|-----|-----|---------|
| 유휴 | 1-5% | 100-150MB | 0 |
| 크롤링 | 20-30% | 200-300MB | ~1MB/s |
| 웹 접속 | 5-10% | 150-200MB | ~0.1MB/s |

---

## 에러 처리

### 재시도 정책

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
```

### 에러 알림

- 크롤링 실패 시 Telegram/Discord 에러 알림
- 서비스 재시작 시 시작 알림
- journald 로그 기록

### Watchdog

```ini
WatchdogSec=300     # 5분 이내 응답 없으면 재시작
```

---

## 확장성

### 추가 가능한 기능

1. **추가 크롤링 소스**
   - park.io API
   - NameJet API
   - DropCatch API

2. **추가 평가 지표**
   - Moz DA/PA
   - WHOIS 도메인 나이
   - 백링크 수

3. **추가 알림 채널**
   - Slack
   - Email
   - SMS (Twilio)

4. **백오더 자동화**
   - GoDaddy API 연동
   - 자동 입찰 기능

---

## 보안 고려사항

1. **API 토큰 보호**
   - `.env` 파일 사용
   - `.gitignore`에 포함

2. **네트워크 보안**
   - 웹 대시보드는 로컬 네트워크만 접근 권장
   - 외부 접근 시 nginx + SSL 사용

3. **시스템 보호**
   - systemd 리소스 제한
   - 일반 사용자 권한으로 실행

---

## 모니터링

### 로그 확인

```bash
# 실시간 로그
journalctl -u domain-sniper -f

# 에러만 필터
journalctl -u domain-sniper -p err

# 특정 시간 이후
journalctl -u domain-sniper --since "1 hour ago"
```

### 상태 확인

```bash
# 서비스 상태
systemctl status domain-sniper

# 리소스 사용량
htop

# 디스크 사용량
df -h
du -sh ~/domain-sniper/*
```

### 헬스체크 API

```bash
curl http://localhost:8000/api/health
# {"status": "healthy", "database": "connected"}
```
