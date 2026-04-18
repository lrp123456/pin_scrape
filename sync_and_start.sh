#!/bin/bash
# 一键同步配置并启动 Chrome 调试模式
# 用法: ./sync_and_start.sh [Windows用户名]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "  一键同步 + 启动 Chrome 调试模式"
echo "=========================================="
echo ""

# Step 1: 同步配置文件
echo "📌 Step 1: 同步 Windows Chrome 配置到调试目录"
echo ""
"$SCRIPT_DIR/sync_profile_from_wsl.sh" "$@"
SYNC_RESULT=$?

if [ $SYNC_RESULT -ne 0 ]; then
    echo "❌ 配置同步失败 (退出码: $SYNC_RESULT)"
    echo "尝试继续启动 Chrome..."
fi

echo ""
echo "=========================================="
echo "  配置同步完成，准备启动 Chrome"
echo "=========================================="
echo ""

# Step 2: 启动 Chrome 调试模式
echo "📌 Step 2: 启动 Chrome 调试模式"
echo ""

# 清除锁文件（无论同步是否成功都清理）
DEBUG_DIR="/mnt/c/temp/chrome-debug-profile"
echo "清除调试目录锁文件..."
rm -f "$DEBUG_DIR/SingletonLock" "$DEBUG_DIR/SingletonSocket" "$DEBUG_DIR/SingletonCookie" 2>/dev/null || true
rm -f "$DEBUG_DIR/Default/SingletonLock" "$DEBUG_DIR/Default/SingletonSocket" "$DEBUG_DIR/Default/SingletonCookie" 2>/dev/null || true
rm -f "$DEBUG_DIR/lockfile" "$DEBUG_DIR/Default/lockfile" 2>/dev/null || true
rm -f "$DEBUG_DIR/DevToolsActivePort" 2>/dev/null || true
echo "  ✅ 锁文件已清理"
echo ""

# 关闭已有 Chrome 进程
echo "关闭已有 Chrome 进程..."
powershell.exe -Command "Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" 2>/dev/null || true
sleep 3

# 再次确认没有残留 Chrome 进程
REMAINING=$(powershell.exe -Command "(Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Measure-Object).Count" 2>/dev/null | tr -d '\r\n' | xargs)
if [ -n "$REMAINING" ] && [ "$REMAINING" != "0" ]; then
    echo "⚠️  仍有 $REMAINING 个 Chrome 进程在运行"
    echo "请手动在任务管理器中结束 Chrome 后重试"
    echo ""
    echo "或在 Windows PowerShell 中运行:"
    echo "  Stop-Process -Name chrome -Force"
    echo ""
fi

# 检测 Chrome 路径
echo "检测 Chrome 安装路径..."
CHROME_PATH=""

# 方式1: 检查标准路径
CHROME_CANDIDATES=(
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
    "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"
)

for candidate in "${CHROME_CANDIDATES[@]}"; do
    if [ -f "$candidate" ]; then
        CHROME_PATH="$candidate"
        break
    fi
done

# 方式2: 通过 PowerShell 检测 LocalAppData 路径
if [ -z "$CHROME_PATH" ]; then
    LOCAL_APP=$(powershell.exe -Command "Write-Host \$env:LOCALAPPDATA" 2>/dev/null | tr -d '\r\n' | xargs)
    if [ -n "$LOCAL_APP" ]; then
        LOCAL_CHROME="/mnt/c$(echo "$LOCAL_APP" | sed 's/C://' | sed 's|\\|/|g')/Google/Chrome/Application/chrome.exe"
        if [ -f "$LOCAL_CHROME" ]; then
            CHROME_PATH="$LOCAL_CHROME"
        fi
    fi
fi

if [ -z "$CHROME_PATH" ]; then
    echo "❌ 无法检测 Chrome 安装路径"
    echo ""
    echo "请手动在 Windows PowerShell 中运行:"
    echo "  .\start_chrome_debug.ps1 -SkipCopy"
    echo ""
    exit 1
fi

echo "  ✅ Chrome: $CHROME_PATH"

# 转换为 Windows 路径
WIN_DEBUG_DIR=$(wslpath -w "$DEBUG_DIR" 2>/dev/null || echo "C:\\temp\\chrome-debug-profile")
WIN_CHROME_PATH=$(wslpath -w "$CHROME_PATH" 2>/dev/null || echo "$CHROME_PATH")

echo "  调试目录: $WIN_DEBUG_DIR"
echo ""

# 检查调试目录是否存在
if [ ! -d "$DEBUG_DIR/Default" ]; then
    echo "❌ 调试配置目录不存在: $DEBUG_DIR/Default"
    echo "请先不带 -SkipCopy 运行 start_chrome_debug.ps1"
    echo ""
    exit 1
fi

# 启动 Chrome（通过 PowerShell Start-Process，避免 cmd.exe UNC 路径问题）
echo "启动 Chrome 调试模式..."

powershell.exe -Command "
Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=9222','--user-data-dir=C:\temp\chrome-debug-profile','--profile-directory=Default','--no-first-run','--no-default-browser-check','--disable-default-apps','--disable-background-networking','--disable-translate','--disable-extensions','--disable-sync'
" 2>/dev/null

