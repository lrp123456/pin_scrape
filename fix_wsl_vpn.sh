#!/bin/bash
# WSL VPN Docker 网络配置修复
# 问题：WSL有VPN(eth2)，但Docker容器使用独立网络
# 解决：让Docker容器使用host网络模式，共享WSL的VPN连接

echo "=========================================="
echo "WSL VPN Docker 网络修复"
echo "=========================================="
echo ""

# 检测网络环境
echo "📊 网络环境检测："
echo "----------------------------------------"

# 检查VPN接口
echo "VPN接口 (eth2):"
ip addr show eth2 2>/dev/null | grep "inet " || echo "  eth2 未找到"

echo ""
echo "默认路由："
ip route | grep default

echo ""
echo "Docker网络："
ip route | grep docker

echo ""

# 检测WSL是否通过VPN上网
if ping -c 1 -W 3 google.com > /dev/null 2>&1; then
    echo "✅ WSL可以访问互联网"
    
    # 检查是否走VPN
    GATEWAY=$(ip route | grep default | head -1 | awk '{print $3}')
    if [[ "$GATEWAY" == "198.18."* ]]; then
        echo "✅ WSL正在使用VPN (网关: $GATEWAY)"
        USE_HOST_NETWORK=true
    else
        echo "⚠️  WSL可能没有使用VPN (网关: $GATEWAY)"
        USE_HOST_NETWORK=false
    fi
else
    echo "❌ WSL无法访问互联网"
    exit 1
fi

echo ""

# 创建Docker Host网络配置文件
COMPOSE_FILE="/home/lrp/n8n/docker-compose.wsl-vpn.yml"

echo "📝 创建Docker配置..."
echo "----------------------------------------"

cat > "$COMPOSE_FILE" << 'EOF'
# WSL VPN Host网络模式配置
# 让Docker容器共享WSL的网络栈，包括VPN连接

services:
  python-runner:
    # 使用host网络模式，共享WSL的网络栈
    network_mode: "host"
    
    # host模式下端口映射不需要，但保留以防切换回bridge模式
    ports: []
    
    # 需要调整环境变量，使用localhost访问其他服务
    environment:
      # Redis连接（host模式下使用localhost）
      - REDIS_HOST=localhost
      - REDIS_PORT=6379
      # 其他配置保持不变
      - SCRIPTS_DIR=/home/node/scripts
      - RESULTS_DIR=/tmp/results
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
      - TZ=Asia/Shanghai

  # 注意：其他服务（n8n, redis, postgres）保持在bridge网络
  # 通过端口映射与host模式的python-runner通信
EOF

echo "✅ 配置文件已创建: $COMPOSE_FILE"
echo ""

# 创建混合网络配置（推荐方案）
COMPOSE_FILE2="/home/lrp/n8n/docker-compose.wsl-mixed.yml"

cat > "$COMPOSE_FILE2" << 'EOF'
# WSL VPN 混合网络配置
# python-runner使用host网络共享VPN
# 其他服务使用bridge网络

services:
  python-runner:
    network_mode: "host"
    ports: []
    environment:
      - REDIS_HOST=localhost
      - REDIS_HOST=127.0.0.1
      - REDIS_PORT=6379
      - SCRIPTS_DIR=/home/node/scripts
      - RESULTS_DIR=/tmp/results
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
      - TZ=Asia/Shanghai
      # 如果Redis需要密码
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    volumes:
      - ./data/chrome-profile:/home/node/.chrome-profile
      - ./docker/scripts:/home/node/scripts
      - ./simhei.ttf:/fonts/simhei.ttf:ro
      - ./data/music:/assets/bgm
      - ./data/videos_result:/tmp/videos_result
      - ./data/videos_class:/tmp/video_class
      - ./data/videos_split:/tmp/videos_split
      - ./data/videos:/home/node/.n8n-files/videos
      - ./data/files:/home/node/.n8n-files/files
      - ./data/outputs:/tmp/outputs
      - ./data/results:/tmp/results
      - ./docker/model:/home/node/.n8n-files/model
      - /usr/lib/wsl/lib:/usr/lib/wsl/lib:ro

  # Redis需要在localhost:6379可访问
  redis:
    ports:
      - "6379:6379"
    # 允许从host网络访问
    command: redis-server --requirepass ${REDIS_PASSWORD} --bind 0.0.0.0
EOF

echo "✅ 混合网络配置已创建: $COMPOSE_FILE2"
echo ""

# 使用说明
echo "🚀 使用方法："
echo "----------------------------------------"
echo ""
echo "方案1: 仅python-runner使用host网络（推荐）"
echo "   cd /home/lrp/n8n"
echo "   # 先启动redis（bridge网络）"
echo "   docker-compose up -d redis"
echo "   # 再启动python-runner（host网络）"
echo "   docker-compose -f docker-compose.yml -f docker-compose.wsl-vpn.yml up -d python-runner"
echo ""
echo "方案2: 使用混合配置（更简单）"
echo "   cd /home/lrp/n8n"
echo "   docker-compose -f docker-compose.yml -f docker-compose.wsl-mixed.yml up -d"
echo ""
echo "⚠️  注意事项："
echo "   - Host网络模式下，容器直接使用WSL的网络栈"
echo "   - 这意味着容器会自动使用WSL的VPN连接（eth2）"
echo "   - 端口映射不再生效，服务直接监听WSL的端口"
echo "   - Redis需要在localhost:6379可访问"
echo ""
echo "🧪 测试方法："
echo "   # 进入容器"
echo "   docker exec -it n8n-python-runner bash"
echo "   # 测试网络"
echo "   python3 -c \"import urllib.request; print(urllib.request.urlopen('https://pinterest.com').getcode())\""
echo ""
