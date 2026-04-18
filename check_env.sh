#!/bin/bash
# Pinterest Scraper - 宿主机环境检查脚本
# 用法: ./check_env.sh

echo "=========================================="
echo "Pinterest Scraper - 宿主机环境检查"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_pass() {
    echo -e "${GREEN}✅ $1${NC}"
}

check_fail() {
    echo -e "${RED}❌ $1${NC}"
}

check_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# 1. 检查 Python
echo "📋 1. 检查 Python"
echo "----------------------------------------"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    check_pass "Python 已安装: $PYTHON_VERSION"
else
    check_fail "Python3 未安装"
    echo "   请安装 Python 3.8+"
fi
echo ""

# 2. 检查 pip
echo "📋 2. 检查 pip"
echo "----------------------------------------"
if command -v pip3 &> /dev/null; then
    check_pass "pip3 已安装"
else
    check_fail "pip3 未安装"
    echo "   安装命令: sudo apt-get install python3-pip"
fi
echo ""

# 3. 检查 Playwright
echo "📋 3. 检查 Playwright"
echo "----------------------------------------"
python3 -c "import playwright" 2>/dev/null
if [ $? -eq 0 ]; then
    PW_VERSION=$(python3 -c "import playwright; print(playwright.__version__)" 2>/dev/null)
    check_pass "Playwright 已安装: $PW_VERSION"
else
    check_fail "Playwright 未安装"
    echo "   安装命令: pip3 install playwright"
fi
echo ""

# 4. 检查 aiohttp
echo "📋 4. 检查 aiohttp"
echo "----------------------------------------"
python3 -c "import aiohttp" 2>/dev/null
if [ $? -eq 0 ]; then
    check_pass "aiohttp 已安装"
else
    check_fail "aiohttp 未安装"
    echo "   安装命令: pip3 install aiohttp"
fi
echo ""

# 5. 检查 Chromium
echo "📋 5. 检查 Chromium"
echo "----------------------------------------"
if command -v chromium &> /dev/null; then
    check_pass "Chromium 已安装: $(which chromium)"
elif command -v chromium-browser &> /dev/null; then
    check_pass "Chromium 已安装: $(which chromium-browser)"
elif command -v google-chrome &> /dev/null; then
    check_pass "Google Chrome 已安装: $(which google-chrome)"
elif [ -d "$HOME/.cache/ms-playwright" ]; then
    check_pass "Playwright Chromium 已安装"
    ls -la $HOME/.cache/ms-playwright/
else
    check_fail "未找到 Chromium/Chrome"
    echo "   安装方式 1: sudo apt-get install chromium-browser"
    echo "   安装方式 2: playwright install chromium"
fi
echo ""

# 6. 检查脚本目录
echo "📋 6. 检查脚本目录"
echo "----------------------------------------"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "脚本目录: $SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/main.py" ]; then
    check_pass "main.py 存在"
else
    check_fail "main.py 不存在"
fi

if [ -f "$SCRIPT_DIR/scraper.py" ]; then
    check_pass "scraper.py 存在"
else
    check_fail "scraper.py 不存在"
fi

if [ -f "$SCRIPT_DIR/chrome_launcher.py" ]; then
    check_pass "chrome_launcher.py 存在"
else
    check_fail "chrome_launcher.py 不存在"
fi
echo ""

# 7. 检查 Chrome 配置（可选）
echo "📋 7. 检查 Chrome 配置（可选）"
echo "----------------------------------------"
CHROME_PROFILE="$SCRIPT_DIR/data/chrome-profile"
if [ -d "$CHROME_PROFILE" ]; then
    check_pass "Chrome 配置目录存在: $CHROME_PROFILE"
    if [ -f "$CHROME_PROFILE/Default/Network/Cookies" ]; then
        check_pass "Cookies 文件存在"
    else
        check_warn "Cookies 文件不存在（登录状态可能未保存）"
    fi
else
    check_warn "Chrome 配置目录不存在"
    echo "   如需持久化登录状态，请创建: $CHROME_PROFILE"
fi
echo ""

# 8. 检查输出目录
echo "📋 8. 检查输出目录"
echo "----------------------------------------"
OUTPUT_DIR="$SCRIPT_DIR/output"
if [ -d "$OUTPUT_DIR" ]; then
    check_pass "输出目录存在: $OUTPUT_DIR"
else
    check_warn "输出目录不存在，将自动创建"
    mkdir -p "$OUTPUT_DIR"
fi
echo ""

# 总结
echo "=========================================="
echo "检查完成"
echo "=========================================="
echo ""
echo "如果所有检查都通过，可以运行测试:"
echo "  ./test_local.sh"
echo ""
echo "如果缺少依赖，请运行:"
echo "  pip3 install -r requirements.txt"
echo "  playwright install chromium"
echo ""
