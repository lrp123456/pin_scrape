#!/bin/bash
# 修复 Pinterest 登录状态
# 从 Windows Chrome 复制 Default 配置到调试目录
# 用法: sudo ./fix_login.sh [Windows用户名] [--docker]
#
# 默认: 复制到 C:\temp\chrome-debug-profile (用于 Windows Chrome 调试模式)
# --docker: 同时复制到 Docker 容器挂载目录 (用于 Docker 内 Chromium)

set -e

MODE="windows"
if [ "$2" = "--docker" ] || [ "$1" = "--docker" ]; then
    MODE="both"
    if [ "$1" = "--docker" ]; then
        shift
    fi
fi

echo "=========================================="
echo "修复 Pinterest 登录状态"
echo "模式: $MODE"
echo "=========================================="
echo ""

if [ "$EUID" -ne 0 ]; then
    echo "⚠️  需要 root 权限，正在使用 sudo 重新运行..."
    sudo "$0" "$@"
    exit $?
fi

WINDOWS_USER="${1:-}"
if [ -z "$WINDOWS_USER" ]; then
    WINDOWS_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n' | xargs)
    if [ -z "$WINDOWS_USER" ] || [ "$WINDOWS_USER" = "%USERNAME%" ]; then
        WINDOWS_USER=$(powershell.exe -Command "Write-Host \$env:USERNAME" 2>/dev/null | tr -d '\r\n' | xargs)
    fi
    if [ -z "$WINDOWS_USER" ]; then
        WINDOWS_USER=$(ls /mnt/c/Users/ 2>/dev/null | grep -v -E "^Public$|^Default$|^All Users|^Default User|^desktop.ini" | head -1)
    fi
fi

if [ -z "$WINDOWS_USER" ]; then
    echo "❌ 无法检测 Windows 用户名"
    echo "请手动指定: sudo ./fix_login.sh 你的用户名"
    ls -la /mnt/c/Users/ 2>/dev/null | grep -v "Public\|Default\|All Users"
    exit 1
fi

echo "Windows 用户名: $WINDOWS_USER"
echo ""

CHROME_SRC="/mnt/c/Users/$WINDOWS_USER/AppData/Local/Google/Chrome/User Data"

if [ ! -d "$CHROME_SRC/Default" ]; then
    echo "❌ Chrome 配置目录不存在"
    echo "路径: $CHROME_SRC/Default"
    echo ""
    echo "可用的用户目录:"
    ls /mnt/c/Users/
    exit 1
fi

COOKIES_FILE="$CHROME_SRC/Default/Network/Cookies"
if [ ! -f "$COOKIES_FILE" ]; then
    echo "⚠️  Cookies 文件不存在或无法访问"
    echo "请确保 Windows Chrome 已关闭后重试"
    echo ""
    read -p "是否继续? (y/n): " CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        exit 1
    fi
else
    echo "✅ 找到 Cookies 文件"
    ls -lh "$COOKIES_FILE"
fi
echo ""

# ==========================================
# 模式 1: 同步到 Windows 调试目录 (C:\temp\chrome-debug-profile)
# ==========================================
sync_to_windows() {
    local DST="/mnt/c/temp/chrome-debug-profile"
    
    echo "同步到 Windows 调试目录: C:\temp\chrome-debug-profile"
    echo ""
    
    mkdir -p "$DST/Default/Network" 2>/dev/null || true
    
    # 复制 Local State
    cp -f "$CHROME_SRC/Local State" "$DST/Local State" 2>/dev/null && echo "  ✅ Local State" || echo "  ⚠️  Local State (失败)"
    
    # 复制 First Run
    cp -f "$CHROME_SRC/First Run" "$DST/First Run" 2>/dev/null || true
    
    # 复制 Last Version
    cp -f "$CHROME_SRC/Last Version" "$DST/Last Version" 2>/dev/null || true
    
    # 复制 Default 配置关键文件
    local KEY_FILES=(
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
    
    for file in "${KEY_FILES[@]}"; do
        if [ -f "$CHROME_SRC/Default/$file" ]; then
            local TARGET_DIR="$DST/Default/$(dirname "$file")"
            mkdir -p "$TARGET_DIR" 2>/dev/null || true
            cp -f "$CHROME_SRC/Default/$file" "$DST/Default/$file" 2>/dev/null && echo "  ✅ Default/$file" || echo "  ⚠️  Default/$file (可能被锁定)"
        fi
    done
    
    # 清除锁文件
    rm -f "$DST/SingletonLock" "$DST/SingletonSocket" "$DST/SingletonCookie" 2>/dev/null || true
    rm -f "$DST/Default/SingletonLock" "$DST/Default/SingletonSocket" 2>/dev/null || true
    rm -f "$DST/lockfile" "$DST/Default/lockfile" 2>/dev/null || true
    rm -f "$DST/DevToolsActivePort" 2>/dev/null || true
    
    echo ""
    echo "  ✅ Windows 调试目录同步完成"
}

# ==========================================
# 模式 2: 同步到 Docker 容器目录
# ==========================================
sync_to_docker() {
    local DST="/home/lrp/n8n/data/chrome-profile"
    
    echo "同步到 Docker 容器目录: $DST"
    echo ""
    
    # 停止容器
    echo "停止 python-runner 容器..."
    cd /home/lrp/n8n && docker-compose stop python-runner 2>/dev/null || true
    echo ""
    
    # 备份
    local BACKUP_DIR="/home/lrp/n8n/data/chrome-profile-backup-$(date +%Y%m%d-%H%M%S)"
    if [ -d "$DST" ]; then
        cp -r "$DST" "$BACKUP_DIR" 2>/dev/null || true
        echo "备份位置: $BACKUP_DIR"
    fi
    
    # 清理
    rm -rf "$DST"/*
    mkdir -p "$DST/Default/Network"
    
    # 复制关键文件
    local KEY_FILES=(
        "Network/Cookies"
        "Network/Cookies-journal"
        "Login Data"
        "Login Data-journal"
        "Preferences"
        "Web Data"
        "Web Data-journal"
    )
    
    for file in "${KEY_FILES[@]}"; do
        if [ -f "$CHROME_SRC/Default/$file" ]; then
            local TARGET_DIR="$DST/Default/$(dirname "$file")"
            mkdir -p "$TARGET_DIR" 2>/dev/null || true
            cp -f "$CHROME_SRC/Default/$file" "$DST/Default/$file" 2>/dev/null && echo "  ✅ Default/$file" || echo "  ⚠️  Default/$file"
        fi
    done
    
    # 设置权限
    chmod -R 777 "$DST"
    
    echo ""
    echo "  ✅ Docker 容器目录同步完成"
    
    # 启动容器
    echo "启动 python-runner 容器..."
    docker-compose start python-runner 2>/dev/null || true
    sleep 5
}

# 执行同步
sync_to_windows

if [ "$MODE" = "both" ]; then
    echo ""
    echo "---"
    echo ""
    sync_to_docker
fi

echo ""
echo "=========================================="
echo "  ✅ 修复完成!"
echo "=========================================="
echo ""
echo "📌 下一步:"
echo "  1. 在 Windows 上运行 start_chrome_debug.ps1 启动调试模式"
echo "  2. 或从 WSL 运行: ./sync_and_start.sh"
echo ""
if [ "$MODE" = "both" ]; then
    echo "  Docker 容器内也可以使用: --auto-launch --chrome-profile /home/node/.chrome-profile"
fi
echo ""