#!/bin/bash
# WSL + Windows VPN 一键配置脚本
# 自动检测网络环境并配置Docker代理

set -e

echo "=========================================="
echo "WSL + Windows VPN 配置助手"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# 检测 WSL 环境
detect_wsl() {
    info "检测 WSL 环境..."
    
    if grep -q "microsoft" /proc/version 2>/dev/null || grep -q "WSL" /proc/version 2>/dev/null; then
        success "检测到 WSL 环境"
        IS_WSL=true
    else
        warn "未检测到 WSL 环境，但脚本仍可运行"
        IS_WSL=false
    fi
    
    echo ""
}

# 显示网络信息
show_network_info() {
    info "当前网络配置："
    echo "----------------------------------------"
    
    echo "默认网关："
    ip route | grep default
    
    echo ""
    echo "DNS 服务器："
    cat /etc/resolv.conf | grep nameserver
    
    echo ""
    echo "IP 地址："
    ip addr show | grep "inet " | grep -v "127.0.0.1"
    
    echo ""
}

# 检测 Windows 主机 IP
detect_windows_ip() {
    info "检测 Windows 主机 IP..."
    
    # 方法1: 通过路由（最可靠）
    WINDOWS_IP=$(ip route | grep "default via" | grep "192.168" | head -1 | awk '{print $3}')
    
    # 方法2: 通过 DNS 配置
    if [ -z "$WINDOWS_IP" ]; then
        WINDOWS_IP=$(cat /etc/resolv.conf | grep nameserver | head -1 | awk '{print $2}')
    fi
    
    # 方法3: 通过 eth0
    if [ -z "$WINDOWS_IP" ]; then
        WINDOWS_IP=$(ip route | grep "default" | head -1 | awk '{print $3}')
    fi
    
    if [ -n "$WINDOWS_IP" ]; then
        success "Windows 主机 IP: $WINDOWS_IP"
    else
        error "无法检测到 Windows 主机 IP"
        read -p "请手动输入 Windows 主机 IP: " WINDOWS_IP
    fi
    
    echo ""
}

# 检测 VPN 代理端口
detect_vpn_port() {
    info "检测 VPN 代理端口..."
    
    # 常见 VPN 端口
    COMMON_PORTS=("7890" "7891" "10808" "10809" "1080" "8080" "8118" "8888" "8889")
    FOUND_PORT=""
    
    for port in "${COMMON_PORTS[@]}"; do
        info "测试端口 $port..."
        
        # 测试 Windows 主机的代理
        if timeout 3 curl -s -x "http://$WINDOWS_IP:$port" http://httpbin.org/ip > /dev/null 2>&1; then
            success "发现可用代理端口: $port"
            FOUND_PORT=$port
            break
        fi
        
        # 测试本地代理（如果VPN在WSL中运行）
        if timeout 3 curl -s -x "http://127.0.0.1:$port" http://httpbin.org/ip > /dev/null 2>&1; then
            success "发现本地代理端口: $port"
            FOUND_PORT=$port
            WINDOWS_IP="127.0.0.1"
            break
        fi
    done
    
    if [ -z "$FOUND_PORT" ]; then
        warn "未自动检测到代理端口"
        echo ""
        echo "常见VPN客户端默认端口："
        echo "  Clash: 7890 (HTTP) / 7891 (SOCKS5)"
        echo "  v2rayN: 10808"
        echo "  Shadowsocks: 1080"
        echo ""
        read -p "请输入代理端口 (默认7890): " FOUND_PORT
        FOUND_PORT=${FOUND_PORT:-7890}
    fi
    
    echo ""
}

# 测试 Pinterest 连接
test_pinterest() {
    info "测试 Pinterest 连接..."
    
    # 测试宿主机（WSL）
    info "1. 测试 WSL 直接连接..."
    if timeout 5 curl -s -o /dev/null -w "%{http_code}" https://pinterest.com > /dev/null 2>&1; then
        success "WSL 可以直接访问 Pinterest"
        WSL_CAN_ACCESS=true
    else
        warn "WSL 无法直接访问 Pinterest（需要VPN）"
        WSL_CAN_ACCESS=false
    fi
    
    # 测试通过代理
    info "2. 测试通过代理连接..."
    if timeout 5 curl -s -x "http://$WINDOWS_IP:$FOUND_PORT" -o /dev/null -w "%{http_code}" https://pinterest.com > /dev/null 2>&1; then
        success "通过代理可以访问 Pinterest"
        PROXY_WORKS=true
    else
        error "通过代理无法访问 Pinterest"
        PROXY_WORKS=false
    fi
    
    echo ""
}

