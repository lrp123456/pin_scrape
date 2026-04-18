# Pinterest Scraper - 宿主机测试脚本

以下是用于在宿主机测试 Pinterest Scraper 的脚本集合。

## 脚本列表

### 1. 安装和环境检查

| 脚本 | 用途 |
|------|------|
| `install.sh` | 一键安装依赖和 Chromium |
| `check_env.sh` | 检查宿主机环境是否配置正确 |

### 2. 本地测试（宿主机直接运行）

| 脚本 | 用途 | 示例 |
|------|------|------|
| `test_local.sh` | 快速测试（无头模式） | `./test_local.sh "现代简约" 5` |
| `test_visual.sh` | 可视化测试（带浏览器窗口） | `./test_visual.sh "cat"` |
| `test_connect.sh` | 连接已有 Chrome 测试 | `./test_connect.sh "dog"` |
| `run_local.sh` | 完整爬取 | `./run_local.sh "现代简约" 50 10` |

### 3. Docker 测试

| 脚本 | 用途 | 示例 |
|------|------|------|
| `test_docker.sh` | Docker 环境测试 | `./test_docker.sh "现代简约" 5` |
| `diagnose.sh` | Docker 环境诊断 | `./diagnose.sh` |

## 使用流程

### 方式一：宿主机直接运行（推荐开发和调试）

```bash
# 1. 进入脚本目录
cd /path/to/pinterest-scraper

# 2. 安装依赖
./install.sh

# 3. 检查环境
./check_env.sh

# 4. 运行测试
./test_local.sh "现代简约" 5
```

### 方式二：Docker 运行（推荐生产环境）

```bash
# 1. 确保 Docker 容器在运行
cd /home/lrp/n8n
docker-compose up -d python-runner

# 2. 运行 Docker 测试
cd docker/scripts/pinterest-scraper
./test_docker.sh "现代简约" 5
```

## 脚本详细说明

### install.sh
一键安装脚本，会：
- 检查 Python 环境
- 安装 Python 依赖（playwright, aiohttp）
- 安装 Playwright Chromium
- 创建必要的目录
- 运行环境检查

### check_env.sh
环境检查脚本，检查项：
- Python 3.x 是否安装
- pip3 是否可用
- Playwright 是否安装
- aiohttp 是否安装
- Chromium/Chrome 是否安装
- 脚本文件是否完整
- Chrome 配置目录是否存在
- 输出目录是否可写

### test_local.sh [关键词] [数量]
快速本地测试：
- 默认关键词："现代简约"
- 默认数量：5
- 模式：无头模式（不显示浏览器窗口）
- 输出：保存在 `output/test_YYYYMMDD_HHMMSS/`

### test_visual.sh [关键词]
可视化测试：
- 显示浏览器窗口
- 可以看到爬取过程
- 需要桌面环境（DISPLAY 变量）
- 适合调试和理解爬取逻辑

### test_connect.sh [关键词]
连接已有 Chrome 测试：
- 连接到手动启动的 Chrome（端口 9222）
- 适合已经登录 Pinterest 的情况
- 需要先启动 Chrome：
  ```bash
  google-chrome --remote-debugging-port=9222
  ```

### run_local.sh [关键词] [数量] [最小saves]
完整爬取脚本：
- 自动检测 Chrome 配置
- 支持筛选条件
- 保存完整结果
- 示例：`./run_local.sh "现代简约" 50 10`
  - 关键词："现代简约"
  - 数量：50
  - 最小 saves：10

### test_docker.sh [关键词] [数量]
Docker 环境测试：
- 自动检查容器状态
- 如果容器未运行会自动启动
- 在容器内执行测试

### diagnose.sh
Docker 环境诊断：
- 检查容器状态
- 检查脚本路径
- 检查 Chrome 配置
- 检查 Chromium 安装
- 检查网络连接
- 检查输出目录
- 检查 Python 依赖

## 常见问题

### Q: 安装依赖失败？
```bash
# 手动安装
pip3 install playwright aiohttp
playwright install chromium
```

### Q: 找不到 Chrome？
```bash
# 安装系统 Chromium（Ubuntu/Debian）
sudo apt-get update
sudo apt-get install -y chromium-browser

# 或使用 Playwright 安装的 Chromium
playwright install chromium
```

### Q: 权限问题？
```bash
# 设置脚本权限
chmod +x *.sh

# 设置输出目录权限
chmod -R 777 output/
```

### Q: 需要登录 Pinterest？
参考 `CHROME_PROFILE_SETUP.md` 配置 Chrome 登录状态。

## 目录结构

```
pinterest-scraper/
├── main.py                 # 主程序
├── scraper.py             # 爬虫逻辑
├── chrome_launcher.py     # Chrome 启动器
├── downloader.py          # 图片下载器
├── output.py              # 输出处理
├── models.py              # 数据模型
├── requirements.txt       # Python 依赖
├── install.sh             # 安装脚本 ⭐
├── check_env.sh           # 环境检查 ⭐
├── test_local.sh          # 本地测试 ⭐
├── test_visual.sh         # 可视化测试 ⭐
├── test_connect.sh        # 连接测试 ⭐
├── run_local.sh           # 完整运行 ⭐
├── test_docker.sh         # Docker 测试 ⭐
├── diagnose.sh            # 诊断脚本
├── data/                  # 数据目录
│   └── chrome-profile/    # Chrome 配置
└── output/                # 输出目录
```

## 提示

1. **首次使用**：先运行 `./install.sh` 和 `./check_env.sh`
2. **快速验证**：使用 `./test_local.sh` 进行快速测试
3. **调试问题**：使用 `./test_visual.sh` 查看浏览器行为
4. **生产环境**：使用 `./test_docker.sh` 或 `./run_in_docker.sh`

