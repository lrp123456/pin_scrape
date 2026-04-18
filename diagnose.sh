#!/bin/bash
# Pinterest Scraper - 诊断脚本

echo "=========================================="
echo "Pinterest Scraper - 系统诊断"
echo "=========================================="
echo ""

# 1. 检查容器状态
echo "📋 1. 检查容器状态"
echo "----------------------------------------"
if docker ps | grep -q n8n-python-runner; then
  echo "✅ python-runner 容器正在运行"
else
  echo "❌ python-runner 容器未运行"
  echo "请先启动容器: docker-compose up -d python-runner"
  exit 1
fi
echo ""

# 2. 检查脚本路径
echo "📋 2. 检查脚本路径"
echo "----------------------------------------"
if docker exec n8n-python-runner test -f /home/node/scripts/pinterest-scraper/main.py; then
  echo "✅ 主脚本存在"
  docker exec n8n-python-runner ls -lh /home/node/scripts/pinterest-scraper/main.py
else
  echo "❌ 主脚本不存在"
  echo "请检查 volume 映射是否正确"
  exit 1
fi
echo ""

# 3. 检查 Chrome 配置
echo "📋 3. 检查 Chrome 配置"
echo "----------------------------------------"
if docker exec n8n-python-runner test -f /home/node/.chrome-profile/Default/Network/Cookies; then
  SIZE=$(docker exec n8n-python-runner stat -c%s /home/node/.chrome-profile/Default/Network/Cookies 2>/dev/null || echo "0")
  echo "✅ Cookies 文件存在 (${SIZE} bytes)"
else
  echo "❌ Cookies 文件不存在"
  echo "请按照 CHROME_PROFILE_SETUP.md 重新配置"
  exit 1
fi
echo ""

# 4. 检查 Chromium 安装
echo "📋 4. 检查 Chromium 安装"
echo "----------------------------------------"
if docker exec n8n-python-runner which chromium >/dev/null 2>&1; then
  echo "✅ Chromium 已安装"
  docker exec n8n-python-runner which chromium
elif docker exec n8n-python-runner which google-chrome >/dev/null 2>&1; then
  echo "✅ Google Chrome 已安装"
  docker exec n8n-python-runner which google-chrome
else
  echo "❌ 未找到 Chrome/Chromium"
  echo "需要重新构建镜像: docker-compose build python-runner"
  exit 1
fi
echo ""

# 5. 检查网络连接
echo "📋 5. 检查网络连接"
echo "----------------------------------------"
echo "测试访问 Pinterest..."
if docker exec n8n-python-runner curl -s -o /dev/null -w "%{http_code}" https://pinterest.com | grep -q "200\|301\|302"; then
  echo "✅ 可以访问 Pinterest"
else
  echo "⚠️  无法访问 Pinterest 或被重定向"
  echo "可能需要检查网络或代理设置"
fi
echo ""

# 6. 检查输出目录
echo "📋 6. 检查输出目录"
echo "----------------------------------------"
docker exec n8n-python-runner mkdir -p /tmp/results/pinterest 2>/dev/null
if docker exec n8n-python-runner test -d /tmp/results/pinterest; then
  echo "✅ 输出目录已创建"
  docker exec n8n-python-runner ls -lh /tmp/results/
else
  echo "❌ 无法创建输出目录"
fi
echo ""

# 7. 检查依赖包
echo "📋 7. 检查 Python 依赖"
echo "----------------------------------------"
docker exec n8n-python-runner python -c "import playwright; import requests; print('✅ 核心依赖已安装')" 2>/dev/null || {
  echo "❌ 缺少依赖包"
  echo "需要重新构建镜像"
  exit 1
}
echo ""

echo "=========================================="
echo "✅ 基础诊断完成"
echo "=========================================="
echo ""
echo "如果所有检查都通过，请运行："
echo "  docker exec -it n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \\"
echo "    -q 'test' -n 3 --connect --auto-launch \\"
echo "    --chrome-profile /home/node/.chrome-profile --debug"
echo ""
echo "如果遇到错误，请提供完整的错误信息。"
