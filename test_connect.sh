#!/bin/bash
# Pinterest Scraper - 宿主机连接已有 Chrome 测试
# 用法: ./test_connect.sh [关键词]

set -e

QUERY="${1:-test}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Pinterest Scraper - 连接已有 Chrome 测试"
echo "=========================================="
echo ""
echo "此脚本测试连接到已运行的 Chrome 浏览器"
echo ""

# 检查 Chrome 是否在 9222 端口运行
echo "📋 检查 Chrome CDP 端口..."
echo "----------------------------------------"

if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then
    echo "✅ 发现 Chrome 在 localhost:9222"
    CDP_ENDPOINT="http://localhost:9222"
elif curl -s http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
    echo "✅ 发现 Chrome 在 127.0.0.1:9222"
    CDP_ENDPOINT="http://127.0.0.1:9222"
else
    echo "❌ 未找到在 9222 端口运行的 Chrome"
    echo ""
    echo "请先启动 Chrome:"
    echo "  方式 1: 使用本脚本自动启动"
    echo "    ./test_local.sh"
    echo ""
    echo "  方式 2: 手动启动 Chrome"
    echo "    google-chrome --remote-debugging-port=9222"
    echo ""
    exit 1
fi

echo "CDP 端点: $CDP_ENDPOINT"
echo ""

# 运行测试
echo "📋 运行测试..."
echo "----------------------------------------"

python3 main.py \
  -q "$QUERY" \
  -n 3 \
  --connect \
  --cdp-endpoint "$CDP_ENDPOINT" \
  -o "$SCRIPT_DIR/output/connect_test_$(date +%Y%m%d_%H%M%S)" \
  --debug

RESULT=$?

echo ""
echo "=========================================="
if [ $RESULT -eq 0 ]; then
    echo "✅ 连接测试成功！"
else
    echo "❌ 连接测试失败"
fi
echo "=========================================="
