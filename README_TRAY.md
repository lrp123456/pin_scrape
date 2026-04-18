# Pinterest Scraper 托盘应用

Pinterest图片爬虫的Windows托盘应用版本，提供图形化界面和自动化管理功能。

## 功能特性

- ✅ 系统托盘图标，右键菜单控制
- ✅ 自动启动/停止API服务
- ✅ 实时任务进度显示
- ✅ Chrome自动管理（按需启动，自动关闭）
- ✅ 配置文件管理
- ✅ 开机自启支持
- ✅ 打包为独立EXE文件

## 快速开始

### 开发环境运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装Playwright浏览器
playwright install chromium

# 3. 运行API服务（调试）
python api_service_enhanced/service_main.py

# 4. 运行托盘应用（另一个终端）
python tray_app/tray_main.py
```

### 生产环境打包

```bash
# 1. 进入build目录
cd build

# 2. 运行打包脚本
build_all.bat

# 3. 查看输出
# dist/tray_app.exe - 托盘应用
# dist/api_service.exe - API服务
```

## 使用方法

### 1. 启动托盘应用

双击 `dist/tray_app.exe`，系统托盘会显示Pinterest Scraper图标。

### 2. 右键菜单功能

| 菜单项 | 功能 |
|--------|------|
| 服务状态 | 显示当前服务状态和任务进度 |
| 启动服务 | 启动API服务进程 |
| 停止服务 | 停止API服务进程 |
| 重启服务 | 重启API服务进程 |
| 打开API文档 | 在浏览器中打开Swagger文档 (http://localhost:8000/docs) |
| 打开输出目录 | 打开爬取结果保存目录 |
| 查看日志 | 用记事本打开日志文件 |
| 配置设置 | 编辑配置文件 |
| 开机自启 | 设置开机自动启动 |
| 退出 | 关闭托盘应用 |

### 3. API接口调用

#### 爬取Pinterest图片

```bash
# 同步爬取（阻塞）
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "query": "简约风格",
    "max_pins": 50,
    "min_saves": 100
  }'

# 异步爬取（后台运行）
curl -X POST http://localhost:8000/api/scrape/async \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cat",
    "max_pins": 100
  }'
```

#### 查询进度

```bash
# 获取当前任务进度
curl http://localhost:8000/api/progress

# 返回示例
{
  "running": true,
  "stage": "collecting",
  "percentage": 45,
  "current": 45,
  "total": 100,
  "query": "cat",
  "message": "已收集 45/100 个Pin"
}
```

#### 配置管理

```bash
# 获取配置
curl http://localhost:8000/api/config

# 更新配置
curl -X POST http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "api_port": 8000,
    "output_dir": "C:\\PinterestOutput",
    "chrome_headless": false
  }'
```

## 配置文件

配置文件位置：`%APPDATA%\PinterestScraper\config.json`

```json
{
  "api_port": 8000,
  "output_dir": "C:\\Users\\王\\PinterestScraper\\output",
  "chrome_port": 9222,
  "chrome_headless": false,
  "chrome_profile": "",
  "default_query": "",
  "default_max_pins": 100,
  "default_min_saves": 0,
  "default_min_likes": 0,
  "default_min_comments": 0,
  "auto_start": false
}
```

## 架构设计

```
┌─────────────────┐
│  tray_app.exe   │ ← 托盘应用（主进程）
│  (用户交互)     │
└────────┬────────┘
         │ 启动/停止/监控
         ↓
┌─────────────────┐
│ api_service.exe │ ← API服务（子进程）
│  (FastAPI)      │
└────────┬────────┘
         │ 按需启动
         ↓
┌─────────────────┐
│  Chrome进程     │ ← 爬虫执行
│  (调试模式)     │
└─────────────────┘
```

**关键特性：**
- 双进程架构：托盘应用和API服务分离，提高稳定性
- Chrome自动管理：首次爬虫请求时启动Chrome，空闲5分钟后自动关闭
- 进度追踪：通过HTTP接口实时查询任务进度
- 配置持久化：所有配置保存在用户数据目录

## 项目结构

```
pinterest-scraper/
├── tray_app/                    # 托盘应用模块
│   ├── tray_main.py            # 入口
│   ├── tray_icon.py            # 托盘图标和菜单
│   ├── process_manager.py      # 进程管理
│   ├── config_manager.py       # 配置管理
│   └── assets/                 # 图标资源
│
├── api_service_enhanced/        # API服务模块
│   ├── service_main.py         # 服务入口
│   ├── progress_tracker.py     # 进度追踪
│   ├── chrome_manager.py       # Chrome管理
│   ├── task_manager.py         # 任务管理
│   └── routes/                 # API路由
│       ├── scrape.py
│       ├── status.py
│       └── config.py
│
├── shared/                      # 共享模块
│   ├── models.py               # 数据模型
│   ├── progress_state.py       # 进度状态
│   └── config_schema.py        # 配置结构
│
├── chrome_launcher.py          # Chrome启动器
├── scraper.py                  # 核心爬虫
├── main.py                     # CLI入口
├── downloader.py               # 图片下载器
├── output.py                   # 输出处理
│
├── build/                       # 打包配置
│   ├── tray_app.spec
│   ├── api_service.spec
│   └── build_all.bat
│
└── requirements.txt            # 依赖列表
```

## 常见问题

### Q: 首次运行提示找不到Chrome？

A: 确保已安装Chrome浏览器，托盘应用会自动查找Chrome路径。也可以在配置中指定Chrome路径。

### Q: 任务进度一直显示0%？

A: 检查Chrome是否正常启动，查看日志文件了解详细错误信息。

### Q: 端口被占用怎么办？

A: 在配置中修改`api_port`为其他端口，或关闭占用8000端口的程序。

### Q: 如何保留Pinterest登录状态？

A: 设置`chrome_profile`配置项为持久化目录路径，首次手动登录后会保存登录状态。

## 版本历史

### v2.0.0 (2026-04-17)
- 全新托盘应用架构
- 增强版API服务
- Chrome自动管理
- 实时进度追踪
- 配置文件管理
- 开机自启支持

## 许可证

MIT License

## 作者

Pinterest Scraper Team
