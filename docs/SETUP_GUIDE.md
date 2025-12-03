# 📘 Domain Sniper 상세 설치 가이드

라즈베리파이4에서 Domain Sniper를 단계별로 설치하는 완전한 가이드입니다.

## 📋 목차

1. [사전 준비](#1-사전-준비)
2. [라즈베리파이 OS 설치](#2-라즈베리파이-os-설치)
3. [시스템 초기 설정](#3-시스템-초기-설정)
4. [Domain Sniper 설치](#4-domain-sniper-설치)
5. [Telegram Bot 설정](#5-telegram-bot-설정)
6. [Discord Webhook 설정](#6-discord-webhook-설정-선택)
7. [서비스 시작 및 확인](#7-서비스-시작-및-확인)
8. [웹 대시보드 접속](#8-웹-대시보드-접속)
9. [고급 설정](#9-고급-설정)
10. [문제 해결](#10-문제-해결)

---

## 1. 사전 준비

### 필요 장비

| 장비 | 필수 여부 | 설명 |
|-----|---------|------|
| Raspberry Pi 4 | ✅ 필수 | 4GB 또는 8GB 권장 |
| microSD 카드 | ✅ 필수 | 16GB 이상, Class 10 |
| 전원 어댑터 | ✅ 필수 | 5V 3A USB-C |
| 이더넷 케이블 | 권장 | 안정적인 네트워크 |
| 케이스 + 쿨러 | 권장 | 발열 관리 |

### 준비물

- [ ] Telegram 계정 (알림 수신용)
- [ ] Discord 계정 (선택사항)
- [ ] SSH 클라이언트 (Windows: PuTTY, Mac/Linux: 터미널)

---

## 2. 라즈베리파이 OS 설치

### 2.1 Raspberry Pi Imager 다운로드

공식 사이트에서 다운로드: https://www.raspberrypi.com/software/

### 2.2 OS 이미지 굽기

1. Raspberry Pi Imager 실행
2. **OS 선택**: Raspberry Pi OS (64-bit) Lite 권장
3. **저장소 선택**: microSD 카드
4. **설정** (⚙️ 버튼):
   - 호스트네임: `raspberrypi`
   - SSH 활성화: ✅
   - 사용자명: `pi`
   - 비밀번호: (원하는 비밀번호)
   - Wi-Fi 설정 (필요시)
   - 로케일: `Asia/Seoul`
5. **쓰기** 클릭

### 2.3 첫 부팅

1. microSD 카드를 라즈베리파이에 삽입
2. 이더넷 케이블 연결 (권장)
3. 전원 연결
4. 1-2분 대기 (첫 부팅 시간)

---

## 3. 시스템 초기 설정

### 3.1 SSH 접속

```bash
# Windows (PowerShell) 또는 Mac/Linux 터미널
ssh pi@raspberrypi.local
# 또는 IP 주소로 접속
ssh pi@192.168.x.x
```

### 3.2 시스템 업데이트

```bash
sudo apt update && sudo apt upgrade -y
sudo apt autoremove -y
```

### 3.3 시간대 설정 확인

```bash
# 현재 시간 확인
date

# 시간대 변경 (필요시)
sudo raspi-config
# → Localisation Options → Timezone → Asia → Seoul
```

### 3.4 스왑 메모리 증가 (권장)

```bash
# 현재 스왑 확인
free -h

# 스왑 크기 변경 (1GB로)
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# CONF_SWAPSIZE=1024 로 변경
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# 확인
free -h
```

---

## 4. Domain Sniper 설치

### 4.1 프로젝트 다운로드

```bash
cd ~
git clone https://github.com/YawnsDuzin/DropDomainHunter.git domain-sniper
cd domain-sniper
```

### 4.2 자동 설치 실행

```bash
chmod +x install.sh
./install.sh
```

설치 과정:
1. 시스템 패키지 업데이트
2. Python 3 및 pip 설치
3. 가상환경 생성
4. 의존성 설치
5. systemd 서비스 등록

### 4.3 수동 설치 (선택)

자동 설치가 실패하는 경우:

```bash
# 필수 패키지
sudo apt install -y python3 python3-pip python3-venv git

# 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install --upgrade pip
pip install -r requirements.txt

# 환경 설정 파일 복사
cp .env.example .env

# 로그 디렉토리 생성
mkdir -p logs

# 서비스 파일 복사
sudo cp domain-sniper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable domain-sniper
```

---

## 5. Telegram Bot 설정

### 5.1 Bot 생성

1. Telegram에서 **@BotFather** 검색 후 대화 시작
2. `/newbot` 명령어 입력
3. 봇 이름 입력 (예: `My Domain Sniper`)
4. 봇 사용자명 입력 (예: `my_domain_sniper_bot`)
5. **토큰 저장** (예: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 5.2 Chat ID 확인

1. 생성한 봇에게 아무 메시지 전송 (예: `/start`)
2. **@userinfobot** 에게 메시지 전송
3. 표시되는 **ID** 번호 저장 (예: `123456789`)

### 5.3 .env 파일 설정

```bash
nano .env
```

다음 항목 수정:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

저장: `Ctrl+O`, `Enter`, `Ctrl+X`

---

## 6. Discord Webhook 설정 (선택)

### 6.1 Webhook 생성

1. Discord 서버 설정 → 연동 → 웹후크
2. **새 웹후크** 클릭
3. 이름 설정 (예: `Domain Sniper`)
4. 채널 선택
5. **웹후크 URL 복사**

### 6.2 .env 파일 설정

```bash
nano .env
```

다음 항목 추가:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## 7. 서비스 시작 및 확인

### 7.1 서비스 시작

```bash
sudo systemctl start domain-sniper
```

### 7.2 상태 확인

```bash
sudo systemctl status domain-sniper
```

정상 출력 예시:
```
● domain-sniper.service - Domain Sniper - 도메인 스나이핑 서비스
     Loaded: loaded (/etc/systemd/system/domain-sniper.service; enabled)
     Active: active (running) since ...
```

### 7.3 로그 확인

```bash
# 실시간 로그
journalctl -u domain-sniper -f

# 최근 100줄
journalctl -u domain-sniper -n 100
```

### 7.4 Telegram 테스트

서비스 시작 시 Telegram으로 시작 알림이 도착해야 합니다:
```
🚀 Domain Sniper 시작됨

⏰ 시작 시간: 2024-01-01 12:00:00
🔄 전체 스캔: 매일 06:00
🔄 7일 스캔: 3시간마다
🔄 1일 스캔: 30분마다
```

---

## 8. 웹 대시보드 접속

### 8.1 브라우저에서 접속

```
http://raspberrypi.local:8000
```

또는 IP 주소로:
```
http://192.168.x.x:8000
```

### 8.2 기능

- **홈**: 도메인 목록 및 통계
- **관심목록**: 북마크한 도메인
- **로그**: 크롤링 기록
- **설정**: 현재 설정 확인

---

## 9. 고급 설정

### 9.1 크롤링 주기 변경

```bash
nano .env
```

```env
# 전체 스캔: 매 12시간
CRAWL_FULL_INTERVAL_HOURS=12

# 7일 이내: 매 2시간
CRAWL_WEEK_INTERVAL_HOURS=2

# 1일 이내: 매 15분
CRAWL_DAY_INTERVAL_MINUTES=15
```

변경 후 서비스 재시작:
```bash
sudo systemctl restart domain-sniper
```

### 9.2 도메인 필터 조정

```env
# 4~8자 도메인만 수집
MIN_DOMAIN_LENGTH=4
MAX_DOMAIN_LENGTH=8

# .ai TLD 추가
ALLOWED_TLDS=com,net,io,co,ai

# 숫자 포함 도메인 허용
ALLOW_NUMBERS=true
```

### 9.3 알림 점수 조정

```env
# 80점 이상만 알림
MIN_SCORE_ALERT=80

# 매일 오전 9시 리포트
DAILY_REPORT_TIME=09:00
```

### 9.4 커스텀 키워드 추가

```bash
nano data/keywords.json
```

예시:
```json
{
    "fintech": 95,
    "saas": 90,
    "defi": 95,
    "metaverse": 85
}
```

---

## 10. 문제 해결

### 문제: 서비스가 시작되지 않음

```bash
# 상세 로그 확인
journalctl -u domain-sniper -n 50 --no-pager

# 수동 실행으로 에러 확인
cd ~/domain-sniper
source venv/bin/activate
python main.py
```

### 문제: Telegram 알림이 오지 않음

1. 토큰 확인:
```bash
grep TELEGRAM .env
```

2. 봇에게 먼저 메시지 전송했는지 확인

3. 수동 테스트:
```bash
cd ~/domain-sniper
source venv/bin/activate
python -c "
from notifier.telegram import TelegramNotifier
import asyncio
n = TelegramNotifier()
asyncio.run(n.send_message('테스트 메시지'))
"
```

### 문제: 메모리 부족

```bash
# 메모리 확인
free -h

# 불필요한 서비스 중지
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon

# 스왑 증가 (위 3.4 참조)
```

### 문제: 웹 대시보드 접속 불가

```bash
# 포트 확인
sudo netstat -tlnp | grep 8000

# 방화벽 확인
sudo ufw status

# 방화벽 허용 (필요시)
sudo ufw allow 8000
```

### 문제: 크롤링이 실패함

```bash
# 네트워크 확인
ping -c 3 expireddomains.net

# DNS 확인
nslookup expireddomains.net

# 수동 크롤링 테스트
cd ~/domain-sniper
source venv/bin/activate
python main.py --crawl-now
```

---

## 🎉 설치 완료!

축하합니다! Domain Sniper가 정상적으로 설치되었습니다.

### 다음 단계

1. 며칠간 로그를 모니터링하여 정상 작동 확인
2. 필터 설정을 조정하여 원하는 도메인만 수집
3. 알림 점수를 조정하여 중요한 도메인만 알림 수신

### 유용한 명령어 요약

```bash
# 서비스 관리
sudo systemctl start|stop|restart|status domain-sniper

# 로그 확인
journalctl -u domain-sniper -f

# 즉시 크롤링
cd ~/domain-sniper && source venv/bin/activate && python main.py --crawl-now

# 설정 변경 후 재시작
sudo systemctl restart domain-sniper
```

문제가 있으시면 GitHub Issues에 문의해주세요!