echo "等待 Chrome 启动..."
sleep 8

# 验证 CDP 端点（必须 --noproxy 绕过 WSL 代理）
echo ""
echo "验证 CDP 端点..."

CDP_OK=false
CDP_HOST=""
CDP_PORT=9222

# 尝试 localhost（绕过代理）
for i in $(seq 1 10); do
    if curl -s --noproxy '*' --connect-timeout 2 http://localhost:9222/json/version > /dev/null 2>&1; then
        CDP_OK=true
        CDP_HOST="localhost"
        CDP_PORT=9222
        break
    fi
    sleep 1
    echo "  等待中... ($i/10)" 
done

# 尝试 Windows 主机 IP（绕过代理）
if [ "$CDP_OK" = false ]; then
    HOST_IP=$(ip route | grep default | awk '{print $3}' | head -1)
    if [ -n "$HOST_IP" ]; then
        echo "  尝试 Windows 主机 IP: $HOST_IP"
        for i in $(seq 1 5); do
            if curl -s --noproxy '*' --connect-timeout 2 "http://$HOST_IP:9222/json/version" > /dev/null 2>&1; then
                CDP_OK=true
                CDP_HOST="$HOST_IP"
                CDP_PORT=9222
                break
            fi
            sleep 1
        done
    fi
fi

# Docker 容器连接方案：
# Chrome CDP 只监听 127.0.0.1:9222，Docker bridge 网络无法直接访问
# 解决: 启动 Python TCP 转发器，监听 0.0.0.0:9223 -> 127.0.0.1:9222
FORWARDER_PID=""
if [ "$CDP_OK" = true ]; then
    echo ""
    echo "启动 Docker 端口转发器 (0.0.0.0:9223 -> 127.0.0.1:9222)..."

    # 共享 Docker 网桥的 TCP 转发器（Docker 容器通过 host.docker.internal 访问）
    python3 -c "
import socket, threading, select

def forward(src, dst):
    try:
        while True:
            r, _, _ = select.select([src], [], [], 60)
            if not r: break
            data = src.recv(65536)
            if not data: break
            dst.sendall(data)
    except: pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass

def handle(client):
    try:
        upstream = socket.create_connection(('127.0.0.1', 9222), timeout=5)
    except:
        client.close()
        return
    t1 = threading.Thread(target=forward, args=(client, upstream), daemon=True)
    t2 = threading.Thread(target=forward, args=(upstream, client), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 9223))
server.listen(10)
while True:
    client, addr = server.accept()
    threading.Thread(target=handle, args=(client,), daemon=True).start()
" &
    FORWARDER_PID=$!
    sleep 1

    if kill -0 "$FORWARDER_PID" 2>/dev/null; then
        echo "  ✅ 转发器已启动 (PID: $FORWARDER_PID)"
    else
        echo "  ⚠️  转发器启动失败"
        FORWARDER_PID=""
    fi

    # 同时设置 Windows 端口转发（netsh portproxy）作为备用
    powershell.exe -Command "netsh interface portproxy add v4tov4 listenport=9222 listenaddress=0.0.0.0 connectport=9222 connectaddress=127.0.0.1" 2>/dev/null || true
    powershell.exe -Command "New-NetFirewallRule -DisplayName 'Chrome CDP Debug Port' -Direction Inbound -LocalPort 9222 -Protocol TCP -Action Allow -ErrorAction SilentlyContinue" 2>/dev/null || true
fi

echo ""
if [ "$CDP_OK" = true ]; then
    VERSION=$(curl -s --noproxy '*' "http://$CDP_HOST:$CDP_PORT/json/version" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Browser','unknown'))" 2>/dev/null || echo "unknown")
    echo "=========================================="
    echo "  ✅ Chrome 调试模式已就绪!"
    echo "=========================================="
    echo ""
    echo "  Chrome 版本: $VERSION"
    echo ""
    echo "  📌 连接方式:"
    echo "  - WSL:       http://localhost:9222"
    echo "  - Docker:    http://host.docker.internal:9223"
    echo ""
    echo "  Docker 容器内需要设置 Host: localhost 头"
    echo "  n8n 工作流已自动处理此问题"
    echo ""
    echo "📌 运行爬虫:"
    echo "  ./run_with_windows_chrome.sh"
    echo ""
    echo "💡 转发器 PID: $FORWARDER_PID (停止: kill $FORWARDER_PID)"
else
    echo "=========================================="
    echo "  ⚠️  Chrome 已启动但调试端口未就绪"
    echo "=========================================="
    echo ""
    echo "  可能的原因:"
    echo "  1. Chrome 正在使用原始配置目录（Singleton 冲突）"
    echo "  2. Chrome 136+ 禁止了默认目录的远程调试"
    echo "  3. 防火墙阻止了端口"
    echo ""
    echo "  请尝试:"
    echo "  1. 在 Windows PowerShell 中运行:"
    echo "     .\start_chrome_debug.ps1"
    echo ""
    echo "  2. 手动验证 (WSL，需加 --noproxy):"
    echo "     curl --noproxy '*' http://localhost:9222/json/version"
    echo ""
fi