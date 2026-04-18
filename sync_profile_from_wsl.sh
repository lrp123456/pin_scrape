#!/bin/bash
# 从 WSL 同步 Windows Chrome 配置到调试目录
# 用法: ./sync_profile_from_wsl.sh [Windows用户名]
#
# 此脚本将 Windows Chrome Default 配置文件复制到 C:\temp\chrome-debug-profile
# 绕过 Chrome 136+ 对默认目录的远程调试限制
#
# 注意: 建议在 Windows Chrome 关闭时运行（确保 cookies 和 session 文件完整）

set -e

echo "=========================================="
echo "  同步 Windows Chrome 配置到调试目录"
echo "=========================================="
echo ""

# 获取 Windows 用户名
if [ -n "$1" ]; then
    WINDOWS_USER="$1"
else
    # 尝试自动检测
    WINDOWS_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n' | xargs)
    if [ -z "$WINDOWS_USER" ] || [ "$WINDOWS_USER" = "%USERNAME%" ]; then
        WINDOWS_USER=$(powershell.exe -Command "Write-Host \$env:USERNAME" 2>/dev/null | tr -d '\r\n' | xargs)
    fi
    # 从 /mnt/c/Users/ 目录检测
    if [ -z "$WINDOWS_USER" ] || [ "$WINDOWS_USER" = "" ]; then
        WINDOWS_USER=$(ls /mnt/c/Users/ 2>/dev/null | grep -v -E "^Public$|^Default$|^All Users|^Default User|^desktop.ini" | head -1)
    fi
fi

if [ -z "$WINDOWS_USER" ]; then
    echo "❌ 无法检测 Windows 用户名"
    echo "请手动指定: ./sync_profile_from_wsl.sh 你的用户名"
    echo ""
    echo "可用的用户目录:"
    ls -la /mnt/c/Users/ 2>/dev/null | grep -v "Public\|Default\|All Users"
    exit 1
fi

echo "Windows 用户名: $WINDOWS_USER"
echo ""

# 设置路径
SRC_DIR="/mnt/c/Users/$WINDOWS_USER/AppData/Local/Google/Chrome/User Data"
DST_DIR="/mnt/c/temp/chrome-debug-profile"

echo "源目录: $SRC_DIR/Default"
echo "目标目录: $DST_DIR"
echo ""

# 检查源目录
if [ ! -d "$SRC_DIR/Default" ]; then
    echo "❌ Chrome Default 配置目录不存在"
    echo "路径: $SRC_DIR/Default"
    echo ""
    echo "请确认:"
    echo "  1. Chrome 已安装"
    echo "  2. 用户名正确: $WINDOWS_USER"
    exit 1
fi

# 检查关键文件
CRITICAL_FILES=(
    "$SRC_DIR/Default/Network/Cookies"
    "$SRC_DIR/Default/Login Data"
    "$SRC_DIR/Default/Preferences"
    "$SRC_DIR/Default/Web Data"
    "$SRC_DIR/Local State"
)

MISSING=0
for file in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "⚠️  缺少: $(basename "$file")"
        MISSING=$((MISSING + 1))
    fi
done

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "⚠️  有 $MISSING 个关键文件缺失"
    echo "可能原因: Chrome 正在运行，请先关闭 Chrome 后重试"
    echo ""
    read -p "是否继续? (y/n): " CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        exit 1
    fi
fi

# 创建目标目录
echo "创建目标目录..."
mkdir -p "$DST_DIR/Default/Network" 2>/dev/null || true

# 检查 Windows 是否有 temp 目录（WSL 下可能需要）
if [ ! -d "/mnt/c/temp" ]; then
    echo "创建 C:\temp 目录..."
    mkdir -p "/mnt/c/temp" 2>/dev/null || {
        echo "❌ 无法创建 C:\temp 目录"
        echo "请在 Windows PowerShell 中运行: mkdir C:\temp"
        exit 1
    }
fi

# 清理旧的调试配置（保留目录结构）
echo "清理旧的调试配置..."
# 只删除内容，不删除目录本身（避免 WSL 权限问题）
rm -rf "$DST_DIR/Default" 2>/dev/null || true
rm -f "$DST_DIR/Local State" 2>/dev/null || true
rm -f "$DST_DIR/First Run" 2>/dev/null || true
rm -f "$DST_DIR/Last Version" 2>/dev/null || true

# 复制 Local State（Chrome 需要它来识别配置文件）
echo "复制 Local State..."
cp -f "$SRC_DIR/Local State" "$DST_DIR/Local State" 2>/dev/null || {
    echo "⚠️  复制 Local State 失败，可能在被 Chrome 使用中"
}

# 复制 First Run
if [ -f "$SRC_DIR/First Run" ]; then
    cp -f "$SRC_DIR/First Run" "$DST_DIR/First Run" 2>/dev/null || true
fi

# 复制 Last Version
if [ -f "$SRC_DIR/Last Version" ]; then
    cp -f "$SRC_DIR/Last Version" "$DST_DIR/Last Version" 2>/dev/null || true
fi

# 排除的目录（缓存、扩展等，占用空间大但不需要）
EXCLUDE_DIRS=(
    "Cache" "Code Cache" "GPUCache" "Service Worker"
    "extensions" "Extension Rules" "Extension State"
    "Extension Scripts" "Extension Settings"
    "IndexedDB" "Session Storage" "blob_storage"
    "File System" "Local Extension Settings"
    "Sync Extension Settings" "Platform Notifications"
    "databases" "Application Cache" "ShaderCache"
    "GrShaderCache" "Download Service" "OptimizationHints"
    "MEIPreload" "Hyphen" "DIPS" "BudgetDatabase"
    "Developer Tools" "Download" "InterventionPolicyDatabase"
    "ChromeDWriteFontCache" "FontCache"
)

