#!/bin/bash
# 使用 Windows Chrome 运行 Pinterest 爬虫
# 前置条件: 先运行 sync_and_start.sh 或在 Windows 上运行 start_chrome_debug.ps1

echo "=========================================="
echo "Pinterest 爬虫 - Windows Chrome 模式"
echo "=========================================="
echo ""

QUERY="${1:-现代简约}"
MAX_PINS="${2:-50}"
MIN_SAVES="${3:-50}"

echo "搜索关键词: $QUERY"
echo "最大数量: $MAX_PINS"
echo "最小 Saves: $MIN_SAVES"
echo ""

# WSL 直连: 端口 9222
CDP_ENDPOINT=""
CDP_OK=false
CDP_FOR_DOCKER=""

if curl -s --noproxy '*' --connect-timeout 3 http://localhost:9222/json/version > /dev/null 2>&1; then
    CDP_ENDPOINT="http://localhost:9222"
    CDP_OK=true
    echo "✅ Chrome 调试端口 (localhost:9222)"
fi

if [ "$CDP_OK" = false ]; then
    if curl -s --noproxy '*' --connect-timeout 3 http://127.0.0.1:9222/json/version > /dev/null 2>&1; then
        CDP_ENDPOINT="http://127.0.0.1:9222"
        CDP_OK=true
        echo "✅ Chrome 调试端口 (127.0.0.1:9222)"
    fi
fi

if [ "$CDP_OK" = false ]; then
    GATEWAY_IP=$(ip route | grep default | awk '{print $3}' | head -1)
    if [ -n "$GATEWAY_IP" ] && curl -s --noproxy '*' --connect-timeout 3 "http://$GATEWAY_IP:9222/json/version" > /dev/null 2>&1; then
        CDP_ENDPOINT="http://$GATEWAY_IP:9222"
        CDP_OK=true
        echo "✅ Chrome 调试端口 ($GATEWAY_IP:9222)"
    fi
fi

# Docker: 端口 9223（TCP 转发器绕过 Chrome 的 Host 头限制）
if curl -s --noproxy '*' --connect-timeout 3 http://localhost:9223/json/version > /dev/null 2>&1; then
    CDP_FOR_DOCKER="http://host.docker.internal:9223"
    echo "✅ Docker 端口转发器就绪 (port 9223)"
fi

if [ "$CDP_OK" = false ] && [ -z "$CDP_FOR_DOCKER" ]; then
    echo "❌ 无法连接到 Chrome 调试端口"
    echo ""
    echo "请先启动 Chrome 调试模式:"
    echo "  ./sync_and_start.sh"
    echo ""
    echo "手动验证（WSL 中需要加 --noproxy）:"
    echo "  curl --noproxy '*' http://localhost:9222/json/version"
    echo ""
    exit 1
fi

# 显示 Chrome 版本
if [ "$CDP_OK" = true ]; then
    VERSION=$(curl -s --noproxy '*' "$CDP_ENDPOINT/json/version" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Browser','unknown'))" 2>/dev/null || echo "unknown")
    echo "  Chrome 版本: $VERSION"
fi
echo ""

# 运行爬虫（从 WSL 直接运行时使用 9222，容器内使用 9223）
if [ -n "$CDP_ENDPOINT" ]; then
    RUN_ENDPOINT="$CDP_ENDPOINT"
elif [ -n "$CDP_FOR_DOCKER" ]; then
    RUN_ENDPOINT="$CDP_FOR_DOCKER"
fi

echo "🚀 启动爬虫..."
echo "   CDP 端点: $RUN_ENDPOINT"
echo ""

RESPONSE=$(curl -s -X POST http://localhost:5000/run/pinterest_scraper_n8n.py \
  -H "Content-Type: application/json" \
  -d "{
    \"args\": [
      \"--query\", \"$QUERY\",
      \"--max-pins\", \"$MAX_PINS\",
      \"--min-saves\", \"$MIN_SAVES\",
      \"--connect\",
      \"--cdp-endpoint\", \"$RUN_ENDPOINT\"
    ]
  }")

if command -v python3 > /dev/null 2>&1; then
    echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'stdout' in data:
        try:
            result = json.loads(data['stdout'])
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except:
            print(data['stdout'])
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
except:
    print(sys.stdin.read() if hasattr(sys.stdin, 'read') else 'Response parsing failed')
"
else
    echo "$RESPONSE"
fi

echo ""
echo "=========================================="
echo "完成！"
echo "=========================================="