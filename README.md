# Pinterest 搜索爬虫

一个基于 Playwright 的 Pinterest 搜索结果爬虫，支持按 save 数和评论数筛选图片，采用拟人化浏览模式降低反爬检测风险。

## 特性

- ✅ **拟人化浏览模式**：模拟真实用户行为，边滚动边点击查看，降低反爬检测风险
- ✅ **相似推荐探索**：自动点击相似推荐，扩展数据来源
- ✅ **Chrome 自动启动**：无需手动启动 Chrome，一键运行
- ✅ **VSCode 集成**：自动激活 conda 环境，开箱即用
- ✅ **智能去重**：自动去除重复 pin，保证数据唯一性

## 安装

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器（仅在使用非连接模式时需要）
playwright install chromium
```

## 使用方法

### 方式1: 自动启动 Chrome + 持久化登录（推荐）

自动启动 Chrome 并使用持久化配置（保留登录状态）：

```bash
# 首次使用：创建配置目录
mkdir -p ./data/chrome-profile

# 首次使用：手动登录（详见下方说明）
python main.py -q "test" -n 5 --connect --auto-launch \
  --chrome-profile ./data/chrome-profile --no-headless

# 在打开的浏览器中登录 Pinterest，登录后关闭浏览器

# 后续使用：自动使用已登录状态
python main.py -q "现代简约" -n 100 --connect --auto-launch \
  --chrome-profile ./data/chrome-profile
```

**首次登录说明：**
1. 使用 `--no-headless` 显示浏览器窗口
2. 在浏览器中访问 pinterest.com 并登录
3. 登录成功后关闭浏览器
4. 后续运行自动使用已保存的登录状态

### 方式2: 自动启动 Chrome（临时配置）

启动临时的 Chrome 实例（每次全新，无登录状态）：

```bash
python main.py -q "现代简约" -n 100 --connect --auto-launch
```

适合不需要登录的公开内容爬取。脚本结束后自动关闭 Chrome。

### 方式2: 连接到已有浏览器

如果需要使用已登录的 Pinterest 账号，可以连接到手动启动的 Chrome：

1. 关闭所有 Chrome 窗口

2. 以调试模式启动 Chrome：
   ```bash
   # Windows
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

   # Mac
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

   # Linux
   google-chrome --remote-debugging-port=9222
   ```

3. 在打开的 Chrome 中访问 Pinterest 并登录（可选但推荐）

4. 运行爬虫：
   ```bash
   python main.py -q "现代简约" -n 100 --connect
   ```

### 方式3: 自动启动浏览器

可能被 Pinterest 检测为机器人，不推荐使用。

```bash
# 基本用法
python main.py -q "cat" -n 100

# 带筛选条件
python main.py -q "dog" -n 200 --min-saves 50 --min-comments 10

# 显示浏览器窗口（调试用）
python main.py -q "cat" --no-headless --debug
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-q, --query` | 搜索关键词（必需） | - |
| `-n, --max-pins` | 最大爬取数量 | 100 |
| `--min-saves` | save 数筛选阈值 | 0 |
| `--min-likes` | 点赞数筛选阈值 | 0 |
| `--min-comments` | 评论数筛选阈值 | 0 |
| `-o, --output` | 输出目录 | ./output |
| `--no-headless` | 显示浏览器窗口 | 关闭 |
| `--debug` | 调试模式，保存截图和HTML | 关闭 |
| `--connect` | 连接到已有浏览器 (端口 9222) | 关闭 |
| `--auto-launch` | 自动启动 Chrome 调试实例（需配合 --connect） | 关闭 |
| `--chrome-profile` | Chrome 用户数据目录路径（持久化登录状态） | 临时目录 |
| `--cdp-endpoint` | Chrome DevTools Protocol 端点 | http://localhost:9222 |

## 输出文件

```
output/
├── data.json           # 所有爬取的 Pin 数据（包含主 pin 和相似推荐）
├── filtered_data.json  # 筛选后的 Pin 数据
└── images/             # 下载的图片
    ├── 123456789.jpg
    └── ...
```

## JSON 数据格式

```json
{
  "query": "现代简约",
  "total_pins": 150,
  "main_pins": 100,
  "similar_pins": 50,
  "filtered_pins": 25,
  "timestamp": "2026-04-16T08:00:00",
  "pins": [
    {
      "id": "123456789",
      "title": "现代简约客厅设计",
      "description": "简约风格的客厅装修",
      "image_url": "https://i.pinimg.com/originals/...",
      "image_url_736x": "https://i.pinimg.com/736x/...",
      "saves": 1234,
      "likes": 56,
      "comments": 10,
      "link": "https://...",
      "pinner": "username",
      "source": "main"
    },
    {
      "id": "987654321",
      "title": "简约卧室设计",
      "description": "温馨的卧室",
      "image_url": "https://i.pinimg.com/originals/...",
      "image_url_736x": "https://i.pinimg.com/736x/...",
      "saves": 567,
      "likes": 23,
      "comments": 5,
      "link": "https://...",
      "pinner": "user2",
      "source": "similar_from_123456789"
    }
  ]
}
```

**字段说明：**
- `source`: Pin 来源
  - `"main"`: 主搜索结果
  - `"similar_from_{pin_id}"`: 来自指定 pin 的相似推荐

## 拟人化浏览模式说明

爬虫采用拟人化浏览策略，模拟真实用户行为：

### 浏览行为
- 滚动过程中随机点击 15-25% 的 pin 查看详情
- 查看 pin 时模拟 3-15 秒的阅读时间
- 自动探索相似推荐，扩展数据来源

### 相似推荐策略
- **前 20 个主 pin**：每个探索 3-5 个相似推荐
- **后续主 pin**：每个探索 1-2 个相似推荐
- 自动去重，避免重复收集相同 pin

### 优势
- 降低反爬检测风险
- 获得更丰富的相关内容
- 数据质量更高（包含详细互动数据）

## Docker 部署（n8n 工作流集成）

如果你的场景是在 Docker 容器中运行（例如 n8n 工作流），请参考详细部署指南：

📚 **[Docker 部署指南](DOCKER_DEPLOYMENT.md)**

关键要点：
- 使用 `--chrome-profile` 参数指定持久化目录
- 首次通过 VNC 或复制配置文件完成登录
- 登录状态保存在 Docker volume 中，容器重启不丢失
- 脚本自动检测登录需求并提供清晰的解决指导

### 快速示例（Docker）

```bash
# 1. 修改 docker-compose.yml 添加 volume
volumes:
  - ./data/chrome-profile:/home/node/.chrome-profile

# 2. 首次登录（通过 VNC 或复制宿主机配置）

# 3. 在 n8n 中调用
python main.py -q "现代简约" -n 100 --connect --auto-launch \
  --chrome-profile /home/node/.chrome-profile
```

## VSCode 开发环境配置

项目已配置 VSCode 工作区设置，自动激活 `scraper` conda 环境：

1. 打开 VSCode：`code .`
2. 打开终端（Ctrl+`），自动显示 `(scraper)` 前缀
3. 按 F5 启动调试，自动使用 scraper 环境

**配置文件位置：**
- `.vscode/settings.json` - Python 解释器设置
- `.vscode/launch.json` - 调试配置
- `.vscode/extensions.json` - 推荐扩展

## 注意事项

- Pinterest 有严格的反爬机制，推荐使用 `--connect --auto-launch` 模式
- 使用连接模式时，建议先在浏览器中登录 Pinterest
- 请合理设置爬取数量和频率，避免被封禁
- 仅支持图片下载，不支持视频
- 相似推荐不计入 `-n` 参数指定的数量，实际收集数量会更多
