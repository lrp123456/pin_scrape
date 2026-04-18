<#
.SYNOPSIS
    启动 Chrome 调试模式 - 用于 Pinterest 爬虫

.DESCRIPTION
    解决 Chrome 多配置文件 + SingletonLock + Chrome 136+ 限制的调试模式启动问题。
    
    工作原理:
    1. 关闭所有 Chrome 进程（包括后台进程）
    2. 将 Default 配置文件复制到 C:\temp\chrome-debug-profile（非标准目录，绕过 Chrome 136+ 限制）
    3. 清除复制目录中的锁文件
    4. 使用 --remote-debugging-port=9222 启动 Chrome（非标准 user-data-dir）
    5. 用户可以随后重新打开常规 Chrome（两个实例可以并行运行）

.EXAMPLE
    .\start_chrome_debug.ps1                # 完整流程：关闭Chrome → 复制配置 → 启动调试
    .\start_chrome_debug.ps1 -SkipCopy     # 跳过复制，直接启动已有的调试配置
    .\start_chrome_debug.ps1 -Port 9223    # 使用不同的调试端口
#>

param(
    [switch]$SkipCopy = $false,
    [int]$Port = 9222,
    [string]$DebugProfileDir = "C:\temp\chrome-debug-profile"
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Chrome 调试模式启动器 (Pinterest 爬虫)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================
# Step 1: 检查 Chrome 安装路径
# ============================================
Write-Host "[1/5] 检查 Chrome 安装..." -ForegroundColor Yellow

$chromePaths = @(
    "${env:PROGRAMFILES}\Google\Chrome\Application\chrome.exe",
    "${env:PROGRAMFILES(X86)}\Google\Chrome\Application\chrome.exe",
    "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)

$chromeExe = $null
foreach ($path in $chromePaths) {
    if (Test-Path $path) {
        $chromeExe = $path
        break
    }
}

if (-not $chromeExe) {
    Write-Host "  ❌ 未找到 Chrome 安装" -ForegroundColor Red
    Write-Host "  请安装 Google Chrome 后重试" -ForegroundColor Red
    exit 1
}

Write-Host "  ✅ Chrome: $chromeExe" -ForegroundColor Green

# ============================================
# Step 2: 关闭所有 Chrome 进程
# ============================================
Write-Host ""
Write-Host "[2/5] 关闭 Chrome 进程..." -ForegroundColor Yellow

$chromeProcesses = Get-Process -Name "chrome" -ErrorAction SilentlyContinue

if ($chromeProcesses) {
    $count = ($chromeProcesses | Measure-Object).Count
    Write-Host "  发现 $count 个 Chrome 进程，正在关闭..." -ForegroundColor Yellow
    
    # 强制关闭所有 Chrome 进程
    $chromeProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    
    # 等待进程关闭
    $waitCount = 0
    while ($waitCount -lt 10) {
        Start-Sleep -Seconds 1
        $remaining = Get-Process -Name "chrome" -ErrorAction SilentlyContinue
        if (-not $remaining) { break }
        $waitCount++
        Write-Host "  等待进程关闭... ($waitCount/10)" -ForegroundColor Gray
    }
    
    # 最终检查
    $stillRunning = Get-Process -Name "chrome" -ErrorAction SilentlyContinue
    if ($stillRunning) {
        Write-Host "  ⚠️  仍有 Chrome 进程在运行" -ForegroundColor Yellow
        Write-Host "  请手动在任务管理器中结束所有 Chrome 进程后重试" -ForegroundColor Yellow
        Read-Host "按 Enter 重试，或按 Ctrl+C 退出"
        
        $stillRunning | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        
        $finalCheck = Get-Process -Name "chrome" -ErrorAction SilentlyContinue
        if ($finalCheck) {
            Write-Host "  ❌ 无法关闭所有 Chrome 进程" -ForegroundColor Red
            Write-Host "  请在任务管理器中手动结束 Chrome 后重试" -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host "  ✅ Chrome 已关闭" -ForegroundColor Green
} else {
    Write-Host "  ✅ 没有运行中的 Chrome 进程" -ForegroundColor Green
}

# ============================================
# Step 3: 复制配置文件到非标准目录
# ============================================
Write-Host ""
Write-Host "[3/5] 准备调试配置文件..." -ForegroundColor Yellow

$srcDir = "${env:LOCALAPPDATA}\Google\Chrome\User Data"

if (-not $SkipCopy) {
    # 检查源目录
    if (-not (Test-Path $srcDir)) {
        Write-Host "  ❌ Chrome 配置目录不存在: $srcDir" -ForegroundColor Red
        exit 1
    }
    
    if (-not (Test-Path "$srcDir\Default")) {
        Write-Host "  ❌ Default 配置文件不存在" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "  源目录: $srcDir\Default" -ForegroundColor Gray
    Write-Host "  目标目录: $DebugProfileDir" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  📝 说明: 使用非标准目录绕过 Chrome 136+ 的远程调试限制" -ForegroundColor Yellow
    Write-Host "  📝 登录状态（Cookies等）会从原始配置复制过来" -ForegroundColor Yellow
    Write-Host ""
    
    # 清理旧的调试配置
    if (Test-Path $DebugProfileDir) {
        Write-Host "  清理旧的调试配置..." -ForegroundColor Gray
        Remove-Item -Path $DebugProfileDir -Recurse -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    
    # 创建目标目录
    New-Item -ItemType Directory -Path $DebugProfileDir -Force | Out-Null
    New-Item -ItemType Directory -Path "$DebugProfileDir\Default\Network" -Force | Out-Null
    
    Write-Host "  复制配置文件（跳过缓存以加速）..." -ForegroundColor Gray
    
    # 复制 Local State（必须，Chrome 需要它来识别配置文件）
    Copy-Item "$srcDir\Local State" "$DebugProfileDir\Local State" -Force
    
    # 复制 First Run 文件（避免首次运行提示）
    if (Test-Path "$srcDir\First Run") {
        Copy-Item "$srcDir\First Run" "$DebugProfileDir\First Run" -Force
    }
    
    # 复制 Last Version 文件
    if (Test-Path "$srcDir\Last Version") {
        Copy-Item "$srcDir\Last Version" "$DebugProfileDir\Last Version" -Force
    }
    
    # 使用 robocopy 复制 Default 配置文件（排除缓存目录）
    $excludeDirs = @(
        'Cache', 'Code Cache', 'GPUCache', 'Service Worker',
        'extensions', 'Extension Rules', 'Extension State',
        'Extension Scripts', 'Extension Settings',
        'IndexedDB', 'Session Storage', 'blob_storage',
        'File System', 'Local Extension Settings',
        'Sync Extension Settings', 'Platform Notifications',
        'databases', 'Application Cache', 'ShaderCache',
        'GrShaderCache', 'Download Service', 'OptimizationHints',
        'MEIPreload', 'Hyphen', 'DIPS', 'BudgetDatabase'
    )
    
    $robocopyArgs = @(
        "$srcDir\Default",
        "$DebugProfileDir\Default",
        '/E', '/R:1', '/W:1',
        '/NFL', '/NDL', '/NJ', '/NP',
        '/MT:8'
    )
    
    foreach ($dir in $excludeDirs) {
        $robocopyArgs += "/XD"
        $robocopyArgs += """$srcDir\Default\$dir"""
    }
    
    Write-Host "  正在复制 Default 配置文件..." -ForegroundColor Gray
    
    $result = & robocopy @robocopyArgs 2>$null
    $exitCode = $LASTEXITCODE
    
    # robocopy 返回码: 0-7 为成功，8+ 为错误
    if ($exitCode -ge 8) {
        Write-Host "  ⚠️  复制过程中有一些错误（返回码: $exitCode）" -ForegroundColor Yellow
    } else {
        Write-Host "  ✅ 配置文件复制完成" -ForegroundColor Green
    }
    
    # 验证并强制复制关键登录文件（robocopy 可能因文件锁定而跳过）
    Write-Host "  验证关键登录文件..." -ForegroundColor Gray
    
    $sourceTargetPairs = @(
        @{Src="$srcDir\Default\Network\Cookies"; Dst="$DebugProfileDir\Default\Network\Cookies"; Name="Cookies"},
        @{Src="$srcDir\Default\Network\Cookies-journal"; Dst="$DebugProfileDir\Default\Network\Cookies-journal"; Name="Cookies-journal"},
        @{Src="$srcDir\Default\Login Data"; Dst="$DebugProfileDir\Default\Login Data"; Name="Login Data"},
        @{Src="$srcDir\Default\Login Data-journal"; Dst="$DebugProfileDir\Default\Login Data-journal"; Name="Login Data-journal"},
        @{Src="$srcDir\Default\Preferences"; Dst="$DebugProfileDir\Default\Preferences"; Name="Preferences"},
        @{Src="$srcDir\Default\Secure Preferences"; Dst="$DebugProfileDir\Default\Secure Preferences"; Name="Secure Preferences"},
        @{Src="$srcDir\Default\Web Data"; Dst="$DebugProfileDir\Default\Web Data"; Name="Web Data"},
        @{Src="$srcDir\Default\Web Data-journal"; Dst="$DebugProfileDir\Default\Web Data-journal"; Name="Web Data-journal"},
        @{Src="$srcDir\Default\Bookmarks"; Dst="$DebugProfileDir\Default\Bookmarks"; Name="Bookmarks"}
    )
    
    $missingFiles = @()
    $forcedCopies = @()
    
    foreach ($pair in $sourceTargetPairs) {
        $srcFile = $pair.Src
        $dstFile = $pair.Dst
        $name = $pair.Name
        
        if (-not (Test-Path $srcFile)) {
            continue
        }
        
        $needsCopy = $false
        if (-not (Test-Path $dstFile)) {
            $needsCopy = $true
        } else {
            $srcSize = (Get-Item $srcFile -ErrorAction SilentlyContinue).Length
            $dstSize = (Get-Item $dstFile -ErrorAction SilentlyContinue).Length
            if ($srcSize -ne $dstSize) {
                $needsCopy = $true
            }
        }
        
        if ($needsCopy) {
            $dstDir = Split-Path $dstFile -Parent
            if (-not (Test-Path $dstDir)) {
                New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
            }
            
            # 尝试多次复制（文件可能暂时被锁定）
            $copied = $false
            for ($attempt = 1; $attempt -le 3; $attempt++) {
                try {
                    Copy-Item $srcFile $dstFile -Force -ErrorAction Stop
                    if (Test-Path $dstFile) {
                        $copied = $true
                        $forcedCopies += $name
                        break
                    }
                } catch {
                    Start-Sleep -Milliseconds 500
                }
            }
            
            if (-not $copied) {
                $missingFiles += $name
            }
        }
    }
    
    # 检查最关键的 Cookies 文件
    $cookiesFile = "$DebugProfileDir\Default\Network\Cookies"
    if (-not (Test-Path $cookiesFile) -or (Get-Item $cookiesFile -ErrorAction SilentlyContinue).Length -eq 0) {
        Write-Host ""
        Write-Host "  ⚠️  Cookies 文件缺失或为空！" -ForegroundColor Red
        Write-Host "  Pinterest 登录状态将无法保持" -ForegroundColor Red
        Write-Host "  请确保关闭 Chrome 后重新运行此脚本" -ForegroundColor Yellow
    } else {
        $cookiesSize = (Get-Item $cookiesFile).Length
        Write-Host "  ✅ Cookies 文件已就绪 ($cookiesSize bytes)" -ForegroundColor Green
    }
    
    if ($forcedCopies.Count -gt 0) {
        Write-Host "  ✅ 强制复制了 $($forcedCopies.Count) 个文件: $($forcedCopies -join ', ')" -ForegroundColor Green
    }
    
    if ($missingFiles.Count -gt 0) {
        Write-Host "  ⚠️  缺少关键文件: $($missingFiles -join ', ')" -ForegroundColor Yellow
        Write-Host "  Pinterest 登录状态可能未保留" -ForegroundColor Yellow
    }

} else {
    Write-Host "  跳过复制，使用已有调试配置: $DebugProfileDir" -ForegroundColor Yellow
    
    if (-not (Test-Path "$DebugProfileDir\Default")) {
        Write-Host "  ❌ 调试配置目录不存在: $DebugProfileDir\Default" -ForegroundColor Red
        Write-Host "  请先不带 -SkipCopy 运行一次" -ForegroundColor Red
        exit 1
    }
}

# ============================================
# Step 4: 清除锁文件
# ============================================
Write-Host ""
Write-Host "[4/5] 清除锁文件..." -ForegroundColor Yellow

$lockFiles = @(
    "$DebugProfileDir\SingletonLock",
    "$DebugProfileDir\SingletonSocket",
    "$DebugProfileDir\SingletonCookie",
    "$DebugProfileDir\Default\SingletonLock",
    "$DebugProfileDir\Default\SingletonSocket",
    "$DebugProfileDir\Default\SingletonCookie",
    "$DebugProfileDir\lockfile",
    "$DebugProfileDir\Default\lockfile",
    "$DebugProfileDir\DevToolsActivePort"
)

foreach ($file in $lockFiles) {
    if (Test-Path $file) {
        Remove-Item $file -Force -ErrorAction SilentlyContinue
        Write-Host "  已删除: $(Split-Path $file -Leaf)" -ForegroundColor Gray
    }
}

Write-Host "  ✅ 锁文件已清理" -ForegroundColor Green

# ============================================
# Step 5: 启动 Chrome 调试模式
# ============================================
Write-Host ""
Write-Host "[5/5] 启动 Chrome 调试模式..." -ForegroundColor Yellow

# 检查端口是否被占用
$portInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "  ⚠️  端口 $Port 已被占用" -ForegroundColor Yellow
    $procId = ($portInUse | Select-Object -First 1).OwningProcess
    Write-Host "  占用进程 PID: $procId" -ForegroundColor Gray
    
    $killChoice = Read-Host "是否终止占用进程? (y/n)"
    if ($killChoice -eq 'y') {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    } else {
        Write-Host "  ❌ 端口 $Port 被占用，无法启动" -ForegroundColor Red
        exit 1
    }
}

# 构建启动参数
# 关键: --user-data-dir 必须是非标准目录（Chrome 136+ 限制）
$startArgs = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$DebugProfileDir",
    "--profile-directory=Default",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-default-apps",
    "--disable-background-networking",
    "--disable-translate",
    "--disable-extensions",
    "--disable-sync"
)

Write-Host "  启动参数:" -ForegroundColor Gray
Write-Host "    --remote-debugging-port=$Port" -ForegroundColor White
Write-Host "    --user-data-dir=$DebugProfileDir" -ForegroundColor White
Write-Host "    --profile-directory=Default" -ForegroundColor White
Write-Host ""

# 启动 Chrome
try {
    Start-Process $chromeExe -ArgumentList $startArgs
    Write-Host "  ✅ Chrome 已启动" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Chrome 启动失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 等待 CDP 端点就绪
Write-Host ""
Write-Host "等待 Chrome 调试端口就绪..." -ForegroundColor Yellow

$maxWait = 15
$waited = 0
$cdpReady = $false
$versionInfo = $null

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 1
    $waited++
    
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$Port/json/version" -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            $cdpReady = $true
            $versionInfo = $response.Content | ConvertFrom-Json
            break
        }
    } catch {
        # 端口尚未就绪
    }
    
    Write-Host "  等待中... ($waited/$maxWait)" -ForegroundColor Gray
}

Write-Host ""
if ($cdpReady) {
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "  ✅ Chrome 调试模式已就绪!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  调试端口: $Port" -ForegroundColor Cyan
    Write-Host "  CDP 端点: http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "  Chrome 版本: $($versionInfo.Browser)" -ForegroundColor Cyan
    Write-Host ""
    # 设置端口转发（让 Docker 容器能访问 CDP）
    # Chrome 只监听 127.0.0.1，Docker bridge 网络无法直接访问
    # 使用 netsh portproxy 将 0.0.0.0:9222 转发到 127.0.0.1:9222
    Write-Host ""
    Write-Host "  设置端口转发（Docker 容器访问）..." -ForegroundColor Yellow
    try {
        $existingProxy = netsh interface portproxy show v4tov4 | Select-String ":$Port "
        if ($existingProxy) {
            Write-Host "  端口转发已存在" -ForegroundColor Gray
        } else {
            netsh interface portproxy add v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=127.0.0.1 2>$null
            Write-Host "  ✅ 端口转发已添加: 0.0.0.0:$Port -> 127.0.0.1:$Port" -ForegroundColor Green
        }
        
        # 添加防火墙规则
        $existingRule = Get-NetFirewallRule -DisplayName "Chrome CDP Debug Port" -ErrorAction SilentlyContinue
        if (-not $existingRule) {
            New-NetFirewallRule -DisplayName "Chrome CDP Debug Port" -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
            Write-Host "  ✅ 防火墙规则已添加" -ForegroundColor Green
        } else {
            Write-Host "  防火墙规则已存在" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  ⚠️  端口转发设置失败（需要管理员权限）" -ForegroundColor Yellow
        Write-Host "  请以管理员身份运行 PowerShell 并执行:" -ForegroundColor Yellow
        Write-Host "  netsh interface portproxy add v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=127.0.0.1" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host "  📌 连接方式:" -ForegroundColor Yellow
    Write-Host "  - 本机:     http://localhost:$Port" -ForegroundColor White
    Write-Host "  - WSL:      http://localhost:$Port（需加 --noproxy）" -ForegroundColor White
    Write-Host "  - Docker:   http://host.docker.internal:9223" -ForegroundColor White
    Write-Host ""
    Write-Host "  💡 提示:" -ForegroundColor Yellow
    Write-Host "  - Docker 容器请使用端口 9223（WSL 上运行的 TCP 转发器）" -ForegroundColor White
    Write-Host "  - Docker 容器访问时需要设置 Host: localhost 头" -ForegroundColor White
    Write-Host "  - 现在可以重新打开常规 Chrome（两个实例可以并行运行）" -ForegroundColor White
    Write-Host "  - 调试 Chrome 使用独立的配置文件，不影响日常使用" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "  ⚠️  Chrome 已启动但调试端口未就绪" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "  可能的原因:" -ForegroundColor Yellow
    Write-Host "  1. Chrome 正在加载配置文件，请稍等片刻" -ForegroundColor White
    Write-Host "  2. 防火墙阻止了端口 $Port" -ForegroundColor White
    Write-Host "  3. Chrome 可能未正确启动调试模式" -ForegroundColor White
    Write-Host ""
    Write-Host "  请在 Chrome 地址栏输入 chrome://version 检查:" -ForegroundColor Yellow
    Write-Host "  确认 --remote-debugging-port 出现在命令行参数中" -ForegroundColor White
    Write-Host ""
    Write-Host "  手动验证命令:" -ForegroundColor Yellow
    Write-Host "  curl http://localhost:$Port/json/version" -ForegroundColor White
    Write-Host ""
}

Read-Host "按 Enter 键关闭此窗口（Chrome 调试实例将继续运行）"