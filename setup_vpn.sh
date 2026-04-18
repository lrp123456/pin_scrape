#!/bin/bash
# Pinterest VPN代理配置助手
# 一键配置Docker容器使用宿主机VPN

echo "=========================================="
echo "Pinterest Scraper - VPN代理配置"
echo "=========================================="
echo ""

# 检测常见VPN代理端口
echo "🔍 检测VPN代理端口..."
PORTS=("7890" "7891" "10808" "10809" "1080" "8080")
FOUND_PORT=""

for port in "${PORTS[@]}"; do
    if curl -s --connect-timeout 2 -x "http://127.0.0.1:$port" http://httpbin.org/ip > /dev/null 2>&1; then
        echo "  ✅ 发现代理端口: $port"
        FOUND_PORT=$port
        break
    fi
done

if [ -z "$FOUND_PORT" ]; then
    echo "  ⚠️  未自动检测到代理端口"
    echo ""
    read -p "请输入你的VPN代理端口 (默认7890): " FOUND_PORT
    FOUND_PORT=${FOUND_PORT:-7890}
fi

echo ""
echo "📝 代理端口: $FOUND_PORT"
echo ""

# 检测宿主机IP
HOST_IP=$(ip route | grep default | awk '{print $3}' | head -1)
echo "🌐 宿主机网关IP: $HOST_IP"
echo ""

# 创建代理配置文件
cat > /home/lrp/n8n/docker-compose.proxy.yml << EOF
# VPN代理配置 - 自动生成
# 生成时间: $(date)

services:
  python-runner:
    environment:
      - HTTP_PROXY=http://$HOST_IP:$FOUND_PORT
      - HTTPS_PROXY=http://$HOST_IP:$FOUND_PORT
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis
      - http_proxy=http://$HOST_IP:$FOUND_PORT
      - https_proxy=http://$HOST_IP:$FOUND_PORT
      - no_proxy=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis

  n8n:
    environment:
      - HTTP_PROXY=http://$HOST_IP:$FOUND_PORT
      - HTTPS_PROXY=http://$HOST_IP:$FOUND_PORT
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis,python-runner
      - http_proxy=http://$HOST_IP:$FOUND_PORT
      - https_proxy=http://$HOST_IP:$FOUND_PORT
      - no_proxy=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis,python-runner
EOF

echo "✅ 已创建配置文件: /home/lrp/n8n/docker-compose.proxy.yml"
echo ""

# 询问是否立即应用
read -p "是否立即应用配置并重启容器? (y/n): " APPLY

if [ "$APPLY" = "y" ] || [ "$APPLY" = "Y" ]; then
    echo ""
    echo "🔄 重启容器..."
    cd /home/lrp/n8n
    docker-compose -f docker-compose.yml -f docker-compose.proxy.yml restart python-runner
    
    echo ""
    echo "⏳ 等待容器启动..."
    sleep 5
    
    echo ""
    echo "🧪 测试网络连接..."
    docker exec n8n-python-runner python3 -c "
import urllib.request
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
try:
    response = urllib.request.urlopen('https://pinterest.com', timeout=10)
    print(f'✅ 连接成功! 状态码: {response.getcode()}')
except Exception as e:
    print(f'❌ 连接失败: {e}')
"
else
    echo ""
    echo "💡 手动应用配置:"
    echo "   cd /home/lrp/n8n"
    echo "   docker-compose -f docker-compose.yml -f docker-compose.proxy.yml restart python-runner"
fi

echo ""
echo "=========================================="
echo "配置完成!"
echo "=========================================="
echo ""
echo "使用说明:"
echo "1. 启动/重启服务:"
echo "   docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d"
echo ""
echo "2. 仅重启python-runner:"
echo "   docker-compose -f docker-compose.yml -f docker-compose.proxy.yml restart python-runner"
echo ""
echo "3. 运行Pinterest爬虫:"
echo "   ./run_in_docker.sh '现代简约' 50"
echo ""
