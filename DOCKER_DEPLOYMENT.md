# Pinterest Scraper - Docker 部署指南

## 概述

本指南说明如何在 n8n 的 Docker 容器中使用 Pinterest 爬虫，重点解决登录状态持久化问题。

## 架构说明

```
┌─────────────────────────────────────────┐
│  n8n 工作流                              │
│  └─ HTTP Request → Python Runner        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Python Runner 容器 (n8n-python-runner) │
│  ├─ Playwright Chromium                 │
│  ├─ Chrome 用户配置 (持久化)             │
│  └─ Pinterest Scraper                   │
└─────────────────────────────────────────┘
                    ↓
        挂载到宿主机 ./data/chrome-profile
```

## 快速开始

### 步骤 1：修改 docker-compose.yml

在 `python-runner` 服务的 `volumes` 部分添加 Chrome 配置目录：

```yaml
services:
  python-runner:
    # ... 其他配置 ...
    volumes:
      # ... 现有 volumes ...

      # ⭐ 添加 Chrome 配置持久化
      - ./data/chrome-profile:/home/node/.chrome-profile
```

重启容器使配置生效：

```bash
docker-compose down
docker-compose up -d python-runner
```

### 步骤 2：首次登录 Pinterest

由于容器是 headless 环境，需要通过以下方式之一进行首次登录：

#### 方案 A：通过 VNC 远程桌面登录（推荐）

1. **安装 VNC 服务器（在容器中）**

修改 `Dockerfile.python`，在 `apt-get install` 部分添加：

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
      # ... 现有依赖 ...
      x11vnc \
      xvfb \
      fluxbox \
      && apt-get clean
```

重新构建镜像：

```bash
docker-compose build python-runner
docker-compose up -d python-runner
```

2. **启动虚拟显示和 VNC**

进入容器：

```bash
docker exec -it n8n-python-runner bash
```

运行以下命令：

```bash
# 创建虚拟显示
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# 启动窗口管理器
fluxbox -display :99 &

# 启动 VNC 服务器（密码: pinterest）
x11vnc -display :99 -forever -shared -rfbauth ~/.vnc/passwd

# 如果没有密码文件，先创建：
mkdir -p ~/.vnc
x11vnc -storepasswd pinterest ~/.vnc/passwd
x11vnc -display :99 -forever -shared -rfbauth ~/.vnc/passwd
```

3. **通过 VNC 客户端连接**

使用 VNC 客户端（如 RealVNC、TightVNC）连接到：
```
host.docker.internal:5900
或
localhost:5900
```

4. **在 VNC 中启动 Chrome 并登录**

在容器的 VNC 终端中运行：

```bash
google-chrome \
  --user-data-dir=/home/node/.chrome-profile \
  --remote-debugging-port=9222 \
  --no-sandbox \
  --disable-setuid-sandbox
```

在打开的 Chrome 中：
1. 访问 https://pinterest.com
2. 点击登录
3. 使用 Google 账号或邮箱登录
4. 登录成功后关闭 Chrome

5. **验证登录状态**

```bash
ls -la /home/node/.chrome-profile/Default/
# 应该看到 Cookies、Login Data 等文件
```

#### 方案 B：从宿主机复制 Chrome 配置（更简单）

如果你在宿主机上已有登录 Pinterest 的 Chrome：

1. **在宿主机找到 Chrome 配置**

Windows:
```
C:\Users\{你的用户名}\AppData\Local\Google\Chrome\User Data
```

Linux:
```
~/.config/google-chrome/Default
```

2. **复制到 Docker volume**

```bash
# 创建目标目录
mkdir -p ./data/chrome-profile

# 复制配置（以 Windows 为例）
# 注意：只复制 Default 文件夹中的关键文件
cp -r "/c/Users/{你的用户名}/AppData/Local/Google/Chrome/User Data/Default/Cookies" ./data/chrome-profile/
cp -r "/c/Users/{你的用户名}/AppData/Local/Google/Chrome/User Data/Default/Login Data" ./data/chrome-profile/
cp -r "/c/Users/{你的用户名}/AppData/Local/Google/Chrome/User Data/Default/Cookies-journal" ./data/chrome-profile/
```

3. **设置权限**

```bash
# 确保容器内的 node 用户可以访问
chmod -R 777 ./data/chrome-profile
```

#### 方案 C：使用 Playwright 的 browser_context（编程方式）

如果你的 Pinterest 账号允许，可以通过脚本注入 cookies：

创建 `pinterest_login_helper.py`：

```python
"""Pinterest 登录辅助脚本"""
from playwright.sync_api import sync_playwright
import json
import os

def manual_login_and_save_state():
    """
    手动登录 Pinterest 并保存状态
    运行此脚本时需要显示浏览器（非 headless）
    """
    profile_dir = "/home/node/.chrome-profile"

    with sync_playwright() as p:
        # 启动浏览器（显示窗口）
        browser = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,  # 显示浏览器
            args=['--disable-blink-features=AutomationControlled']
        )

        page = browser.new_page()
        page.goto('https://pinterest.com')

        print("\n" + "="*60)
        print("请在打开的浏览器中手动登录 Pinterest")
        print("登录成功后，按回车键继续...")
        print("="*60)
        input()

        # 保存 cookies
        cookies = page.context.cookies()
        with open(f"{profile_dir}/cookies.json", 'w') as f:
            json.dump(cookies, f)

        print(f"\n✅ 登录状态已保存到: {profile_dir}")
        print("现在可以在 headless 模式下使用爬虫了")

        browser.close()

