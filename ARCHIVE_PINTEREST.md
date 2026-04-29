# Pinterest 爬虫项目归档

## 项目信息

- **项目名称**: Pinterest Scraper
- **创建日期**: 2026-04-17
- **最后更新**: 2026-04-20
- **技术栈**: Python + Playwright + FastAPI + PyStray
- **状态**: 已归档（可继续使用）

---

## 核心文件

### 爬虫核心
| 文件 | 说明 | 行数 |
|------|------|------|
| `scraper.py` | PinterestScraper 类，核心爬虫逻辑 | ~2360 |
| `main.py` | CLI 入口 | ~375 |
| `downloader.py` | 图片下载器 | ~142 |
| `chrome_launcher.py` | Chrome 启动器 | ~280 |

### API 服务
| 文件 | 说明 |
|------|------|
| `api_service.py` | 基础 API 服务 |
| `api_service_enhanced/` | 增强版 API（进度跟踪、异步任务）|

### 托盘应用
| 文件 | 说明 |
|------|------|
| `tray_app/tray_main.py` | 托盘应用入口 |
| `tray_app/console_gui.py` | 控制台界面 |
| `tray_app/config_gui.py` | 配置对话框 |

### 共享模块
| 文件 | 说明 |
|------|------|
| `shared/models.py` | Pin 数据模型 |
| `shared/config_manager.py` | 配置管理 |
| `shared/progress_state.py` | 进度状态 |
| `shared/config_schema.py` | 配置验证 |

---

## 主要功能

### 已实现
- ✅ 拟人化浏览模式（随机点击、滚动、阅读时间）
- ✅ 相似推荐探索（贪心爬山算法）
- ✅ 媒体类型筛选（图片/视频）
- ✅ 最小收藏数筛选
- ✅ Redis 去重
- ✅ 代理支持（下载时）
- ✅ 进度跟踪
- ✅ FastAPI 异步任务
- ✅ 系统托盘应用
- ✅ Chrome 自动启动
- ✅ N8N 工作流集成

### 问题记录
- ❌ 代理下载仍有连接问题（SSL 验证已禁用）
- ⚠️ build 程序退出问题已部分修复

---

## 工作流程

```
用户输入 → CLI/API/托盘
    ↓
PinterestScraper.search()
    ↓
探索模式：贪心爬山
    ↓
收集达标 Pin → 下载图片
    ↓
保存到 output/
```

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/scrape` | POST | 同步爬取 |
| `/api/scrape/async` | POST | 异步爬取 |
| `/api/progress` | GET | 获取进度 |
| `/api/status` | GET | 服务状态 |
| `/api/config` | GET/POST | 配置管理 |

---

## 命令行用法

```bash
# 基本用法
python main.py -q "现代简约" -n 100

# 带筛选
python main.py -q "简约风格" -n 50 --min-saves 100 --connect --auto-launch

# API 模式
python api_service_enhanced/service_main.py --port 8000
```

---

## 输出文件

```
output/
├── data.json           # 所有数据
├── qualified_pins.json # 达标数据
├── filtered_data.json  # 筛选后数据
└── images/            # 下载图片
```

---

## 相关文档

| 文档 | 说明 |
|------|------|
| `README.md` | 项目说明 |
| `AGENTS.md` | AI Agent 知识库 |
| `SCALING_GUIDE.md` | 扩展多网站指南 |
| `CONSOLE_GUIDE.md` | 控制台使用指南 |
| `DOCKER_DEPLOYMENT.md` | Docker 部署指南 |

---

## 扩展指南

参见 `SCALING_GUIDE.md`，包含：
- 如何创建新爬虫类
- 如何注册网站到控制台
- 如何扩展 API 路由
- 必需实现的方法清单

---

## 变更历史

### 2026-04-20
- 修复爬坡循环收集逻辑（添加 collected_pin_ids）
- 添加代理配置支持
- 添加 SSL 验证禁用
- 创建通用爬虫基类框架

### 2026-04-19
- 修复 scroll_count 递增问题
- 修复 is_collected 重复创建 Redis 连接
- 代理配置从浏览器移到下载器

### 2026-04-18
- 初始探索模式实现
- 贪心爬山算法
- Redis 去重

---

## 联系方式

如有问题，请检查：
1. `TROUBLESHOOTING.md` 常见问题
2. `DOCKER_DEPLOYMENT.md` 部署问题
3. 控制台日志输出
