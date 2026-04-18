# 完整诊断和启动脚本
# 以管理员身份保存并运行

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Chrome 调试模式诊断工具" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查现有 Chrome 进程
Write-Host "🔍 步骤 1: 检查现有 Chrome 进程..." -ForegroundColor Yellow
$chromeProcesses = Get-Process -Name "chrome" -ErrorAction SilentlyContinue
if ($chromeProcesses) {
    Write-Host "   发现 $($chromeProcesses.Count) 个 Chrome 进程" -ForegroundColor Red
    Write-Host "   正在强制关闭..." -ForegroundColor Yellow
    Stop-Process -Name "chrome" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "   ✅ Chrome 已关闭" -ForegroundColor Green
} else {
    Write-Host "   ✅ 没有发现 Chrome 进程" -ForegroundColor Green
}
Write-Host ""

# 2. 检查端口 9222
Write-Host "🔍 步骤 2: 检查端口 9222..." -ForegroundColor Yellow
$portCheck = netstat -ano | findstr 9222
if ($portCheck) {
    Write-Host "   ⚠️  端口 9222 被占用:" -ForegroundColor Red
    Write-Host "   $portCheck"
    Write-Host "   尝试释放端口..."
    $lines = $portCheck -split "`n"
    foreach ($line in $lines) {
        if ($line -match "LISTENING\s+(\d+)") {
            $pid = $matches[1]
            Write-Host "   杀死进程 PID: $pid"
            taskkill /F /PID $pid 2>$null
        }
    }
} else {
    Write-Host "   ✅ 端口 9222 可用" -ForegroundColor Green
}
Write-Host ""

# 3. 验证用户数据目录
Write-Host "🔍 步骤 3: 验证 Chrome 配置目录..." -ForegroundColor Yellow
$userDataDir = "$env:LOCALAPPDATA\Google\Chrome\User Data"
if (Test-Path $userDataDir) {
    Write-Host "   ✅ 配置目录存在: $userDataDir" -ForegroundColor Green
    # 检查 Cookies 文件
    $cookiesPath = Join-Path $userDataDir "Default\Network\Cookies"
    if (Test-Path $cookiesPath) {
        $size = (Get-Item $cookiesPath).Length
        Write-Host "   ✅ Cookies 文件存在 (${size} bytes)" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  未找到 Cookies 文件" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ❌ 配置目录不存在!" -ForegroundColor Red
    Write-Host "   可能的路径:" -ForegroundColor Yellow
    Get-ChildItem "$env:LOCALAPPDATA\Google" -ErrorAction SilentlyContinue | Select-Object -First 5
}
Write-Host ""

# 4. 启动 Chrome 调试模式
Write-Host "🚀 步骤 4: 启动 Chrome 调试模式..." -ForegroundColor Yellow
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"

if (-not (Test-Path $chromePath)) {
    Write-Host "   ❌ Chrome 未安装在默认位置" -ForegroundColor Red
    # 尝试查找 Chrome
    $chromePath = (Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" -ErrorAction SilentlyContinue).'(Default)'
    if (-not $chromePath) {
        Write-Host "   请手动指定 Chrome 路径" -ForegroundColor Red
        exit 1
    }
}

Write-Host "   Chrome 路径: $chromePath" -ForegroundColor Cyan
Write-Host "   正在启动..." -ForegroundColor Yellow

# 使用 Start-Process 以便更好地控制
$process = Start-Process -FilePath $chromePath -ArgumentList `
    "--remote-debugging-port=9222", `
    "--user-data-dir=`"$userDataDir`"", `
    "--no-first-run", `
    "--no-default-browser-check", `
    "--start-maximized" `-PassThru

Write-Host "   Chrome PID: $($process.Id)" -ForegroundColor Cyan
Write-Host "   等待 Chrome 启动..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# 5. 验证调试端口
Write-Host ""
Write-Host "🔍 步骤 5: 验证调试端口..." -ForegroundColor Yellow
$maxAttempts = 5
$connected = $false

for ($i = 1; $i -le $maxAttempts; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:9222/json/version" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        Write-Host "   ✅ 调试端口正常!" -ForegroundColor Green
        Write-Host "   响应: $($response.Content)" -ForegroundColor Gray
        $connected = $true
        break
    } catch {
        Write-Host "   尝试 $i/$maxAttempts..." -ForegroundColor Yellow
        Start-Sleep -Seconds 1
    }
}

if (-not $connected) {
    Write-Host ""
    Write-Host "❌ 无法连接到调试端口" -ForegroundColor Red
    Write-Host ""
    Write-Host "可能的解决方案:" -ForegroundColor Yellow
    Write-Host "1. 检查 Windows Defender 防火墙设置" -ForegroundColor White
    Write-Host "2. 尝试以管理员身份运行 PowerShell" -ForegroundColor White
    Write-Host "3. 检查 Chrome 是否被其他安全软件阻止" -ForegroundColor White
    Write-Host ""
    Write-Host "调试信息:" -ForegroundColor Yellow
    Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Select-Object Id, Path, CommandLine | Format-Table -AutoSize
} else {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "✅ Chrome 调试模式启动成功!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "调试端点: http://localhost:9222" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "现在可以在 WSL 中运行爬虫:" -ForegroundColor Yellow
    Write-Host '  curl -X POST http://localhost:5000/run/pinterest_scraper_n8n.py \' -ForegroundColor White
    Write-Host '    -H "Content-Type: application/json" \' -ForegroundColor White
    Write-Host '    -d '"'"'{"args": ["--query", "现代简约", "--connect", "--cdp-endpoint", "http://host.docker.internal:9222"]}'"'"'' -ForegroundColor White
}

Write-Host ""
Read-Host "按 Enter 键退出"
