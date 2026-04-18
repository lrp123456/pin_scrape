#!/bin/bash
# Pinterest Scraper - 宿主机可视化测试（带浏览器窗口）
# 用法: ./test_visual.sh [关键词]

set -e

QUERY="${1:-test}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Pinterest Scraper - 可视化测试"
echo "=========================================="
echo ""
echo "⚠️  此测试会显示浏览器窗口，需要 GUI 环境"
echo "   确保你在桌面环境运行此脚本"
echo ""
echo "搜索关键词: $QUERY"
echo ""

# 检查是否在桌面环境
if [ -z "$DISPLAY" ]; then
    echo "❌ 未检测到 DISPLAY 环境变量"
    echo "   此脚本需要在桌面环境运行"
    echo ""
    echo "替代方案:"
    echo "1. 在桌面终端中运行此脚本"
    echo "2. 使用 ./test_local.sh 进行无头测试"
    echo "3. 使用 ./test_docker.sh 在 Docker 中测试"
    exit 1
fi

echo "✅ 检测到 DISPLAY=$DISPLAY"
echo ""

# 运行可视化测试
echo "📋 启动浏览器窗口..."
echo "----------------------------------------"
echo "提示: 你可以看到浏览器操作过程"
echo "      按 Ctrl+C 可随时停止"
echo ""

python3 main.py \
  -q "$QUERY" \
  -n 3 \
  --no-headless \
  -o "$SCRIPT_DIR/output/visual_test_$(date +%Y%m%d_%H%M%S)" \
  --debug

RESULT=$?

echo ""
echo "=========================================="
if [ $RESULT -eq 0 ]; then
    echo "✅ 可视化测试完成！"
else
    echo "❌ 测试失败"
fi
echo "=========================================="
