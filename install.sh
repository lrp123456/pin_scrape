#!/bin/bash
# Pinterest Scraper - 一键安装脚本（宿主机）
# 用法: ./install.sh

set -e

echo "=========================================="
echo "Pinterest Scraper - 宿主机安装"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 检查 Python
echo "📋 1. 检查 Python"
echo "----------------------------------------"
if command -v python3 &> /dev/null; then
    echo "✅ Python3 已安装: $(python3 --version)"
else
    echo "❌ Python3 未安装"
    echo "请安装 Python 3.8 或更高版本"
    exit 1
fi
echo ""

# 2. 安装依赖
echo "📋 2. 安装 Python 依赖"
echo "----------------------------------------"
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt
    echo "✅ 依赖安装完成"
else
    echo "⚠️  未找到 requirements.txt"
    echo "手动安装: pip3 install playwright aiohttp"
fi
echo ""

# 3. 安装 Playwright 浏览器
echo "📋 3. 安装 Playwright Chromium"
echo "----------------------------------------"
echo "这可能需要几分钟时间..."
playwright install chromium
echo "✅ Chromium 安装完成"
echo ""

# 4. 创建目录
echo "📋 4. 创建必要目录"
echo "----------------------------------------"
mkdir -p "$SCRIPT_DIR/output"
mkdir -p "$SCRIPT_DIR/data/chrome-profile"
echo "✅ 目录创建完成"
echo ""

# 5. 设置脚本权限
echo "📋 5. 设置脚本权限"
echo "----------------------------------------"
chmod +x *.sh 2>/dev/null || true
echo "✅ 权限设置完成"
echo ""

# 6. 运行环境检查
echo "📋 6. 运行环境检查"
echo "----------------------------------------"
./check_env.sh

echo ""
echo "=========================================="
echo "✅ 安装完成！"
echo "=========================================="
echo ""
echo "接下来可以运行测试:"
echo "  ./test_local.sh         # 快速测试"
echo "  ./test_docker.sh        # Docker 测试"
echo "  ./run_local.sh          # 完整运行"
echo ""
