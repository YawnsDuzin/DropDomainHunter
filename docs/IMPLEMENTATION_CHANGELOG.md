# Domain Sniper v1.1.0 - 구현 변경 로그

## 개요

이 문서는 ISSUES_AND_IMPROVEMENTS.md에서 제안된 개선 사항들의 구현 내용을 설명합니다.

---

## 1. 차단 방지 시스템 (Anti-Blocking)

### 파일: `crawler/anti_blocking.py`

#### 1.1 User-Agent 로테이션

**구현 내용:**
- 20개 이상의 최신 브라우저 User-Agent 목록
- Chrome, Firefox, Safari, Edge 지원 (Windows, Mac, Linux)
- 랜덤 선택, 순차 선택, 쿨다운 기반 선택 지원

```python
from crawler.anti_blocking import UserAgentRotator

rotator = UserAgentRotator()
ua = rotator.get_random()  # 무작위 선택
ua = rotator.get_with_cooldown(300)  # 최근 5분 내 사용한 UA 제외
```

#### 1.2 적응형 딜레이 (Adaptive Delay)

**구현 내용:**
- 기본 딜레이: 2초, 최대: 60초
- 성공 시 딜레이 감소 (10번 연속 성공 시 10% 감소)
- 429 에러 시 3배 증가, 403 에러 시 2배 증가
- 랜덤 지터로 패턴 감지 방지

```python
from crawler.anti_blocking import AdaptiveDelay

delay = AdaptiveDelay(base_delay=2.0)
await delay.wait()
delay.on_success()  # 성공 시
delay.on_error(429)  # Rate limit 시
```

#### 1.3 프록시 로테이션

**구현 내용:**
- 프록시 풀 관리
- 실패 프록시 자동 제외 (3회 실패 시)
- 모든 프록시 실패 시 자동 리셋

```python
from crawler.anti_blocking import ProxyRotator

rotator = ProxyRotator()
rotator.add_proxies(["http://proxy1:8080", "http://proxy2:8080"])
proxy = rotator.get_proxy()  # {"http://": "...", "https://": "..."}
```

#### 1.4 인간 행동 시뮬레이션

**구현 내용:**
- 불규칙한 대기 시간 (10% 확률로 30-60초 대기)
- 20-30개 요청마다 휴식 (5-10분)
- 브라우저 헤더 완전 모방 (Sec-Fetch-* 헤더 포함)

---

## 2. 도메인 가용성 확인

### 파일: `checker/availability.py`

#### 2.1 RDAP 프로토콜 지원

**구현 내용:**
- 주요 TLD별 RDAP 서버 매핑 (com, net, org, io, ai 등)
- IANA 부트스트랩 서버 폴백
- 상세 도메인 정보 파싱 (등록일, 만료일, 레지스트라)

```python
from checker.availability import RDAPChecker

checker = RDAPChecker()
result = await checker.check("example.com")
print(result.available)  # True/False/None
print(result.status)  # DomainStatus.AVAILABLE, REGISTERED 등
```

#### 2.2 WHOIS 직접 조회

**구현 내용:**
- python-whois 없이 소켓 직접 통신
- 다양한 WHOIS 서버 지원
- 미등록 패턴 자동 감지

```python
from checker.availability import WHOISChecker

checker = WHOISChecker()
result = await checker.check("example.com")
```

#### 2.3 통합 도메인 확인

**구현 내용:**
- RDAP 우선, 실패 시 WHOIS 폴백
- 결과 캐싱 (기본 1시간 TTL)
- 배치 확인 지원

```python
from checker.availability import DomainAvailabilityChecker

checker = DomainAvailabilityChecker()
result = await checker.check("example.com")

# 배치 확인
results = await checker.check_batch(["a.com", "b.com", "c.com"])
```

---

## 3. 도메인 히스토리 확인

### 파일: `checker/history.py`

**구현 내용:**
- Archive.org Wayback Machine API 통합
- CDX API로 상세 스냅샷 조회
- 도메인 연령 점수 계산

```python
from checker.history import DomainHistoryChecker, DomainAgeScorer

checker = DomainHistoryChecker()
history = await checker.check("example.com")

print(history.has_history)
print(history.first_seen)
print(history.snapshot_count)
print(history.age_years)

# 점수 계산
scorer = DomainAgeScorer()
bonus = scorer.calculate_score(history)  # 0-20점
```

---

## 4. HTML 파서 강화

### 파일: `crawler/parser.py`

#### 4.1 다중 파싱 전략

**구현 내용:**
- 클래스 기반 파싱 (신뢰도 95%)
- HTML 구조 기반 파싱 (신뢰도 80%)
- 정규표현식 기반 파싱 (신뢰도 50%)
- 전략 실패 시 자동 폴백

```python
from crawler.parser import RobustParser

parser = RobustParser()
result = parser.parse(html, source="expireddomains.net")

print(result.strategy_used)  # ParsingStrategy.CLASS_BASED
print(result.confidence)  # 0.95
print(result.domains)  # [{"name": "...", "tld": "..."}]
```

#### 4.2 향상된 날짜 파싱

**지원 형식:**
- "X days", "X hours", "X weeks", "X months"
- ISO 형식 (2024-01-15)
- 영문 형식 (Jan 15, 2024)
- 숫자 형식 (01/15/2024, 15.01.2024)

