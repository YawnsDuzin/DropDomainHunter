#!/bin/bash
# ============================================================
# Domain Sniper - 제거 스크립트
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}"
echo "╔═══════════════════════════════════════════════════════╗"
echo "║  ⚠️  Domain Sniper 제거                                ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo -e "${NC}"

read -p "정말로 Domain Sniper를 제거하시겠습니까? (y/N): " confirm

if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "제거가 취소되었습니다."
    exit 0
fi

INSTALL_DIR="${INSTALL_DIR:-/home/pi/domain-sniper}"

# 1. 서비스 중지 및 제거
echo -e "${YELLOW}[1/3] 서비스 중지 중...${NC}"
sudo systemctl stop domain-sniper 2>/dev/null || true
sudo systemctl disable domain-sniper 2>/dev/null || true
sudo rm -f /etc/systemd/system/domain-sniper.service
sudo systemctl daemon-reload

# 2. 데이터 백업 확인
echo -e "${YELLOW}[2/3] 데이터 백업 확인...${NC}"
if [ -f "$INSTALL_DIR/domains.db" ]; then
    read -p "데이터베이스를 백업하시겠습니까? (y/N): " backup
    if [[ "$backup" == "y" || "$backup" == "Y" ]]; then
        BACKUP_FILE="$HOME/domains_backup_$(date +%Y%m%d_%H%M%S).db"
        cp "$INSTALL_DIR/domains.db" "$BACKUP_FILE"
        echo -e "${GREEN}백업 완료: $BACKUP_FILE${NC}"
    fi
fi

# 3. 파일 제거 확인
echo -e "${YELLOW}[3/3] 파일 제거...${NC}"
read -p "모든 파일을 삭제하시겠습니까? (y/N): " delete_all

if [[ "$delete_all" == "y" || "$delete_all" == "Y" ]]; then
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}모든 파일이 삭제되었습니다.${NC}"
else
    echo "파일은 유지됩니다: $INSTALL_DIR"
fi

echo ""
echo -e "${GREEN}Domain Sniper가 제거되었습니다.${NC}"
