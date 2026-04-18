#!/bin/bash
# Pinterest Scraper - 宿主机快速测试脚本
# 用法: ./test_local.sh [关键词] [数量]

set -e

# 默认参数
QUERY="${1:-现代简约}"
MAX_PINS="${2:-5}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Pinterest Scraper - 本地测试"
echo "=========================================="
echo ""
echo "搜索关键词: $QUERY"
echo "爬取数量: $MAX_PINS"
echo ""

# 检查 Python 是否可用
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查依赖
python3 -c "import playwright, aiohttp" 2>/dev/null || {
    echo "❌ 缺少依赖，请先安装:"
    echo "   pip3 install -r requirements.txt"
    echo "   playwright install chromium"
    exit 1
}

echo "✅ 依赖检查通过"
echo ""

# 运行测试
echo "📋 开始测试爬取..."
echo "----------------------------------------"

python3 main.py \
  -q "$QUERY" \
  -n "$MAX_PINS" \
  -o "$SCRIPT_DIR/output/test_$(date +%Y%m%d_%H%M%S)" \
  --debug

TEST_RESULT=$?

echo ""
echo "=========================================="
if [ $TEST_RESULT -eq 0 ]; then
    echo "✅ 测试成功！"
    echo ""
    echo "查看结果:"
    ls -la "$SCRIPT_DIR/output/"
else
    echo "❌ 测试失败 (退出码: $TEST_RESULT)"
    echo ""
    echo "排查步骤:"
    echo "1. 运行 ./check_env.sh 检查环境"
    echo "2. 查看 debug_screenshot.png 和 debug_data.json"
    echo "3. 使用 --no-headless 查看浏览器窗口"
fi
echo "=========================================="