#### 4.3 스마트 키워드 매칭

**구현 내용:**
- 오탐 방지 (예: "classic"에서 "ass" 미검출)
- 단어 경계 고려 (짧은 키워드는 위치 검사)

```python
from crawler.parser import SmartKeywordMatcher

SmartKeywordMatcher.is_keyword_match("aicloud", "ai")  # True
SmartKeywordMatcher.is_keyword_match("again", "ai")    # False (오탐 방지)
```

---

## 5. 알림 시스템 개선

### 파일: `notifier/priority.py`

#### 5.1 알림 우선순위

**우선순위 레벨:**
| 레벨 | 조건 | 동작 |
|-----|------|------|
| CRITICAL | 90점+ 또는 오늘 만료 | 즉시 알림 + 30분 반복 |
| HIGH | 80점+ 또는 3일 내 만료 | 즉시 알림 + 60분 반복 |
| MEDIUM | 70점+ 또는 7일 내 만료 | 즉시 알림 |
| LOW | 60점+ | 즉시 알림 |
| BATCH | 60점 미만 | 1시간마다 배치 |

```python
from notifier.priority import NotificationPriorityManager, Priority

manager = NotificationPriorityManager()
prioritized = manager.calculate_priority(domain)

print(prioritized.priority)  # Priority.HIGH
print(prioritized.reasons)   # ["높은 점수 (85점)"]
```

#### 5.2 스로틀링

**구현 내용:**
- 같은 도메인 재알림 쿨다운 (기본 1시간)
- 일일 최대 알림 수 제한 (기본 100개)

### 파일: `notifier/telegram_bot.py`

#### 5.3 Telegram 콜백 핸들러

**지원 명령어:**
- `/start` - 봇 시작
- `/help` - 도움말
- `/status` - 시스템 상태
- `/top` - TOP 10 도메인
- `/watchlist` - 관심 목록
- `/search [키워드]` - 검색

**콜백 액션:**
- 🔍 상세보기 - 도메인 상세 정보
- ⭐ 관심등록 - 관심 목록 추가
- 🚫 무시 - 도메인 무시
- 🔄 가용성 확인 - RDAP/WHOIS 확인

---

## 6. 웹 인증

### 파일: `web/auth.py`

**구현 내용:**
- HTTP Basic Auth 지원
- 세션 기반 인증 (쿠키)
- 로그인 실패 잠금 (5회 실패 시 5분 잠금)
- 타이밍 공격 방지

**설정:**
```env
WEB_USERNAME=admin
WEB_PASSWORD=your_secure_password
```

**사용법:**
```python
from web.auth import create_auth_routes, require_auth

# 라우트 추가
create_auth_routes(app)

# 인증 필수 엔드포인트
@app.get("/protected")
async def protected(user: str = Depends(require_auth)):
    return {"user": user}
```

---

## 7. 새로운 설정 옵션

### `.env` 추가 항목

```env
# 웹 인증
WEB_USERNAME=admin
WEB_PASSWORD=your_password

# 프록시
USE_PROXY=false
PROXY_LIST=http://proxy1:8080,http://proxy2:8080

# 도메인 확인
CHECK_AVAILABILITY=true
CHECK_HISTORY=true
```

---

## 8. 모듈 구조

```
DropDomainHunter/
├── checker/
│   ├── __init__.py
│   ├── availability.py  # WHOIS/RDAP 가용성 확인
│   └── history.py       # Archive.org 히스토리
├── crawler/
│   ├── anti_blocking.py # 차단 방지 (UA 로테이션, 딜레이 등)
│   ├── parser.py        # 강화된 HTML 파서
│   └── ...
├── notifier/
│   ├── priority.py      # 알림 우선순위
│   ├── telegram_bot.py  # Telegram 콜백 핸들러
│   └── ...
├── web/
│   ├── auth.py          # 웹 인증
│   └── ...
└── ...
```

---

## 9. 사용 예시

### 전체 플로우

```python
import asyncio
from crawler.anti_blocking import AntiBlockingManager
from crawler.parser import RobustParser
from checker.availability import DomainAvailabilityChecker
from checker.history import DomainHistoryChecker, DomainAgeScorer
from notifier.priority import NotificationPriorityManager

async def process_domain(domain_data):
    # 1. 파싱
    parser = RobustParser()
    result = parser.parse(html)

    # 2. 가용성 확인
    availability_checker = DomainAvailabilityChecker()
    availability = await availability_checker.check(domain_data['full_name'])

    if not availability.available:
        return  # 이미 등록됨

    # 3. 히스토리 확인
    history_checker = DomainHistoryChecker()
    history = await history_checker.check(domain_data['full_name'])

    # 4. 점수 계산 (히스토리 보너스 추가)
    age_scorer = DomainAgeScorer()
    history_bonus = age_scorer.calculate_score(history)
    total_score = domain_data['score'] + history_bonus

    # 5. 알림 우선순위 결정
    priority_manager = NotificationPriorityManager()
    prioritized = priority_manager.calculate_priority(domain)

    if priority_manager.should_send_now(prioritized):
        await send_notification(domain)
```

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|-----|------|----------|
| 1.1.0 | 2024-12 | 차단 방지, 도메인 확인, 알림 개선, 웹 인증 |
| 1.0.0 | 2024-12 | 초기 릴리즈 |
