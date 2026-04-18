#!/bin/bash
# VPN代理配置脚本
# 用于配置Docker容器通过宿主机VPN访问Pinterest

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="/home/lrp/n8n/docker-compose.yml"

echo "=========================================="
echo "Pinterest Scraper - VPN代理配置"
echo "=========================================="
echo ""

# 检测宿主机VPN代理端口
detect_vpn_proxy() {
    echo "📋 检测宿主机VPN代理..."
    echo "----------------------------------------"
    
    # 常见VPN代理端口
    COMMON_PORTS=("7890" "7891" "7892" "7893" "7895" "1080" "10808" "10809" "8080" "8118" "8888" "8889")
    
    DETECTED_PORT=""
    
    for port in "${COMMON_PORTS[@]}"; do
        if curl -s --connect-timeout 2 -x "http://127.0.0.1:$port" http://httpbin.org/ip > /dev/null 2>&1; then
            echo "✅ 发现HTTP代理端口: $port"
            DETECTED_PORT=$port
            break
        fi
    done
    
    if [ -z "$DETECTED_PORT" ]; then
        echo "⚠️  未自动检测到VPN代理端口"
        echo ""
        echo "请手动输入你的VPN代理端口（常见的如 7890, 10808 等）:"
        read -p "代理端口: " DETECTED_PORT
    fi
    
    echo ""
}

# 方案1: 配置代理环境变量
setup_proxy_env() {
    echo "📋 方案1: 配置代理环境变量"
    echo "----------------------------------------"
    
    PROXY_PORT=${1:-7890}
    PROXY_HOST="192.168.1.1"  # 使用宿主机网关IP
    
    echo "配置代理: http://$PROXY_HOST:$PROXY_PORT"
    echo ""
    
    # 创建docker-compose覆盖文件
    cat > "$SCRIPT_DIR/docker-compose.proxy.yml" << EOF
# VPN代理配置覆盖文件
# 用法: docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d

services:
  python-runner:
    environment:
      - HTTP_PROXY=http://$PROXY_HOST:$PROXY_PORT
      - HTTPS_PROXY=http://$PROXY_HOST:$PROXY_PORT
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis
    
    # 确保可以通过宿主机IP访问代理
    extra_hosts:
      - "host.docker.internal:host-gateway"

  n8n:
    environment:
      - HTTP_PROXY=http://$PROXY_HOST:$PROXY_PORT
      - HTTPS_PROXY=http://$PROXY_HOST:$PROXY_PORT
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis,python-runner
EOF
    
    echo "✅ 已创建代理配置文件: docker-compose.proxy.yml"
    echo ""
    echo "使用方法:"
    echo "  cd /home/lrp/n8n"
    echo "  docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d"
    echo ""
}

# 方案2: 使用Host网络模式
setup_host_network() {
    echo "📋 方案2: 使用Host网络模式"
    echo "----------------------------------------"
    
    cat > "$SCRIPT_DIR/docker-compose.host-network.yml" << EOF
# Host网络模式配置
# 注意: 此模式下容器直接使用宿主机网络，包括VPN

services:
  python-runner:
    network_mode: host
    # 移除端口映射（host模式下不需要）
    ports: []
    environment:
      # Host模式下需要修改服务地址
      - REDIS_HOST=localhost
      - N8N_HOST=localhost
EOF
    
    echo "✅ 已创建Host网络配置文件: docker-compose.host-network.yml"
    echo ""
    echo "⚠️  警告: Host网络模式下:"
    echo "  - 容器直接使用宿主机网络栈"
    echo "  - 可以自动使用宿主机VPN"
    echo "  - 但会失去Docker网络隔离"
    echo "  - 端口映射将失效"
    echo ""
}

