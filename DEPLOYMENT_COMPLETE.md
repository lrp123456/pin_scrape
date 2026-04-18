# 📋 完整部署使用文档

## 🎯 架构更新说明

### 新增前端控制台
- `console.html` - Web 界面展示运行状态和实时日志
- `api_service.py` 更新包含 WebSocket 端点 (`/ws`) 和控制端点 (`/api/stop`)
- 服务启动后会自动打开浏览器访问控制台

## 🚀 使用步骤

### 1️⃣ 构建 EXE (首次需要)
```cmd
cd C:\Users\王\Desktop\pinterest-scraper
pyinstaller --onefile --windowed --name run_service api_service.py
```

生成的 `dist\run_service.exe` 即最终分发文件。

### 2️⃣ 启动服务
```cmd
# 双击 run_service.exe 或在命令行运行
dist\run_service.exe
```

服务启动后会：
- 自动打开浏览器访问控制台页面
- 在系统托盘创建图标（如果需要）
- 日志保存到 `service.log`

### 3️⃣ 访问控制台
浏览器自动打开：`http://localhost:8000/`

界面包含：
- 📊 实时指标（已获取 pin 数、状态、耗时）
- 📝 实时日志输出（带颜色区分）
- ⚙️ 配置表单（关键词、数量参数）
- ▶️ 启动/停止按钮

### 4️⃣ 手动运行爬虫
在控制台中填写参数后点击「开始爬取」，或使用命令行：

```cmd
# 方式一：通过 API 调用
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"简约风格\",\"max_pins\":50,\"min_saves\":100}"

# 方式二：使用脚本
C:\scripts\run_scrape.bat "简约风格" 50 100
```

## 📁 文件清单

### 核心文件
| 文件 | 说明 | 位置 |
|------|------|------|
| `api_service.py` | FastAPI 服务（带控制台） | Desktop/pinterest-scraper/ |
| `console.html` | Web 控制台页面 | Desktop/pinterest-scraper/ |
| `pinterest_local.py` | 本地爬虫客户端 | Desktop/pinterest-scraper/ |
| `run_service.exe` | 打包后的可执行文件 | Desktop/pinterest-scraper/dist/ |

### 辅助脚本（Windows）
| 脚本 | 功能 |
|------|------|
| `start_chrome.bat` | 启动 Chrome 调试模式 |
| `stop_chrome.bat` | 停止 Chrome |
| `run_scrape.bat` | 运行一次爬虫任务 |
| `conda_env.bat` | 管理 Conda 环境 |

## 🌐 API 端点

### Web 接口
| 路径 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 控制台页面 |
| `/ws` | WebSocket | 实时日志推送 |
| `/health` | GET | 健康检查 |
| `/api/status` | GET | 服务状态 |
| `/api/scrape` | POST | 启动爬虫 |
| `/api/stop` | POST | 停止爬虫 |

### 使用示例

**启动爬虫**：
```http
POST http://localhost:8000/api/scrape
Content-Type: application/json

{
  "query": "简约风格",
  "max_pins": 50,
  "min_saves": 100,
  "min_likes": 50
}
```

**获取状态**：
```http
GET http://localhost:8000/api/status
```

**WebSocket 订阅日志**：
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  console.log(data.type, data.message);
};
```

## ⚙️ 配置说明

### 修改端口
编辑 `api_service.py` 中的 `uvicorn.run()` 参数：
```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # 修改端口号
```

### 修改 Chrome 路径
编辑 `start_chrome.bat`：
```batch
set CHROME_PATH="D:\Program Files\Google\Chrome\Application\chrome.exe"
```

### 修改 Conda 环境
编辑 `conda_env.bat`：
```batch
set CONDA_DIR=C:\Users\用户名\Anaconda3
set ENV_NAME=pinterest
```

## 🐛 常见问题解决

### 问题 1: 控制台无法连接

**可能原因**：
- 服务未启动
- 端口被占用
- 防火墙阻止

**解决步骤**：
1. 检查服务是否运行：`tasklist | findstr run_service`
2. 检查端口占用：`netstat -ano | findstr :8000`
3. 关闭占用进程：`taskkill /PID 进程号 /F`
4. 检查防火墙：添加例外规则

### 问题 2: 日志不更新

**原因**：WebSocket 连接未建立

**解决**：
1. 检查浏览器控制台是否有错误
2. 确保服务运行在 `http://localhost:8000`
3. 刷新控制台页面重连

### 问题 3: 爬虫无输出

**原因**：Chrome 未启动或登录状态丢失

**解决**：
1. 运行 `start_chrome.bat` 确保 Chrome 已启动
2. 手动访问 `chrome://version` 确认调试端口
3. 重新登录 Pinterest

### 问题 4: EXE 运行闪退

**原因**：缺少依赖或路径错误

**解决**：
1. 在命令行直接运行 EXE 查看错误
2. 检查 `service.log` 日志文件
3. 确保所有脚本在同一目录

## 📊 日志管理

### 查看日志文件
```cmd
# 直接查看
C:\Users\王\Desktop\pinterest-scraper\service.log

# 实时监控
powershell -Command "Get-Content service.log -Wait"
```

### 日志格式
```
2024-04-16 16:30:00,123 - root - INFO - Service starting up
2024-04-16 16:30:08,456 - root - INFO - Starting scrape: query=简约风格
2024-04-16 16:30:45,789 - root - INFO - Scrape completed successfully
```

## 🔄 更新与维护

### 更新服务
```cmd
# 停止服务
# 重新编译 EXE
pyinstaller --onefile --windowed --name run_service api_service.py
# 替换旧文件
```

### 备份配置
```cmd
# 备份脚本
xcopy "C:\Users\王\Desktop\pinterest-scraper" "C:\backup\pinterest" /E /I

# 导出依赖
pip freeze > requirements_backup.txt
```

## ⚡ 性能优化

### 减少日志量
```python
# 在 api_service.py 中调整
handler.setLevel(logging.WARNING)  # 只记录警告以上
```

### 加快启动速度
```python
# 禁用控制台访问日志
uvicorn.run(..., access_log=False)
```

## 📝 总结

- ✅ 单文件 EXE，易于分发
- ✅ 浏览器可视化控制台
- ✅ 实时日志监控
- ✅ 完整的 API 接口
- ✅ 自动 Chrome 管理
- ✅ 日志持久化保存

## 🆘 技术支持

**快速诊断命令**：
```cmd
# 检查服务
curl http://localhost:8000/health

# 查看日志
type service.log

# 检查 Chrome
powershell "(Get-Process chrome -ErrorAction SilentlyContinue).Count"
```

**联系信息**：检查 `service.log` 中的错误信息。
