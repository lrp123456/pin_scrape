#!/bin/bash
# 在 Docker 容器中启动 VNC + 可视化 Chrome
# 用于手动登录 Pinterest

echo "=========================================="
echo "启动 VNC + 可视化 Chrome"
echo "=========================================="
echo ""

# 检查是否在容器内
if [ -f /.dockerenv ]; then
    echo "✅ 已在容器内"
    INSIDE_CONTAINER=true
else
    echo "🔄 需要在容器外运行，将自动进入容器"
    INSIDE_CONTAINER=false
fi

start_vnc_chrome() {
    echo "📦 安装 VNC 和桌面环境..."
    
    # 安装必要的包
    apt-get update -qq
    apt-get install -y -qq \
        tigervnc-standalone-server \
        tigervnc-viewer \
        xfce4 \
        xfce4-terminal \
        dbus-x11 \
        xfonts-base \
        xfonts-75dpi \
        xfonts-100dpi \
        fonts-wqy-zenhei \
        > /dev/null 2>&1
    
    echo "✅ 安装完成"
    echo ""
    
    # 设置 VNC 密码
    echo "🔐 设置 VNC 密码..."
    mkdir -p ~/.vnc
    echo "password" | vncpasswd -f > ~/.vnc/passwd
    chmod 600 ~/.vnc/passwd
    echo "   VNC 密码: password"
    echo ""
    
    # 创建 xstartup 脚本
    cat > ~/.vnc/xstartup << 'EOF'
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
exec startxfce4
EOF
    chmod +x ~/.vnc/xstartup
    
    # 启动 VNC 服务器
    echo "🖥️  启动 VNC 服务器..."
    vncserver :1 -geometry 1920x1080 -depth 24 -localhost no
    
    echo ""
    echo "✅ VNC 服务器已启动"
    echo "   端口: 5901"
    echo ""
    
    # 在后台启动 Chrome
    echo "🌐 启动 Chrome..."
    DISPLAY=:1 /usr/local/share/chromium/chrome-linux64/chrome \
        --user-data-dir=/home/node/.chrome-profile \
        --no-sandbox \
        --disable-setuid-sandbox \
        --disable-dev-shm-usage \
        --start-maximized \
        https://www.pinterest.com &
    
    CHROME_PID=$!
    echo "   Chrome PID: $CHROME_PID"
    echo ""
    
    echo "=========================================="
    echo "✅ 服务已启动！"
    echo "=========================================="
    echo ""
    echo "📱 连接信息："
    echo "   VNC 地址: localhost:5901"
    echo "   VNC 密码: password"
    echo ""
    echo "🔧 操作步骤："
    echo "   1. 使用 VNC 客户端连接到 localhost:5901"
    echo "      推荐客户端: RealVNC Viewer / TigerVNC Viewer"
    echo "   2. 在 Chrome 中登录 Pinterest"
    echo "   3. 登录完成后关闭 Chrome 窗口"
    echo "   4. 按 Ctrl+C 停止此脚本"
    echo ""
    echo "💡 提示："
    echo "   - 首次连接可能需要 10-20 秒加载桌面"
    echo "   - 如果看到黑屏，等待几秒钟"
    echo "   - 确保在 Pinterest 上完成登录并看到主页"
    echo ""
    
    # 等待用户中断
    wait $CHROME_PID
}

# 如果在容器外，进入容器
if [ "$INSIDE_CONTAINER" = false ]; then
    echo "🔄 正在进入 Docker 容器..."
    docker exec -it n8n-python-runner bash -c "
        cd /home/node/scripts/pinterest-scraper
        ./start_vnc_chrome.sh inside
    "
else
    # 在容器内直接运行
    start_vnc_chrome
fi