if __name__ == '__main__':
    manual_login_and_save_state()
```

在容器外运行（需要 X11 转发或 VNC）：

```bash
# 在宿主机上运行（需要 GUI）
docker exec -it n8n-python-runner python /home/node/scripts/pinterest_login_helper.py
```

### 步骤 3：在 n8n 工作流中使用

#### 配置参数

在 n8n 的 Python Runner 节点中传入参数：

```json
{
  "script": "pinterest_scraper.py",
  "args": {
    "query": "现代简约",
    "max_pins": 100,
    "connect": true,
    "auto_launch": true,
    "chrome_profile": "/home/node/.chrome-profile",
    "output": "/tmp/results"
  }
}
```

#### 完整示例

在 n8n 工作流中添加 **HTTP Request** 节点：

```json
{
  "method": "POST",
  "url": "http://python-runner:5000/execute",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": {
    "script": "pinterest_scraper.py",
    "args": {
      "query": "现代简约",
      "max_pins": 100,
      "connect": true,
      "auto_launch": true,
      "chrome_profile": "/home/node/.chrome-profile",
      "output": "/tmp/results/pinterest"
    }
  }
}
```

## 常见问题

### Q1: 登录状态丢失怎么办？

**A:** 检查以下几点：

1. **volume 是否正确挂载**

```bash
docker exec n8n-python-runner ls -la /home/node/.chrome-profile/
# 应该看到 Default 目录或 cookies.json
```

2. **权限是否正确**

```bash
docker exec n8n-python-runner chmod -R 777 /home/node/.chrome-profile
```

3. **Chrome 进程是否正常退出**

确保上次脚本运行结束后 Chrome 正常关闭，没有残留进程。

### Q2: 仍然被检测为机器人怎么办？

**A:** Pinterest 的反爬检测非常严格，建议：

1. **使用真实浏览器配置**（如方案 B 所示）
2. **降低爬取频率**：
   ```python
   # 在 scraper.py 中增加延迟
   wait_time = random.uniform(8, 15)  # 从 4-8 秒增加到 8-15 秒
   ```

3. **使用代理**：
   在 Chrome 启动参数中添加代理：
   ```python
   # 在 chrome_launcher.py 的 _launch_chrome 方法中添加
   cmd.extend(['--proxy-server=http://your-proxy:port'])
   ```

4. **使用无头模式更隐蔽的参数**：
   ```python
   args=[
       '--disable-blink-features=AutomationControlled',
       '--disable-dev-shm-usage',
       '--no-sandbox',
       '--disable-setuid-sandbox',
       '--disable-web-security',
       '--disable-features=IsolateOrigins,site-per-process'
   ]
   ```

### Q3: 如何在脚本中检测登录是否成功？

**A:** 脚本已内置登录检测。如果检测到需要登录，会抛出异常并提供详细的解决方案提示。

### Q4: 能否使用 Google 账号自动登录？

**A:** 不建议。原因：

1. Google 登录需要人工验证（验证码、2FA）
2. 自动化登录违反 Google 服务条款
3. 容易触发安全警告导致账号被锁定

**最佳实践：** 手动登录一次，然后持久化配置。

### Q5: 多个 Pinterest 账号如何管理？

**A:** 使用不同的配置目录：

```bash
# 账号 1
--chrome-profile /home/node/.chrome-profile-account1

# 账号 2
--chrome-profile /home/node/.chrome-profile-account2
```

在 docker-compose.yml 中添加多个 volume：

```yaml
volumes:
  - ./data/chrome-profile-1:/home/node/.chrome-profile-account1
  - ./data/chrome-profile-2:/home/node/.chrome-profile-account2
```

## 生产环境建议

### 1. 定期备份配置

```bash
# 创建备份脚本
tar -czf chrome-profile-backup-$(date +%Y%m%d).tar.gz ./data/chrome-profile
```

### 2. 监控登录状态

在脚本中添加检测逻辑（已实现）：

```python
# 检测是否需要登录
if login_required:
    # 发送通知到 n8n
    # 例如通过 webhook 触发告警
```

### 3. 使用环境变量管理配置路径

在 docker-compose.yml 中：

```yaml
environment:
  - CHROME_PROFILE_PATH=/home/node/.chrome-profile
```

在 Python 脚本中：

```python
import os
profile_path = os.getenv('CHROME_PROFILE_PATH', '/home/node/.chrome-profile')
```

### 4. 限制并发请求

避免同时运行多个爬虫实例：

```python
# 在脚本开始时检查
import os
lock_file = '/tmp/pinterest_scraper.lock'
if os.path.exists(lock_file):
    raise RuntimeError("另一个爬虫实例正在运行")

with open(lock_file, 'w') as f:
    f.write(str(os.getpid()))

try:
    # 运行爬虫
    pass
finally:
    os.remove(lock_file)
```

## 总结

通过持久化 Chrome 用户配置目录，可以在 Docker 容器中保存 Pinterest 登录状态，实现自动化爬取。关键要点：

✅ 使用 `--chrome-profile` 参数指定持久化目录
✅ 首次使用时手动登录（通过 VNC 或复制宿主机配置）
✅ 后续运行自动使用已登录状态
✅ 登录状态保存在 Docker volume 中，容器重启不丢失

遇到问题时，脚本会提供清晰的错误提示和解决方案指导。
