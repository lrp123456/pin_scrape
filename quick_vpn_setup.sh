#!/bin/bash
# 快速配置VPN代理 - 适用于Clash等HTTP代理
# 用法: ./quick_vpn_setup.sh [代理端口]

set -e

PROXY_PORT="${1:-7890}"
COMPOSE_FILE="/home/lrp/n8n/docker-compose.yml"

echo "=========================================="
echo "Pinterest Scraper - VPN代理快速配置"
echo "=========================================="
echo ""
echo "代理端口: $PROXY_PORT"
echo ""

# 检测宿主机IP（用于Docker容器访问）
HOST_IP=$(ip route | grep default | awk '{print $3}' | head -1)
echo "宿主机IP: $HOST_IP"
echo ""

# 备份原文件
if [ ! -f "$COMPOSE_FILE.backup" ]; then
    cp "$COMPOSE_FILE" "$COMPOSE_FILE.backup"
    echo "✅ 已备份原文件: docker-compose.yml.backup"
fi

# 检查是否已配置代理
if grep -q "HTTP_PROXY" "$COMPOSE_FILE"; then
    echo "⚠️  检测到已有代理配置，将更新..."
    # 删除旧配置
    sed -i '/HTTP_PROXY/d' "$COMPOSE_FILE"
    sed -i '/HTTPS_PROXY/d' "$COMPOSE_FILE"
    sed -i '/NO_PROXY/d' "$COMPOSE_FILE"
fi

# 在python-runner服务中添加代理配置
echo "📋 配置Docker代理..."

# 使用sed在environment部分添加代理配置
sed -i '/python-runner:/,/^  [a-z]/ {
    /environment:/a\      - HTTP_PROXY=http://'