# 创建 Docker 代理配置
create_docker_config() {
    info "创建 Docker 代理配置..."
    
    COMPOSE_FILE="/home/lrp/n8n/docker-compose.proxy.yml"
    
    cat > "$COMPOSE_FILE" << EOF
# WSL + Windows VPN 代理配置
# 自动生成时间: $(date)

services:
  python-runner:
    environment:
      # Windows VPN 代理配置
      - HTTP_PROXY=http://$WINDOWS_IP:$FOUND_PORT
      - HTTPS_PROXY=http://$WINDOWS_IP:$FOUND_PORT
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis
      # 小写形式（兼容某些工具）
      - http_proxy=http://$WINDOWS_IP:$FOUND_PORT
      - https_proxy=http://$WINDOWS_IP:$FOUND_PORT
      - no_proxy=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis

  n8n:
    environment:
      - HTTP_PROXY=http://$WINDOWS_IP:$FOUND_PORT
      - HTTPS_PROXY=http://$WINDOWS_IP:$FOUND_PORT
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis,python-runner
      - http_proxy=http://$WINDOWS_IP:$FOUND_PORT
      - https_proxy=http://$WINDOWS_IP:$FOUND_PORT
      - no_proxy=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis,python-runner

    # 确保可以访问 Windows 主机
    extra_hosts:
      - "host.docker.internal:host-gateway"
EOF
    
    success "已创建配置文件: $COMPOSE_FILE"
    echo ""
}

# 应用配置
apply_config() {
    info "应用 Docker 配置..."
    
    cd /home/lrp/n8n
    
    # 检查容器是否运行
    if docker ps | grep -q n8n-python-runner; then
        warn "正在重启 python-runner 容器..."
        docker-compose -f docker-compose.yml -f docker-compose.proxy.yml restart python-runner
    else
        warn "容器未运行，正在启动..."
        docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d python-runner
    fi
    
    success "配置已应用"
    echo ""
    
    # 等待容器启动
    info "等待容器启动..."
    sleep 5
    
    # 测试容器内连接
    info "测试容器内 Pinterest 连接..."
    docker exec n8n-python-runner python3 -c "
import urllib.request
import ssl
import os

print('环境变量:')
print('HTTP_PROXY:', os.environ.get('HTTP_PROXY', '未设置'))
print('HTTPS_PROXY:', os.environ.get('HTTPS_PROXY', '未设置'))
print('')

ssl._create_default_https_context = ssl._create_unverified_context
try:
    response = urllib.request.urlopen('https://pinterest.com', timeout=10)
    print(f'✅ 连接成功! 状态码: {response.getcode()}')
except Exception as e:
    print(f'❌ 连接失败: {e}')
"
    
    echo ""
}

# 显示使用说明
show_usage() {
    echo "=========================================="
    echo "配置完成！"
    echo "=========================================="
    echo ""
    echo "📋 配置信息："
    echo "  Windows IP: $WINDOWS_IP"
    echo "  代理端口: $FOUND_PORT"
    echo "  配置文件: /home/lrp/n8n/docker-compose.proxy.yml"
    echo ""
    echo "🚀 使用方法："
    echo ""
    echo "1. 启动/重启服务："
    echo "   cd /home/lrp/n8n"
    echo "   docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d"
    echo ""
    echo "2. 运行 Pinterest Scraper："
    echo "   cd /home/lrp/n8n/docker/scripts/pinterest-scraper"
    echo "   ./run_in_docker.sh '现代简约' 50"
    echo ""
    echo "3. 仅重启 python-runner："
    echo "   docker-compose -f docker-compose.yml -f docker-compose.proxy.yml restart python-runner"
    echo ""
    echo "📝 提示："
    echo "  - 确保 Windows 上的 VPN 客户端已开启"
    echo "  - 确保 VPN 客户端允许局域网连接 (Allow LAN)"
    echo "  - 如果连接失败，检查 Windows 防火墙设置"
    echo ""
    echo "🔧 故障排查："
    echo "  1. 检查 Windows VPN 是否允许 LAN："
    echo "     curl -x http://$WINDOWS_IP:$FOUND_PORT http://httpbin.org/ip"
    echo ""
    echo "  2. 检查容器代理环境变量："
    echo "     docker exec n8n-python-runner env | grep -i proxy"
    echo ""
    echo "  3. 手动测试 Pinterest："
    echo "     docker exec n8n-python-runner python3 -c \"import urllib.request; print(urllib.request.urlopen('https://pinterest.com').getcode())\""
    echo ""
}

# 检查是否需要 WSL 镜像模式
suggest_mirror_mode() {
    if [ "$IS_WSL" = true ]; then
        echo ""
        info "💡 提示：如果你使用 Windows 11，可以启用 WSL 镜像模式"
        echo "   这样可以让 WSL2 直接使用 Windows 的网络连接"
        echo ""
        echo "   步骤："
        echo "   1. 在 Windows PowerShell (管理员) 中运行："
        echo "      notepad \$env:USERPROFILE\\.wslconfig"
        echo ""
        echo "   2. 添加以下内容："
        echo "      [wsl2]"
        echo "      networkingMode=mirrored"
        echo "      autoProxy=true"
        echo ""
        echo "   3. 重启 WSL："
        echo "      wsl --shutdown"
        echo ""
    fi
}

# 主程序
main() {
    detect_wsl
    show_network_info
    detect_windows_ip
    detect_vpn_port
    test_pinterest
    
    if [ "$PROXY_WORKS" = true ]; then
        create_docker_config
        apply_config
        show_usage
        suggest_mirror_mode
    else
        error "代理测试失败，无法继续配置"
        echo ""
        echo "可能的原因："
        echo "  1. Windows 上的 VPN 客户端未开启"
        echo "  2. VPN 客户端未开启'允许局域网连接'"
        echo "  3. Windows 防火墙阻止了连接"
        echo "  4. 代理端口不正确"
        echo ""
        echo "请检查以上问题后重试"
    fi
}

# 运行主程序
main
