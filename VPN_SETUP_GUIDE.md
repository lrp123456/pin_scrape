# Pinterest Scraper - VPN/代理配置指南

## 问题描述

Pinterest 在中国大陆无法直接访问，需要通过 VPN 才能正常爬取。本指南提供多种方案让 Docker 容器使用宿主机的 VPN 连接。

## 快速诊断

首先确认宿主机和容器的网络状况：

```bash
# 1. 检查宿主机能否访问 Pinterest（应该返回 200）
curl -s -o /dev/null -w "%{http_code}" https://pinterest.com

# 2. 检查容器能否访问 Pinterest（应该失败或返回非200）
docker exec n8n-python-runner python -c "import urllib.request; print(urllib.request.urlopen('https://pinterest.com').getcode())"

# 3. 检查宿主机VPN代理端口（常见端口: 7890, 10808, 10809）
curl -s --connect-timeout 3 -x "http://127.0.0.1:7890" http://httpbin.org/ip
```

## 解决方案

### 方案一：配置代理环境变量（推荐）

如果你的 VPN 提供 HTTP 代理（如 Clash、V2Ray、Shadowsocks 等），这是最简单的方案。

#### 步骤 1: 确定代理端口

常见 VPN 客户端的默认代理端口：

| VPN 客户端 | HTTP 代理端口 | SOCKS5 端口 |
|-----------|--------------|-------------|
| Clash | 7890 | 7891 |
| Clash Verge | 7890 | 7891 |
| v2rayN | 10808 | 10808 |
| Shadowsocks | 1080 | 1080 |

#### 步骤 2: 修改 docker-compose.yml

编辑 `/home/lrp/n8n/docker-compose.yml`，找到 `python-runner` 服务，添加代理环境变量：

```yaml
services:
  python-runner:
    # ... 其他配置 ...
    
    environment:
      - SCRIPTS_DIR=/home/node/scripts
      - RESULTS_DIR=/tmp/results
      # ... 其他环境变量 ...
      
      # ⭐ 添加代理配置（根据你的VPN端口修改）
      - HTTP_PROXY=http://192.168.1.1:7890
      - HTTPS_PROXY=http://192.168.1.1:7890
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis
```

> **注意**: `192.168.1.1` 是宿主机的网关IP，如果不行可以尝试 `host.docker.internal` 或直接查询宿主机IP。

#### 步骤 3: 重启容器

```bash
cd /home/lrp/n8n
docker-compose restart python-runner

# 等待容器启动
sleep 5

# 测试连接
docker exec n8n-python-runner python -c "import urllib.request; print(urllib.request.urlopen('https://pinterest.com').getcode())"
```

#### 自动配置脚本

我们也提供了自动配置脚本：

```bash
cd /home/lrp/n8n/docker/scripts/pinterest-scraper
./setup_vpn_proxy.sh
```

脚本会：
1. 自动检测常见VPN代理端口
2. 创建 `docker-compose.proxy.yml` 覆盖文件
3. 提供交互式配置选项

---

### 方案二：使用 Host 网络模式

让容器直接使用宿主机的网络栈，自动继承 VPN 连接。

#### 优点
- 配置简单，无需代理设置
- 自动使用宿主机所有网络连接

#### 缺点
- 失去 Docker 网络隔离
- 端口映射方式改变
- 可能与宿主机服务冲突

#### 配置方法

创建 `docker-compose.host.yml`：

```yaml
version: "3.8"

services:
  python-runner:
    network_mode: "host"
    # 使用host模式时，端口映射不需要了
    # 服务将直接使用宿主机端口5000
    
    environment:
      # host模式下需要使用localhost连接其他服务
      - REDIS_HOST=localhost
      - POSTGRES_HOST=localhost
```

使用：

```bash
cd /home/lrp/n8n
docker-compose -f docker-compose.yml -f docker-compose.host.yml up -d python-runner
```

---

### 方案三：使用 Docker 覆盖文件

为了不修改原始 `docker-compose.yml`，可以使用覆盖文件。