# 方案3: 直接修改docker-compose.yml
modify_compose_file() {
    echo "📋 方案3: 直接修改docker-compose.yml"
    echo "----------------------------------------"
    
    PROXY_PORT=${1:-7890}
    PROXY_HOST="192.168.1.1"
    
    echo "将修改: $COMPOSE_FILE"
    echo "代理配置: http://$PROXY_HOST:$PROXY_PORT"
    echo ""
    
    read -p "确认修改? (y/n): " CONFIRM
    
    if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
        # 备份原文件
        cp "$COMPOSE_FILE" "$COMPOSE_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        
        # 修改python-runner服务的环境变量
        sed -i "s/# HTTP_PROXY: http:\/\/192.168.0.37:7890/HTTP_PROXY: http:\/\/$PROXY_HOST:$PROXY_PORT/" "$COMPOSE_FILE"
        sed -i "s/#HTTPS_PROXY: http:\/\/192.168.0.37:7890/HTTPS_PROXY: http:\/\/$PROXY_HOST:$PROXY_PORT/" "$COMPOSE_FILE"
        sed -i "s/#NO_PROXY:/NO_PROXY:/" "$COMPOSE_FILE"
        
        echo "✅ 已修改docker-compose.yml"
        echo "  原文件已备份"
        echo ""
        echo "请重启容器生效:"
        echo "  cd /home/lrp/n8n"
        echo "  docker-compose restart python-runner"
    else
        echo "已取消修改"
    fi
    echo ""
}

# 测试代理连接
test_proxy() {
    echo "📋 测试代理连接"
    echo "----------------------------------------"
    
    PROXY_PORT=${1:-7890}
    PROXY_HOST="192.168.1.1"
    
    echo "测试通过代理访问Pinterest..."
    
    # 宿主机测试
    echo ""
    echo "1. 宿主机直接访问:"
    if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 https://pinterest.com > /dev/null 2>&1; then
        echo "   ✅ 宿主机可以访问 Pinterest"
    else
        echo "   ❌ 宿主机无法访问 Pinterest（VPN可能未连接）"
    fi
    
    # 容器测试（重启后）
    echo ""
    echo "2. 容器访问（配置后需要重启容器）:"
    echo "   运行以下命令测试:"
    echo "   docker exec n8n-python-runner curl -s -o /dev/null -w '%{http_code}' https://pinterest.com"
    echo ""
}

# 主菜单
show_menu() {
    echo "=========================================="
    echo "请选择VPN配置方案:"
    echo "=========================================="
    echo ""
    echo "1. 配置代理环境变量（推荐）"
    echo "   - 创建docker-compose.proxy.yml覆盖文件"
    echo "   - 对原配置无影响"
    echo "   - 可随时切换"
    echo ""
    echo "2. 使用Host网络模式"
    echo "   - 容器直接使用宿主机网络"
    echo "   - 自动使用VPN"
    echo "   - 但失去网络隔离"
    echo ""
    echo "3. 直接修改docker-compose.yml"
    echo "   - 修改原配置文件"
    echo "   - 自动备份原文件"
    echo ""
    echo "4. 仅测试代理连接"
    echo ""
    echo "0. 退出"
    echo ""
}

# 主程序
main() {
    # 检测代理端口
    detect_vpn_proxy
    
    while true; do
        show_menu
        read -p "请选择 [0-4]: " CHOICE
        
        case $CHOICE in
            1)
                setup_proxy_env "$DETECTED_PORT"
                test_proxy "$DETECTED_PORT"
                break
                ;;
            2)
                setup_host_network
                echo "使用方式:"
                echo "  docker-compose -f docker-compose.yml -f docker-compose.host-network.yml up -d"
                break
                ;;
            3)
                modify_compose_file "$DETECTED_PORT"
                test_proxy "$DETECTED_PORT"
                break
                ;;
            4)
                test_proxy "$DETECTED_PORT"
                ;;
            0)
                echo "退出"
                exit 0
                ;;
            *)
                echo "无效选择"
                ;;
        esac
    done
    
    echo ""
    echo "=========================================="
    echo "配置完成！"
    echo "=========================================="
    echo ""
    echo "下一步:"
    echo "1. 重启Docker容器:"
    echo "   cd /home/lrp/n8n"
    echo "   docker-compose restart python-runner"
    echo ""
    echo "2. 测试Pinterest连接:"
    echo "   docker exec n8n-python-runner curl -s -o /dev/null -w '%{http_code}' https://pinterest.com"
    echo ""
    echo "3. 运行Pinterest爬虫:"
    echo "   ./run_in_docker.sh '现代简约' 50"
}

# 如果直接传参则自动执行
if [ $# -ge 1 ]; then
    case $1 in
        env|1)
            setup_proxy_env "${2:-7890}"
            ;;
        host|2)
            setup_host_network
            ;;
        modify|3)
            modify_compose_file "${2:-7890}"
            ;;
        test|4)
            test_proxy "${2:-7890}"
            ;;
        *)
            main
            ;;
    esac
else
    main
fi
