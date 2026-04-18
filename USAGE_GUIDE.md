# Pinterest 爬虫 - 使用指南

## 背景

Pinterest 会检测自动化浏览器（headless、CDP 连接等），直接启动的 Chromium 会被拦截。解决方案是连接到你已登录 Pinterest 的 Windows Chrome 浏览器。

但 Chrome 136+ **禁止在默认 User Data 目录启用远程调试**，且已运行的 Chrome 会通过 SingletonLock 阻止新实例开启调试端口。所以需要将配置复制到非标准目录 `C:\temp\chrome-debug-profile`，再从该目录启动调试实例。

## 快速开始

### 第一步：启动 Chrome 调试模式

选择以下任一方式：

#### 方式 A：从 WSL 一键启动（推荐）

```bash
cd ~/n8n/docker/scripts/pinterest-scraper
./sync_and_start.sh
```

这会自动：同步配置 → 关闭 Chrome → 清锁 → 启动调试 Chrome → 验证端口

#### 方式 B：Windows 双击启动

1. 在 Windows 资源管理器中打开 `\\wsl$\Ubuntu\home\lrp\n8n\docker\scripts\pinterest-scraper\`
2. 双击 `start_chrome_debug.bat`

#### 方式 C：Windows PowerShell 手动启动

```powershell
cd \\wsl$\Ubuntu\home\lrp\n8n\docker\scripts\pinterest-scraper
.\start_chrome_debug.ps1
```

参数选项：
- `-SkipCopy` 跳过配置复制，直接用已有的调试配置启动
- `-Port 9223` 使用其他调试端口

### 第二步：确认 Chrome 调试就绪

看到以下输出表示成功：

```
✅ Chrome 调试模式已就绪!
  Chrome 版本: Chrome/xxx
  WSL CDP:     http://localhost:9222
  Docker CDP:  http://host.docker.internal:9222
```

手动验证：
```bash
curl http://localhost:9222/json/version
```

### 第三步：运行爬虫

```bash
cd ~/n8n/docker/scripts/pinterest-scraper
./run_with_windows_chrome.sh "搜索关键词" 数量 最小saves
```

示例：
```bash
./run_with_windows_chrome.sh "现代简约" 50 100
```

或直接通过 API：

```bash
curl -X POST http://localhost:5000/run/pinterest_scraper_n8n.py \
  -H "Content-Type: application/json" \
  -d '{
    "args": [
      "--query", "现代简约",
      "--max-pins", "50",
      "--min-saves", "100",
      "--connect",
      "--cdp-endpoint", "http://localhost:9222"
    ]
  }'
```

## 各脚本说明

| 脚本 | 位置 | 运行位置 | 用途 |
|------|------|----------|------|
| `start_chrome_debug.ps1` | pinterest-scraper/ | Windows | 关闭Chrome → 复制配置 → 清锁 → 启动调试 |
| `start_chrome_debug.bat` | pinterest-scraper/ | Windows | 双击启动 ps1 的快捷方式 |
| `sync_profile_from_wsl.sh` | pinterest-scraper/ | WSL | 只同步配置到 `C:\temp\chrome-debug-profile`，不启动Chrome |
| `sync_and_start.sh` | pinterest-scraper/ | WSL | 同步配置 + 启动 Chrome 调试（一键脚本） |
| `run_with_windows_chrome.sh` | pinterest-scraper/ | WSL | 自动检测CDP端口并运行爬虫 |
| `fix_login.sh` | pinterest-scraper/ | WSL | 刷新Pinterest登录状态（从Windows复制cookies） |

## 刷新登录状态

如果爬虫提示需要登录，说明 cookies 过期了：

```bash
# 先关闭 Chrome 浏览器，然后：
sudo ./fix_login.sh          # 只刷新 Windows 调试配置
sudo ./fix_login.sh --docker # 同时刷新 Docker 容器内配置

