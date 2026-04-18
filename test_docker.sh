#!/bin/bash
# Pinterest Scraper - 宿主机 Docker 测试脚本
# 用法: ./test_docker.sh [关键词] [数量]

set -e

# 参数
QUERY="${1:-现代简约}"
MAX_PINS="${2:-5}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "Pinterest Scraper - Docker 测试"
echo "=========================================="
echo ""
echo "搜索关键词: $QUERY"
echo "爬取数量: $MAX_PINS"
echo ""

# 检查 Docker
echo "📋 1. 检查 Docker"
echo "----------------------------------------"
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    exit 1
fi

if ! docker ps &> /dev/null; then
    echo "❌ Docker 服务未运行"
    exit 1
fi

echo "✅ Docker 可用"
echo ""

# 检查容器
echo "📋 2. 检查容器"
echo "----------------------------------------"
if docker ps | grep -q n8n-python-runner; then
    echo "✅ n8n-python-runner 容器正在运行"
else
    echo "⚠️  n8n-python-runner 容器未运行"
    echo ""
    echo "尝试启动容器..."
    cd /home/lrp/n8n && docker-compose up -d python-runner || {
        echo "❌ 启动容器失败"
        exit 1
    }
    sleep 5
    echo "✅ 容器已启动"
fi
echo ""

# 运行测试
echo "📋 3. 运行测试"
echo "----------------------------------------"
echo "命令: docker exec n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py"
echo ""

docker exec n8n-python-runner python /home/node/scripts/pinterest-scraper/main.py \
  -q "$QUERY" \
  -n "$MAX_PINS" \
  --connect \
  --auto-launch \
  --chrome-profile /home/node/.chrome-profile \
  -o /tmp/results/pinterest_test_$(date +%Y%m%d_%H%M%S)

RESULT=$?

echo ""
echo "=========================================="
if [ $RESULT -eq 0 ]; then
    echo "✅ Docker 测试成功！"
    echo ""
    echo "查看容器内结果:"
    docker exec n8n-python-runner ls -lh /tmp/results/
else
    echo "❌ Docker 测试失败"
fi
echo "=========================================="