# 使用 cp 复制整个 Default 目录，然后删除排除目录
echo "复制 Default 配置文件..."

# 先清理目标 Default 目录
rm -rf "$DST_DIR/Default" 2>/dev/null || true
mkdir -p "$DST_DIR/Default" 2>/dev/null || true

# 使用 cp -r 复制（比 rsync 更可靠，尤其是在 WSL 跨文件系统时）
cp -r "$SRC_DIR/Default/"* "$DST_DIR/Default/" 2>/dev/null || true
# 单独复制隐藏文件（如果有）
cp -r "$SRC_DIR/Default/".* "$DST_DIR/Default/" 2>/dev/null || true

CP_RESULT=$?
if [ $CP_RESULT -ne 0 ]; then
    echo "  ⚠️  部分文件复制失败（可能被 Chrome 锁定），继续..."
fi

# 删除排除的目录
for dir in "${EXCLUDE_DIRS[@]}"; do
    rm -rf "$DST_DIR/Default/$dir" 2>/dev/null || true
done

echo "  ✅ 配置文件复制完成，缓存目录已清理"

# 强制复制关键文件（确保登录状态，即使上面的 cp 可能因为文件锁定而失败）
echo "验证并强制复制关键登录文件..."

CRITICAL_FILES=(
    "Network/Cookies"
    "Network/Cookies-journal"
    "Login Data"
    "Login Data-journal"
    "Preferences"
    "Secure Preferences"
    "Web Data"
    "Web Data-journal"
    "Bookmarks"
    "Favicons"
    "Favicons-journal"
    "History"
    "History-journal"
    "Current Session"
    "Current Tabs"
    "Last Session"
    "Last Tabs"
    "Visited Links"
    "QuotaManager"
    "QuotaManager-journal"
)

MISSING_CRITICAL=0
for file in "${CRITICAL_FILES[@]}"; do
    SRC_FILE="$SRC_DIR/Default/$file"
    DST_FILE="$DST_DIR/Default/$file"
    
    if [ -f "$SRC_FILE" ]; then
        DST_PARENT=$(dirname "$DST_FILE")
        mkdir -p "$DST_PARENT" 2>/dev/null || true
        
        # 检查目标文件是否存在且大小相同
        if [ -f "$DST_FILE" ]; then
            SRC_SIZE=$(stat -c%s "$SRC_FILE" 2>/dev/null || echo "0")
            DST_SIZE=$(stat -c%s "$DST_FILE" 2>/dev/null || echo "0")
            if [ "$SRC_SIZE" = "$DST_SIZE" ]; then
                continue
            fi
        fi
        
        # 强制复制（如果文件被锁定，尝试多次）
        COPIED=false
        for attempt in 1 2 3; do
            if cp -f "$SRC_FILE" "$DST_FILE" 2>/dev/null; then
                # 验证复制结果
                if [ -f "$DST_FILE" ]; then
                    COPIED=true
                    break
                fi
            fi
            sleep 0.5
        done
        
        if [ "$COPIED" = true ]; then
            echo "  ✅ $file"
        else
            echo "  ❌ $file (复制失败，可能被 Chrome 锁定)"
            MISSING_CRITICAL=$((MISSING_CRITICAL + 1))
        fi
    fi
done

# 特别检查 Cookies 文件（最关键）
if [ ! -f "$DST_DIR/Default/Network/Cookies" ] || [ ! -s "$DST_DIR/Default/Network/Cookies" ]; then
    echo ""
    echo "  ⚠️  Cookies 文件缺失或为空！"
    echo "  这可能导致 Pinterest 无法保持登录状态"
    echo "  请确保 Windows Chrome 已关闭后重新运行此脚本"
    MISSING_CRITICAL=$((MISSING_CRITICAL + 1))
else
    COOKIES_SIZE=$(stat -c%s "$DST_DIR/Default/Network/Cookies" 2>/dev/null || echo "0")
    echo ""
    echo "  ✅ Cookies 文件已就绪 (${COOKIES_SIZE} bytes)"
fi

if [ $MISSING_CRITICAL -gt 0 ]; then
    echo ""
    echo "  ⚠️  $MISSING_CRITICAL 个关键文件缺失"
    echo "  建议: 关闭 Windows Chrome 后重新运行此脚本"
fi

# 清除锁文件
echo "清除锁文件..."
rm -f "$DST_DIR/SingletonLock" "$DST_DIR/SingletonSocket" "$DST_DIR/SingletonCookie" 2>/dev/null || true
rm -f "$DST_DIR/Default/SingletonLock" "$DST_DIR/Default/SingletonSocket" "$DST_DIR/Default/SingletonCookie" 2>/dev/null || true
rm -f "$DST_DIR/lockfile" "$DST_DIR/Default/lockfile" 2>/dev/null || true
rm -f "$DST_DIR/DevToolsActivePort" 2>/dev/null || true

echo ""
echo "=========================================="
echo "  ✅ 配置文件同步完成!"
echo "=========================================="
echo ""
echo "  调试配置目录: C:\temp\chrome-debug-profile"
echo ""
echo "📌 下一步:"
echo "  1. 在 Windows PowerShell 中运行:"
echo "     .\start_chrome_debug.ps1"
echo "     （或双击 start_chrome_debug.bat）"
echo ""
echo "  2. 或者从 WSL 中运行:"
echo "     ./sync_and_start.sh"
echo ""