#### 创建覆盖文件

创建 `/home/lrp/n8n/docker-compose.proxy.yml`：

```yaml
# VPN代理配置覆盖文件
# 用法: docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d

services:
  python-runner:
    environment:
      - HTTP_PROXY=http://192.168.1.1:7890
      - HTTPS_PROXY=http://192.168.1.1:7890
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis

  n8n:
    environment:
      - HTTP_PROXY=http://192.168.1.1:7890
      - HTTPS_PROXY=http://192.168.1.1:7890
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis,python-runner
```

#### 使用覆盖文件启动

```bash
cd /home/lrp/n8n

# 使用覆盖文件启动
docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d

# 或者仅重启 python-runner
docker-compose -f docker-compose.yml -f docker-compose.proxy.yml up -d python-runner
```

---

### 方案四：通过环境文件配置

将代理配置放在单独的文件中，便于管理。

#### 创建代理配置文件

创建 `/home/lrp/n8n/proxy.env`：

```bash
HTTP_PROXY=http://192.168.1.1:7890
HTTPS_PROXY=http://192.168.1.1:7890
NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis
http_proxy=http://192.168.1.1:7890
https_proxy=http://192.168.1.1:7890
no_proxy=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis
```

#### 修改 docker-compose.yml

```yaml
services:
  python-runner:
    # ... 其他配置 ...
    env_file:
      - ./proxy.env
```

---

## Playwright 代理配置

即使配置了 Docker 代理，Playwright 可能需要额外配置才能使用代理。

### 修改 scraper.py

编辑 `scraper.py`，在 `start()` 方法中添加代理支持：

```python
def start(self):
    """启动浏览器"""
    self._playwright = sync_playwright().start()
    
    # 检查代理环境变量
    proxy_config = None
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    if http_proxy:
        # 解析代理地址
        proxy_config = {"server": http_proxy}
        print(f"使用代理: {http_proxy}")
    
    if self.cdp_endpoint:
        # 连接到已有浏览器（代理已在浏览器层面配置）
        # ... 现有代码 ...
    else:
        # 启动新的浏览器
        self._own_browser = True
        
        # 如果配置了代理，在启动时使用
        launch_options = {
            "headless": self.headless,
            "args": ['--disable-blink-features=AutomationControlled']
        }
        
        if proxy_config:
            launch_options["proxy"] = proxy_config
        
        self.browser = self._playwright.chromium.launch(**launch_options)
        # ... 其他代码 ...
```

### 更简单的方案：让 Chrome 使用系统代理

在 `chrome_launcher.py` 中添加代理参数：

```python
def _launch_chrome(self) -> subprocess.Popen:
    cmd = [
        self.chrome_path,
        f"--remote-debugging-port={self.port}",
        f"--user-data-dir={self.user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-translate",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--metrics-recording-only",
        "--disable-default-apps",
        "--no-sandbox",
        "--disable-setuid-sandbox",
    ]
    
    # ⭐ 添加代理配置
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    if http_proxy:
        cmd.extend([
            f"--proxy-server={http_proxy}",
            "--proxy-bypass-list=localhost,127.0.0.1"
        ])
    
    if self.headless:
        cmd.append("--headless")
    
    cmd.append("about:blank")
    
    # ... 启动进程 ...
```

---

## 验证配置

### 1. 验证环境变量

```bash
# 检查容器内的代理环境变量
docker exec n8n-python-runner env | grep -i proxy

# 应该显示:
# HTTP_PROXY=http://192.168.1.1:7890
# HTTPS_PROXY=http://192.168.1.1:7890
```

### 2. 验证网络连接

```bash
# 在容器内测试 Pinterest 访问
docker exec n8n-python-runner python3 << 'EOF'
import urllib.request
import ssl

# 禁用SSL验证（测试用）
ssl._create_default_https_context = ssl._create_unverified_context

try:
    response = urllib.request.urlopen('https://pinterest.com', timeout=10)
    print(f"✅ 连接成功! 状态码: {response.getcode()}")
except Exception as e:
    print(f"❌ 连接失败: {e}")
EOF
```