# 刷新后重新启动 Chrome 调试
./sync_and_start.sh
```

## n8n 工作流

### 网络配置

python-runner 使用 **host 网络模式**，可以直接访问 `localhost:9222`。这已在 `docker-compose.yml` 中配置。

如果需要切换回桥接网络，需要同时运行 TCP 转发器（见下方"网络架构"部分）。

### 在 n8n 中使用

工作流会自动检测 Chrome CDP 端点（`localhost:9222`）。

导入最新工作流：

```
pinterest-scraper/n8n_workflow_windows_chrome.json
```

或通过 Execute Command 节点调用：

```bash
python3 /home/node/scripts/pinterest_scraper_n8n.py --query "关键词" --max-pins 50 --min-saves 100 --connect --cdp-endpoint http://localhost:9222
```

### 网络架构

```
Windows Chrome (127.0.0.1:9222)
        ↓
WSL (localhost:9222, 需加 --noproxy '*' 避免 VPN 代理)
        ↓
Docker python-runner (host 网络模式, localhost:9222 直连)
```

之前尝试过的方案和问题：
- ❌ `--remote-debugging-address=0.0.0.0` — Chrome 136+ 忽略此参数
- ❌ `netsh portproxy` + 桥接网络 — Chrome 拒绝非 localhost 的 Host 头
- ❌ TCP 转发器 + 桥接网络 — WebSocket 升级请求被代理截断
- ✅ **host 网络模式** — 容器直接访问 localhost:9222，所有问题解决

## 常见问题

### Chrome 调试端口连不上

```bash
# 1. 检查端口（WSL 有代理时必须加 --noproxy）
curl --noproxy '*' http://localhost:9222/json/version

# 2. 如果上面有响应但 curl 不加 --noproxy 就超时
#    说明 WSL 的 HTTP 代理拦截了请求
#    所有脚本已自动处理此问题

# 3. 检查 Chrome 是否带调试参数启动
#    在 Chrome 地址栏输入:
chrome://version
#    确认命令行参数中有 --remote-debugging-port=9222

# 4. 如果没有，重新运行启动脚本
./sync_and_start.sh
```

**WSL 代理注意事项**：如果 WSL 配置了 `http_proxy`/`https_proxy`，`curl` 会通过代理访问，导致 CDP 端点返回 502。所有脚本已自动加 `--noproxy '*'`，手动测试时也需要加。

### 脚本报错 "无法关闭 Chrome"

1. 打开 Windows 任务管理器
2. 结束所有 `Google Chrome` 进程
3. 重新运行脚本

### Pinterest 检测到机器人

调试 Chrome 打开后，手动操作一下：
1. 在调试 Chrome 中访问 `https://www.pinterest.com`
2. 确认已登录（如果未登录，手动登录）
3. 浏览几个页面
4. 再运行爬虫

### Cookies 复制失败

Chrome 运行时某些文件会被锁定。解决方法：
1. **先关闭 Chrome**，再运行 `sync_and_start.sh` 或 `fix_login.sh`
2. 如果无法关闭，用 `start_chrome_debug.ps1`（会自动关闭并复制）

### Docker 容器连不上 Chrome

确认容器使用 host 网络模式：
```bash
docker inspect n8n-python-runner | grep NetworkMode
# 应该显示 "host"
```

如果不是：
```bash
cd ~/n8n
docker-compose -f docker-compose.wsl-vpn.yml up -d python-runner
```

### 日常 Chrome 和调试 Chrome 能同时用吗？

可以。调试 Chrome 使用 `C:\temp\chrome-debug-profile` 独立配置，不影响日常 Chrome 的 `User Data` 目录。但启动调试实例时需要先短暂关闭日常 Chrome（为了复制配置和清除锁文件）。

## 完整操作流程

```
1. 关闭日常 Chrome（或让脚本自动关闭）
2. 运行 ./sync_and_start.sh（同步配置 + 启动调试Chrome）
3. 等待 ✅ Chrome 调试模式已就绪
4. （可选）在调试Chrome中手动登录 Pinterest
5. 运行 ./run_with_windows_chrome.sh 或通过 n8n 调用
6. 使用完毕后，关闭调试 Chrome 窗口即可
7. 下次需要刷新登录状态时运行 sudo ./fix_login.sh
```