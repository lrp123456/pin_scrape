#!/bin/bash
# 直接使用 Windows 原始 Chrome 配置启动调试模式
# 优点: 不复制配置，完全保持登录状态

echo "=========================================="
echo "  Chrome 调试模式 - 使用原始配置"
echo "=========================================="
echo ""

# Step 1: 关闭日常 Chrome（必须，否则无法启动第二个实例）
echo "Step 1: 关闭日常 Chrome..."
echo "  请确保已保存所有工作，Chrome 将被关闭"
echo ""
read -p "按 Enter 继续，或 Ctrl+C 取消..."

powershell.exe -Command "Stop-Process -Name 'chrome' -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 3" 2>/dev/null

# 确认关闭
CHROME_COUNT=$(powershell.exe -Command "(Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Measure-Object).Count" 2>/dev/null | tr -d '\r\n')
if [ "$CHROME_COUNT" != "0" ]; then
    echo "仍有 $CHROME_COUNT 个 Chrome 进程在运行"
    echo "  请手动在任务管理器中结束 Chrome 后重试"
    exit 1
fi

echo "  Chrome 已关闭"
echo ""

# Step 2: 清除原始配置的锁文件（否则 Chrome 以为还在运行）
echo "Step 2: 清除配置锁..."
rm -f "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/SingletonLock" 2>/dev/null && echo "  已清除: SingletonLock"
rm -f "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/SingletonSocket" 2>/dev/null && echo "  已清除: SingletonSocket"
rm -f "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/SingletonCookie" 2>/dev/null && echo "  已清除: SingletonCookie"
rm -f "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/SingletonLock" 2>/dev/null && echo "  已清除: Default/SingletonLock"
rm -f "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data/Default/SingletonSocket" 2>/dev/null && echo "  已清除: Default/SingletonSocket"

echo ""

# Step 3: 启动调试 Chrome（使用原始配置）
echo "Step 3: 启动 Chrome 调试模式..."
echo "  使用原始配置: %LOCALAPPDATA%\\Google\\Chrome\\User Data"
echo ""

# 使用 cmd.exe 启动，避免 PowerShell 转义问题
WIN_USER_DATA=$(wslpath -w "/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data")
cmd.exe /C start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$WIN_USER_DATA" --profile-directory=Default --no-first-run --no-default-browser-check 2>/dev/null &

echo "等待 Chrome 启动..."
sleep 8

# Step 4: 验证 CDP
echo ""
echo "Step 4: 验证 CDP 端点..."

for i in $(seq 1 10); do
    if curl -s --noproxy '*' --connect-timeout 2 http://localhost:9222/json/version > /dev/null 2>&1; then
        echo ""
        echo "=========================================="
        echo "  Chrome 调试模式已就绪!"
        echo "=========================================="
        echo ""
        
        VERSION=$(curl -s --noproxy '*' http://localhost:9222/json/version 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Browser','unknown'))" 2>/dev/null)
        echo "  Chrome 版本: $VERSION"
        echo "  CDP 端点: http://localhost:9222"
        echo ""
        echo "现在可以:"
        echo "  1. 运行爬虫: ./run_with_windows_chrome.sh"
        echo "  2. 或使用 n8n 工作流"
        echo ""
        echo "注意: 调试 Chrome 窗口就是你现在看到的 Chrome"
        echo "    它使用的是你的日常配置，登录状态完全保留"
        echo ""
        echo "使用完毕后:"
        echo "  关闭调试 Chrome 窗口，然后重新打开日常 Chrome 即可"
        exit 0
    fi
    sleep 1
    echo "  等待中... ($i/10)"
done

echo ""
echo "=========================================="
echo "  Chrome 已启动但调试端口未就绪"
echo "=========================================="
echo ""
echo "  可能原因:"
echo "  1. Chrome 136+ 禁止了默认目录的远程调试"
echo "  2. 需要重新打开日常 Chrome 再试一次"
echo ""
echo "  如果始终无法启动，请使用复制配置方案:"
echo "  ./sync_and_start.sh"
