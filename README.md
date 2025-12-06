# 🎯 Domain Sniper

**라즈베리파이4 무중단 운영 도메인 스나이핑 시스템**

고가치 만료 도메인을 자동으로 탐지하고, 가치를 평가하여 Telegram/Discord로 알림을 보내는 경량화된 시스템입니다.

## ✨ 주요 기능

- 🔍 **자동 크롤링**: expireddomains.net에서 만료 예정 도메인 수집
- 📊 **AI 가치 평가**: 길이, 키워드, 발음 패턴 기반 점수 산정
- 📱 **실시간 알림**: Telegram Bot & Discord Webhook 지원
- 🖥️ **웹 대시보드**: 반응형 웹 UI (FastAPI + Jinja2)
- ⏰ **무중단 운영**: systemd 서비스로 24/7 자동 실행
- 🔋 **저전력**: 라즈베리파이4에 최적화된 경량 설계

## 📋 시스템 요구사항

| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| 하드웨어 | Raspberry Pi 4 (2GB) | Raspberry Pi 4 (4GB/8GB) |
| OS | Raspberry Pi OS Lite | Raspberry Pi OS (64-bit) |
| Python | 3.9+ | 3.11+ |
| 저장공간 | 2GB | 8GB+ |
| 네트워크 | 유선/무선 | 유선 권장 |

## 🚀 빠른 시작

### 1. 프로젝트 클론

```bash
git clone https://github.com/YawnsDuzin/DropDomainHunter.git
cd DropDomainHunter
```

### 2. 자동 설치

```bash
chmod +x install.sh
./install.sh
```

### 3. 환경 설정

```bash
nano .env
```

필수 설정:
```env
# ExpiredDomains.net 로그인 (필수)
EXPIRED_DOMAINS_USERNAME=your_username
EXPIRED_DOMAINS_PASSWORD=your_password

# Telegram 알림
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

> ⚠️ ExpiredDomains.net 계정이 없으면 https://www.expireddomains.net 에서 가입하세요.

### 4. 서비스 시작

```bash
sudo systemctl start domain-sniper
sudo systemctl status domain-sniper
```

### 5. 웹 대시보드 접속

```
http://raspberrypi.local:8000
# 또는
http://<라즈베리파이IP>:8000
```

## 📁 프로젝트 구조

```
domain-sniper/
├── main.py                 # 메인 엔트리포인트
├── config.py               # 설정 관리
├── requirements.txt        # Python 의존성
├── .env.example           # 환경변수 템플릿
├── domain-sniper.service  # systemd 서비스
├── install.sh             # 설치 스크립트
├── uninstall.sh           # 제거 스크립트
│
├── crawler/               # 크롤링 모듈
│   ├── expired_domains.py # 만료 도메인 크롤러
│   └── parser.py          # HTML/JSON 파서
│
├── scorer/                # 점수 평가 모듈
│   ├── length.py          # 길이 점수
│   ├── keyword.py         # 키워드 점수
│   ├── pattern.py         # 패턴 점수
│   └── evaluator.py       # 통합 평가기
│
├── notifier/              # 알림 모듈
│   ├── telegram.py        # Telegram Bot
│   ├── discord.py         # Discord Webhook
│   └── manager.py         # 통합 관리자
│
├── database/              # 데이터베이스
│   ├── models.py          # ORM 모델
│   └── schema.sql         # SQLite 스키마
│
├── web/                   # 웹 대시보드
│   ├── app.py             # FastAPI 앱
│   └── templates/         # Jinja2 템플릿
│
├── data/
│   └── keywords.json      # 고가치 키워드 DB
│
└── docs/                  # 문서
    ├── SETUP_GUIDE.md     # 상세 설치 가이드
    └── ARCHITECTURE.md    # 아키텍처 문서
```

## ⚙️ 설정 옵션

### 크롤링 설정

| 환경변수 | 기본값 | 설명 |
|---------|-------|------|
| `CRAWL_FULL_INTERVAL_HOURS` | 24 | 전체 스캔 주기 |
| `CRAWL_WEEK_INTERVAL_HOURS` | 3 | 7일 이내 스캔 주기 |
| `CRAWL_DAY_INTERVAL_MINUTES` | 30 | 1일 이내 스캔 주기 |

### 도메인 필터

| 환경변수 | 기본값 | 설명 |
|---------|-------|------|
| `MIN_DOMAIN_LENGTH` | 3 | 최소 도메인 길이 |
| `MAX_DOMAIN_LENGTH` | 12 | 최대 도메인 길이 |
| `ALLOWED_TLDS` | com,net,io,co,kr | 허용 TLD |
| `ALLOW_NUMBERS` | false | 숫자 포함 허용 |
| `ALLOW_HYPHENS` | false | 하이픈 포함 허용 |

### 알림 설정

| 환경변수 | 기본값 | 설명 |
|---------|-------|------|
| `MIN_SCORE_ALERT` | 70 | 알림 최소 점수 |
| `DAILY_REPORT_TIME` | 08:00 | 일일 리포트 시간 |

## 📊 점수 체계

### 가중치
- **길이 점수**: 35%
- **키워드 점수**: 40%
- **패턴 점수**: 25%

### 등급
| 점수 | 등급 | 설명 |
|-----|------|------|
| 90+ | 🔥🔥🔥 | 프리미엄 도메인 |
| 80-89 | 🔥🔥 | 고가치 도메인 |
| 70-79 | 🔥 | 좋은 도메인 |
| 60-69 | ✨ | 괜찮은 도메인 |
| 60 미만 | - | 일반 도메인 |

## 🔧 관리 명령어

```bash
# 서비스 상태 확인
sudo systemctl status domain-sniper

# 서비스 시작/중지/재시작
sudo systemctl start domain-sniper
sudo systemctl stop domain-sniper
sudo systemctl restart domain-sniper

# 로그 확인
journalctl -u domain-sniper -f

# 즉시 크롤링 실행
cd /home/dzp/domain-sniper
source venv/bin/activate
python main.py --crawl-now
```

## 🛠️ 트러블슈팅

### 서비스가 시작되지 않을 때
```bash
# 로그 확인
journalctl -u domain-sniper -n 50

# 수동 실행으로 에러 확인
cd /home/dzp/domain-sniper
source venv/bin/activate
python main.py
```

### Telegram 알림이 오지 않을 때
1. `TELEGRAM_BOT_TOKEN` 확인
2. `TELEGRAM_CHAT_ID` 확인 (@userinfobot으로 확인)
3. 봇에게 먼저 메시지 전송

### 메모리 부족 시
```bash
# 스왑 메모리 확인
free -h

# 스왑 추가 (필요시)
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile  # CONF_SWAPSIZE=1024
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## 📈 리소스 사용량

| 항목 | 예상 사용량 |
|-----|-----------|
| CPU | 평상시 5%, 크롤링 시 30% |
| RAM | 150~300MB |
| Storage | DB 100MB/년, 로그 50MB/월 |
| Network | 100MB/일 (크롤링) |

## 📜 라이선스

MIT License

## 🤝 기여

버그 리포트 및 기능 제안은 [Issues](https://github.com/YawnsDuzin/DropDomainHunter/issues)에 등록해주세요.

## 📞 문의

- GitHub Issues: [YawnsDuzin/DropDomainHunter](https://github.com/YawnsDuzin/DropDomainHunter/issues)
