# 便携版部署指南 - 无需Python环境

## ✅ 最终答案：不需要Python环境！

打包后的程序可以**在任何Windows电脑上运行**，只需Chrome浏览器。

## 架构说明

打包后会生成**3个独立的EXE文件**：

```
PinterestScraper/
├── tray_app.exe          # 托盘应用（主程序）
├── api_service.exe       # API服务
└── scraper_worker.exe    # 爬虫工作进程
```

### 工作原理

```
用户 → tray_app.exe (托盘应用)
          ↓ 启动
       api_service.exe (API服务)
          ↓ 调用
       scraper_worker.exe (执行爬虫)
          ↓ 连接
       Chrome浏览器 (系统已安装)
```

**关键点**：
- 3个exe文件**必须在同一目录**
- **不依赖Python环境**
- **不依赖其他库**
- 只需要**Chrome浏览器**

## 数据采集逻辑说明

### 保存/点赞/评论数据获取方式

1. **始终获取详情**：程序会访问每个 pin 的详情页面获取完整数据（不再依赖筛选条件）
2. **多重提取机制**：
   - 优先从 `__PWS_DATA__` JSON 提取
   - JSON 失败时自动降级为 DOM 文本解析
3. **数字解析**：DOM 提取使用正则表达式从文本中识别实际数值
   - 支持中文：保存/收藏、赞、评论
   - 支持英文：saves、likes、comments
   - 支持千分位格式：1,234

### 筛选条件说明

- `--min-saves`：最小保存数阈值
- `--min-likes`：最小点赞数阈值  
- `--min-comments`：最小评论数阈值
- **注意**：这些是输出筛选，不是数据获取开关

## 打包步骤

### 1. 开发环境准备

```bash
# 安装依赖
pip install -r requirements.txt
playwright install

# 安装PyInstaller
pip install pyinstaller
```

### 2. 执行打包

```bash
cd build
build_all.bat
```

打包过程（约5-10分钟）：
1. 构建托盘应用 → `tray_app.exe`
2. 构建API服务 → `api_service.exe`
3. 构建爬虫工作进程 → `scraper_worker.exe`

### 3. 输出文件

```
dist/
├── tray_app.exe          (~15MB)
├── api_service.exe       (~30MB)
├── scraper_worker.exe    (~40MB)
└── README_PORTABLE.txt
```

**总大小**：约 85-100MB

## 部署到其他电脑

### 必需条件

目标电脑需要：
- ✅ **Windows 10/11** 操作系统
- ✅ **Chrome浏览器**（任意版本）
- ✅ **网络连接**（首次运行需要）
- ❌ ~~Python环境~~ **不需要**
- ❌ ~~其他依赖~~ **不需要**

### 部署步骤

**方法1：直接复制**
```
1. 复制所有exe文件到目标电脑
   - tray_app.exe
   - api_service.exe
   - scraper_worker.exe

2. 确保在同一目录

3. 双击 tray_app.exe 运行
```

**方法2：打包分发**
```
1. 将3个exe文件压缩成ZIP
2. 发送给用户
3. 用户解压后运行 tray_app.exe
```

## 使用流程

### 启动服务

```
1. 双击 tray_app.exe
2. 系统托盘显示图标
3. 右键图标 → 启动服务
4. 等待API服务就绪
```

### 调用API

```
浏览器访问：http://localhost:8000/docs
或使用curl命令调用API
```

### 查看进度

```
右键托盘图标 → 查看状态
或访问：http://localhost:8000/api/progress
```

## 常见问题

### Q: 目标电脑没有Python怎么办？

**A: 没关系！打包后的exe包含所有依赖，不需要Python环境。**

### Q: 需要安装Playwright吗？

**A: 不需要手动安装。首次运行会自动检测并安装。**

### Q: 为什么需要3个exe文件？

**A: 架构设计需要：**
- `tray_app.exe` - 用户界面
- `api_service.exe` - API服务进程
- `scraper_worker.exe` - 爬虫执行进程

**好处**：
- 进程隔离，更稳定
- 可以单独更新某个组件
- 方便调试和维护

### Q: 文件体积为什么这么大？

**A: 包含了完整的运行环境：**
- Python解释器（~15MB）
- Playwright库（~20MB）
- 所有依赖库（~40MB）
- 资源文件（~10MB）

**相比手动配置环境，这个体积是合理的。**
