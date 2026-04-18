#!/bin/bash
# Windows 原生 Chrome + Python 爬虫方案
# 让 Python 爬虫直接在 Windows 上运行，避免 Docker 网络问题

echo "=========================================="
echo "  Windows 原生 Chrome 调试模式"
echo "=========================================="
echo ""

# Step 1: 检查并关闭日常 Chrome
echo "Step 1: 准备 Chrome..."
CHROME_COUNT=$(powershell.exe -Command "(Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Measure-Object).Count" 2>/dev/null | tr -d '\r\n')

if [ "$CHROME_COUNT" != "0" ]; then
    echo "  发现 $CHROME_COUNT 个 Chrome 进程"
    echo "  需要关闭日常 Chrome 才能启动调试模式"
    echo ""
    read -p "按 Enter 关闭 Chrome（请确保已保存工作），或 Ctrl+C 取消..."
    
    powershell.exe -Command "Stop-Process -Name 'chrome' -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 3" 2>/dev/null
    
    # 确认
    NEW_COUNT=$(powershell.exe -Command "(Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Measure-Object).Count" 2>/dev/null | tr -d '\r\n')
    if [ "$NEW_COUNT" != "0" ]; then
        echo "  错误: 仍有 $NEW_COUNT 个 Chrome 进程在运行"
        echo "  请手动在任务管理器中结束所有 Chrome 后重试"
        exit 1
    fi
fi

echo "  Chrome 已准备就绪"
echo ""

# Step 2: 清除锁文件
echo "Step 2: 清除配置锁..."
LOCK_PATH="/mnt/c/Users/王/AppData/Local/Google/Chrome/User Data"
rm -f "$LOCK_PATH/SingletonLock" "$LOCK_PATH/SingletonSocket" "$LOCK_PATH/SingletonCookie" 2>/dev/null
rm -f "$LOCK_PATH/Default/SingletonLock" "$LOCK_PATH/Default/SingletonSocket" 2>/dev/null
echo "  锁文件已清除"
echo ""

# Step 3: 启动调试 Chrome（使用原始配置）
echo "Step 3: 启动 Chrome 调试模式..."
echo "  配置: %LOCALAPPDATA%\\Google\\Chrome\\User Data"
echo "  登录状态: 完全保留"
echo ""

# 启动 Chrome（不使用复制配置）
cmd.exe /C start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" ^
  --profile-directory=Default ^
  --no-first-run ^
  --no-default-browser-check ^
  --disable-background-networking ^
  --disable-default-apps ^
  2>/dev/null &

echo "等待 Chrome 启动（8秒）..."
sleep 8

# Step 4: 验证 CDP
echo ""
echo "Step 4: 验证调试端口..."

for i in $(seq 1 10); do
    if curl -s --noproxy '*' --connect-timeout 2 http://localhost:9222/json/version > /dev/null 2>&1; then
        VERSION=$(curl -s --noproxy '*' http://localhost:9222/json/version 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Browser','unknown'))" 2>/dev/null)
        
        echo ""
        echo "=========================================="
        echo "  Chrome 调试模式已就绪!"
        echo "=========================================="
        echo ""
        echo "  版本: $VERSION"
        echo "  CDP: http://localhost:9222"
        echo ""
        echo "  登录状态: ✅ 完全保留（使用原始配置）"
        echo ""
        echo "=========================================="
        echo "  运行方案选择"
        echo "=========================================="
        echo ""
        echo "方案 A - WSL 命令行爬虫（推荐测试）:"
        echo "  ./run_with_windows_chrome.sh \"搜索词\" 50 100"
        echo ""
        echo "方案 B - n8n 工作流:"
        echo "  导入: n8n_workflow_windows_chrome.json"
        echo "  注意: python-runner 需使用 host 网络模式"
        echo ""
        echo "方案 C - Windows 原生 Python（最稳定）:"
        echo "  在 Windows PowerShell 中运行 Python 爬虫"
        echo "  绕过 Docker 网络层，直接连接 localhost:9222"
        echo ""
        echo "⚠️  重要提示:"
        echo "  你现在看到的 Chrome 窗口就是调试实例"
        echo "  请检查 Pinterest 是否已登录"
        echo "  使用完毕后关闭此窗口，重新打开日常 Chrome"
        echo ""
        exit 0
    fi
    sleep 1
    echo "  等待中... ($i/10)"
done

echo ""
echo "=========================================="
echo "  启动失败"
echo "=========================================="
echo ""
echo "Chrome 136+ 可能拒绝了默认目录的远程调试。"
echo ""
echo "解决方案:"
echo "  1. 重启电脑后重试（清除所有锁文件）"
echo "  2. 使用复制配置方案（可能需重新登录 Pinterest）:"
echo "     ./sync_and_start.sh"
echo ""