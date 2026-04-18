#!/bin/bash
# WSL VPN 网络混合配置方案
# 保持桥接网络用于服务间通信，使用代理访问外部网络

echo "=========================================="
echo "WSL VPN 混合网络配置"
echo "=========================================="
echo ""

# 检测WSL VPN网关
VPN_GATEWAY=$(ip route | grep "198.18.0.2" | awk '{print $3}')
WSL_IP=$(ip addr show eth2 | grep "inet " | awk '{print $2}' | cut -d/ -f1)

echo "🌐 网络信息："
echo "   WSL VPN IP: $WSL_IP"
echo "   VPN 网关: ${VPN_GATEWAY:-198.18.0.2}"
echo ""

# 创建混合网络配置
COMPOSE_FILE="/home/lrp/n8n/docker-compose.wsl-bridge.yml"

cat > "$COMPOSE_FILE" << EOF
# WSL VPN 混合网络配置
# 保持桥接网络用于服务间通信（n8n-redis等）
# 通过HTTP代理让外部流量走WSL VPN

services:
  python-runner:
    # 保持原有网络配置（桥接模式）
    networks:
      - n8n-net
    
    # 添加HTTP代理环境变量，让外部流量走WSL VPN
    environment:
      # 保持原有环境变量
      - SCRIPTS_DIR=/home/node/scripts
      - RESULTS_DIR=/tmp/results
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_PASSWORD=\${REDIS_PASSWORD}
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
      - TZ=Asia/Shanghai
      
      # ⭐ 新增：HTTP代理配置
      # 方法1: 如果WSL上有HTTP代理（如clash）在7890端口
      # - HTTP_PROXY=http://$WSL_IP:7890
      # - HTTPS_PROXY=http://$WSL_IP:7890
      
      # 方法2: 使用WSL的IP作为代理（需要在WSL上安装代理）
      # 先运行: sudo apt-get install -y tinyproxy
      # 然后: sudo service tinyproxy start
      # - HTTP_PROXY=http://$WSL_IP:8888
      # - HTTPS_PROXY=http://$WSL_IP:8888
      
      # 方法3: 使用透明代理（通过iptables，需要配置）
      # 这需要额外的网络配置
      
      # 方法4: 使用WSL网关作为代理（如果VPN提供代理服务）
      # - HTTP_PROXY=http://198.18.0.2:7890
      # - HTTPS_PROXY=http://198.18.0.2:7890
      
      # 方法5: 不设置代理，直接修改容器的默认路由（见下方extra_hosts和配置）
      
    # 添加extra_hosts确保解析正确
    extra_hosts:
      - "host.docker.internal:$WSL_IP"
      - "wsl-vpn-gateway:198.18.0.2"

# 网络配置保持原样
networks:
  n8n-net:
    driver: bridge
EOF

echo "✅ 配置文件已创建: $COMPOSE_FILE"
echo ""

# 方案说明
echo "📋 提供的解决方案："
echo "=========================================="
echo ""
echo "方案1: 在WSL上安装HTTP代理（推荐）"
echo "----------------------------------------"
echo "优点: 不影响现有网络，配置简单"
echo "步骤:"
echo "   1. 在WSL中安装代理:"
echo "      sudo apt-get update"
echo "      sudo apt-get install -y tinyproxy"
echo ""
echo "   2. 修改tinyproxy配置，允许Docker网络访问:"
echo "      sudo sed -i 's/Allow 127.0.0.1/Allow 127.0.0.1\\nAllow 172.0.0.0\\/8/' /etc/tinyproxy/tinyproxy.conf"
echo ""
echo "   3. 启动tinyproxy:"
echo "      sudo service tinyproxy start"
echo ""
echo "   4. 编辑配置文件，启用方法2的代理设置"
echo "      nano $COMPOSE_FILE"
echo "      # 取消注释 HTTP_PROXY=http://$WSL_IP:8888"
echo ""
echo "   5. 重启容器:"
echo "      docker-compose -f docker-compose.yml -f $COMPOSE_FILE restart python-runner"
echo ""
echo ""
echo "方案2: 使用端口映射保持通信（推荐）"
echo "----------------------------------------"
echo "优点: 最简单，不需要额外软件"
echo "方法:"
echo "   1. 修改 docker-compose.yml"
echo "   2. 将redis端口暴露给WSL:"
echo "      redis:"
echo "        ports:"
echo "          - \"6379:6379\""
echo "        command: redis-server --requirepass \${REDIS_PASSWORD} --bind 0.0.0.0"
echo ""
echo "   3. python-runner使用host网络:"
echo "      python-runner:"
echo "        network_mode: \"host\""
echo "        environment:"
echo "          - REDIS_HOST=localhost"
echo ""
echo "   4. 这样python-runner可以:"
echo "      - 通过host网络使用WSL VPN访问Pinterest"
echo "      - 通过localhost:6379访问redis"
echo ""
echo "   5. n8n保持桥接网络不变，继续正常工作"
echo ""
echo ""
echo "方案3: 修改路由表（高级）"
echo "----------------------------------------"
echo "优点: 透明代理，无需应用层配置"
echo "方法:"
echo "   配置Docker容器的默认路由指向WSL VPN网关"
echo "   需要创建自定义Docker网络并使用iptables"
echo "   这比较复杂，建议使用方案1或2"
echo ""

