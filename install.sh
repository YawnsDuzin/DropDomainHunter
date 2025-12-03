#!/bin/bash
# ============================================================
# Domain Sniper - 자동 설치 스크립트
# 라즈베리파이4 최적화 버전
# ============================================================

set -e  # 에러 발생 시 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로고 출력
echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║   🎯  Domain Sniper - 설치 스크립트                   ║"
echo "║       Raspberry Pi 4 Edition                          ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 현재 디렉토리 확인
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/home/pi/domain-sniper}"

echo -e "${YELLOW}📂 설치 디렉토리: ${INSTALL_DIR}${NC}"
echo ""

# 1. 시스템 업데이트
echo -e "${GREEN}[1/7] 시스템 업데이트 중...${NC}"
sudo apt update && sudo apt upgrade -y

# 2. 필수 패키지 설치
echo -e "${GREEN}[2/7] 필수 패키지 설치 중...${NC}"
sudo apt install -y python3 python3-pip python3-venv git

# 3. 설치 디렉토리 생성
echo -e "${GREEN}[3/7] 설치 디렉토리 준비 중...${NC}"
if [ ! -d "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
fi

# 현재 디렉토리와 설치 디렉토리가 다르면 복사
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo "파일 복사 중..."
    cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
fi

cd "$INSTALL_DIR"

# 4. Python 가상환경 생성
echo -e "${GREEN}[4/7] Python 가상환경 설정 중...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# pip 업그레이드
pip install --upgrade pip

# 5. 의존성 설치
echo -e "${GREEN}[5/7] 의존성 설치 중...${NC}"
pip install -r requirements.txt

# 6. 환경 설정 파일 생성
echo -e "${GREEN}[6/7] 환경 설정 파일 확인 중...${NC}"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}⚠️  .env 파일이 생성되었습니다.${NC}"
    echo -e "${YELLOW}   Telegram 토큰 등을 설정해주세요!${NC}"
else
    echo ".env 파일이 이미 존재합니다."
fi

# 로그 디렉토리 생성
mkdir -p logs

# 7. systemd 서비스 설치
echo -e "${GREEN}[7/7] systemd 서비스 설치 중...${NC}"

# 서비스 파일 경로 수정
sed -i "s|/home/pi/domain-sniper|$INSTALL_DIR|g" domain-sniper.service
sed -i "s|User=pi|User=$USER|g" domain-sniper.service
sed -i "s|Group=pi|Group=$USER|g" domain-sniper.service

# 서비스 파일 복사
sudo cp domain-sniper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable domain-sniper

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗"
echo -e "║  ✅ 설치가 완료되었습니다!                             ║"
echo -e "╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📋 다음 단계:${NC}"
echo ""
echo "  1. .env 파일 설정:"
echo -e "     ${YELLOW}nano $INSTALL_DIR/.env${NC}"
echo ""
echo "  2. Telegram Bot 설정:"
echo "     - @BotFather에서 봇 생성"
echo "     - TELEGRAM_BOT_TOKEN 입력"
echo "     - TELEGRAM_CHAT_ID 입력"
echo ""
echo "  3. 서비스 시작:"
echo -e "     ${YELLOW}sudo systemctl start domain-sniper${NC}"
echo ""
echo "  4. 상태 확인:"
echo -e "     ${YELLOW}sudo systemctl status domain-sniper${NC}"
echo ""
echo "  5. 로그 확인:"
echo -e "     ${YELLOW}journalctl -u domain-sniper -f${NC}"
echo ""
echo "  6. 웹 대시보드 접속:"
echo -e "     ${YELLOW}http://$(hostname -I | awk '{print $1}'):8000${NC}"
echo ""
echo -e "${GREEN}즐거운 도메인 헌팅 되세요! 🎯${NC}"