### 3. 运行 Pinterest 爬虫测试

```bash
cd /home/lrp/n8n/docker/scripts/pinterest-scraper
./run_in_docker.sh "test" 3
```

---

## 常见问题

### Q1: 配置了代理但还是无法访问？

**可能原因**：
1. 代理地址错误（不是 `127.0.0.1`，应该是宿主机 IP 或网关）
2. 代理端口错误
3. 代理仅支持 SOCKS5，不支持 HTTP

**排查步骤**：

```bash
# 1. 确认宿主机IP
ip route | grep default
# 默认网关通常是宿主机的IP

# 2. 在宿主机测试代理
curl -x "http://192.168.1.1:7890" https://pinterest.com -v

# 3. 在容器内测试代理
docker exec n8n-python-runner python3 -c "
import urllib.request
proxy = urllib.request.ProxyHandler({'https': 'http://192.168.1.1:7890'})
opener = urllib.request.build_opener(proxy)
response = opener.open('https://pinterest.com')
print(response.getcode())
"
```

### Q2: 使用 Clash，但不知道代理端口？

打开 Clash 客户端查看：
- 混合代理端口（Mixed Port）通常是 `7890`
- HTTP 代理端口通常是 `7890`
- SOCKS5 端口通常是 `7891`

### Q3: 如何让 Python requests 使用代理？

如果爬虫使用 requests 库，它会自动读取 `HTTP_PROXY` 环境变量。或者手动设置：

```python
import requests
import os

proxies = {
    'http': os.environ.get('HTTP_PROXY'),
    'https': os.environ.get('HTTPS_PROXY')
}

response = requests.get('https://pinterest.com', proxies=proxies)
```

### Q4: 如何让 Playwright 使用代理？

Playwright 支持代理参数：

```python
browser = playwright.chromium.launch(
    proxy={
        "server": "http://192.168.1.1:7890",
        "bypass": "localhost,127.0.0.1"
    }
)
```

### Q5: 不想让所有流量都走代理？

配置 `NO_PROXY` 环境变量：

```yaml
environment:
  - HTTP_PROXY=http://192.168.1.1:7890
  - HTTPS_PROXY=http://192.168.1.1:7890
  - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

---

## 推荐配置

对于 Pinterest Scraper，推荐使用**方案一**（代理环境变量）：

1. 简单，无需修改代码
2. 稳定，大多数 VPN 客户端都支持 HTTP 代理
3. 灵活，可以随时开启/关闭

### 一键配置

```bash
# 1. 进入项目目录
cd /home/lrp/n8n

# 2. 备份原配置
cp docker-compose.yml docker-compose.yml.backup

# 3. 编辑配置，添加代理（根据你的VPN端口修改）
cat >> docker-compose.yml << 'EOF'

  python-runner:
    environment:
      - HTTP_PROXY=http://192.168.1.1:7890
      - HTTPS_PROXY=http://192.168.1.1:7890
      - NO_PROXY=localhost,127.0.0.1,n8n-postgres,n8n-redis,postgres,redis
EOF

# 4. 重启容器
docker-compose restart python-runner

# 5. 测试
docker exec n8n-python-runner python3 -c "import urllib.request; print(urllib.request.urlopen('https://pinterest.com').getcode())"
```

---

## 总结

| 方案 | 难度 | 稳定性 | 适用场景 |
|------|------|--------|----------|
| 代理环境变量 | ⭐ 简单 | ⭐⭐⭐ 高 | 大多数 VPN 客户端 |
| Host 网络模式 | ⭐ 简单 | ⭐⭐ 中 | 简单快速，但牺牲隔离性 |
| VPN 容器 | ⭐⭐⭐ 复杂 | ⭐⭐⭐ 高 | 需要精细控制 |

**推荐**: 从方案一开始，如果不工作再尝试其他方案。