# 询问用户选择
read -p "你希望使用哪个方案？(1/2/3): " CHOICE

case $CHOICE in
  1)
    echo ""
    echo "正在配置方案1..."
    
    # 安装tinyproxy
    if ! command -v tinyproxy &> /dev/null; then
      echo "安装tinyproxy..."
      sudo apt-get update
      sudo apt-get install -y tinyproxy
    fi
    
    # 配置tinyproxy
    sudo sed -i 's/^Allow 127.0.0.1/Allow 127.0.0.1\nAllow 172.0.0.0\/8/' /etc/tinyproxy/tinyproxy.conf 2>/dev/null || true
    sudo sed -i 's/^# Port 8888/Port 8888/' /etc/tinyproxy/tinyproxy.conf
    
    # 启动服务
    sudo service tinyproxy restart || sudo systemctl restart tinyproxy || tinyproxy -d &
    
    # 更新docker-compose配置
    sed -i "s/# 方法2:/方法2:/" "$COMPOSE_FILE"
    sed -i "s/# - HTTP_PROXY=http:\/\/$WSL_IP:8888/- HTTP_PROXY=http:\/\/$WSL_IP:8888/" "$COMPOSE_FILE"
    sed -i "s/# - HTTPS_PROXY=http:\/\/$WSL_IP:8888/- HTTPS_PROXY=http:\/\/$WSL_IP:8888/" "$COMPOSE_FILE"
    
    echo ""
    echo "✅ 配置完成！"
    echo "   Tinyproxy 已安装并配置"
    echo "   代理地址: http://$WSL_IP:8888"
    echo ""
    echo "重启Docker容器："
    echo "   cd /home/lrp/n8n"
    echo "   docker-compose -f docker-compose.yml -f $COMPOSE_FILE restart python-runner"
    ;;
    
  2)
    echo ""
    echo "正在配置方案2..."
    
    # 创建新的配置，修改redis和python-runner
    cat > "/home/lrp/n8n/docker-compose.wsl-host.yml" << EOF
# 方案2: python-runner使用host网络，redis暴露端口

services:
  redis:
    # 暴露端口给host网络访问
    ports:
      - "127.0.0.1:6379:6379"
    # 允许从任何地址连接（不仅是localhost）
    command: redis-server --requirepass \${REDIS_PASSWORD} --bind 0.0.0.0

  python-runner:
    # 使用host网络，共享WSL的网络栈
    network_mode: "host"
    # host模式下端口映射不需要
    ports: []
    environment:
      # 使用localhost访问redis
      - REDIS_HOST=127.0.0.1
      - REDIS_PORT=6379
      - REDIS_PASSWORD=\${REDIS_PASSWORD}
      # 其他配置保持不变
      - SCRIPTS_DIR=/home/node/scripts
      - RESULTS_DIR=/tmp/results
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
      - TZ=Asia/Shanghai
EOF
    
    echo ""
    echo "✅ 配置文件已创建: /home/lrp/n8n/docker-compose.wsl-host.yml"
    echo ""
    echo "使用方法："
    echo "   cd /home/lrp/n8n"
    echo "   # 只重启redis和python-runner"
    echo "   docker-compose up -d redis"
    echo "   docker-compose -f docker-compose.yml -f docker-compose.wsl-host.yml up -d python-runner"
    echo ""
    echo "⚠️  注意:"
    echo "   - python-runner现在使用host网络，可以访问WSL VPN"
    echo "   - n8n保持原配置不变，继续使用桥接网络"
    echo "   - redis同时监听桥接网络和host网络的6379端口"
    ;;
    
  3)
    echo ""
    echo "方案3需要手动配置iptables路由规则"
    echo "请参考网络文档进行配置"
    echo ""
    ;;
    
  *)
    echo "无效选择"
    ;;
esac

echo ""
echo "=========================================="
echo "配置完成！"
echo "=========================================="
echo ""
echo "测试方法："
echo "   docker exec n8n-python-runner python3 -c \"import urllib.request; print(urllib.request.urlopen('https://pinterest.com').getcode())\""
echo ""
