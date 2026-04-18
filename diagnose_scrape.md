# 爬取卡在"初始化中"问题诊断

## 问题现象
- API服务正常启动
- 发送爬取请求后，状态一直显示"初始化中"
- 进度不更新，任务无法完成

## 可能原因

### 1. Chrome启动问题
**检查方法**：
```bash
# 查看是否有Chrome进程
tasklist | findstr chrome
```

**可能问题**：
- Chrome未安装
- Chrome端口被占用
- Chrome启动超时

**解决方案**：
```bash
# 手动测试Chrome启动
python -c "from chrome_launcher import ChromeLauncher; c = ChromeLauncher(port=9222, headless=False); c.__enter__(); print('Chrome已启动'); import time; time.sleep(10); c.__exit__(None, None, None)"
```

### 2. 爬虫进程未启动
**检查日志**：
```bash
# 查看服务日志
type service.log
```

**可能问题**：
- scraper_worker.exe 不存在（打包环境）
- main.py 导入错误

**解决方案**：
开发环境测试：
```bash
python main.py --query "test" --max-pins 5 --connect --cdp-endpoint http://localhost:9222
```

### 3. 进度更新问题
**检查环境变量**：
```bash
# 进度文件位置
echo %TEMP%\pinterest_scraper_progress.json
```

**手动测试进度更新**：
```python
import requests
import json

# 手动更新进度文件
progress = {
    "running": True,
    "stage": "testing",
    "percentage": 50,
    "current": 5,
    "total": 10,
    "query": "test",
    "message": "测试进度更新"
}

with open(r'%TEMP%\pinterest_scraper_progress.json', 'w') as f:
    json.dump(progress, f)

# 查询API
response = requests.get('http://localhost:8000/api/progress')
print(response.json())
```

## 快速诊断步骤

### 步骤1: 检查Chrome是否正常

```bash
# 手动启动Chrome测试
python -c "
from chrome_launcher import ChromeLauncher
import time

print('启动Chrome...')
launcher = ChromeLauncher(port=9222, headless=False)
launcher.__enter__()
print(f'Chrome已启动，端点: {launcher.endpoint}')
print('等待10秒...')
time.sleep(10)
launcher.__exit__(None, None, None)
print('Chrome已关闭')
"
```

### 步骤2: 检查爬虫能否运行

```bash
# 手动运行爬虫测试（需要先启动Chrome）
# 终端1: 启动Chrome
python -c "from chrome_launcher import ChromeLauncher; import time; c = ChromeLauncher(port=9222, headless=False); c.__enter__(); time.sleep(300)"

# 终端2: 运行爬虫
python main.py --query "test" --max-pins 5 --connect --cdp-endpoint http://localhost:9222
```

### 步骤3: 查看详细日志

```bash
# 启动API服务并查看详细输出
python api_service_enhanced/service_main.py
```

观察控制台输出，看是否有错误信息。

### 步骤4: 检查进程管理

```python
# 创建文件：test_task_manager.py
import sys
sys.path.insert(0, '.')

from api_service_enhanced.task_manager import TaskManager
from api_service_enhanced.progress_tracker import ProgressTracker
from api_service_enhanced.chrome_manager import ChromeManager

print("初始化组件...")
progress_tracker = ProgressTracker()
chrome_manager = ChromeManager(progress_tracker)
task_manager = TaskManager(chrome_manager, progress_tracker)

print("测试任务执行...")
params = {
    'query': 'test',
    'max_pins': 5,
    'chrome_port': 9222,
    'chrome_headless': False
}

result = task_manager.run_scrape(params)
print(f"结果: {result}")
```

运行：
```bash
python test_task_manager.py
```

## 临时解决方案

### 方案1: 使用命令行直接爬取

不使用API服务，直接运行：

```bash
# 1. 启动Chrome
python -c "from chrome_launcher import ChromeLauncher; import time; c = ChromeLauncher(port=9222, headless=False); c.__enter__(); input('按Enter关闭Chrome...'); c.__exit__(None, None, None)"

# 2. 另一个终端运行爬虫
python main.py --query "简约风格" --max-pins 10 --connect --cdp-endpoint http://localhost:9222
```

### 方案2: 使用旧的API服务

如果新的API服务有问题，使用原始版本：

```bash
python api_service.py
```

## 日志收集

收集以下信息帮助诊断：

```bash
# 1. API服务日志
type service.log

# 2. Chrome进程
tasklist | findstr chrome

# 3. 端口占用
netstat -ano | findstr "9222 8000"

# 4. 进度文件
type %TEMP%\pinterest_scraper_progress.json

# 5. Python进程
tasklist | findstr python
```

## 常见错误模式

### 错误1: Chrome启动超时
```
Chrome 在 10 秒内未能启动
```

**原因**: 端口被占用或Chrome路径错误

**解决**:
```bash
# 检查端口
netstat -ano | findstr 9222

# 清理
taskkill /F /IM chrome.exe
```

### 错误2: 连接Chrome失败
```
连接失败: ...
```

**原因**: Chrome未启动或端口错误

**解决**: 确保Chrome先启动

### 错误3: 爬虫进程找不到
```
API服务文件不存在
```

**原因**: 打包后路径问题

**解决**: 使用开发环境测试

## 下一步

1. **运行Chrome测试**：确认Chrome能正常启动
2. **手动测试爬虫**：确认爬虫逻辑正常
3. **查看日志**：找到具体卡住的位置
4. **提供日志**：将错误信息发给我

---

**快速测试命令**：
```bash
# 一键测试
python -c "
from chrome_launcher import ChromeLauncher
from scraper import PinterestScraper
import time

print('1. 启动Chrome...')
launcher = ChromeLauncher(port=9222, headless=False)
launcher.__enter__()

print('2. 连接爬虫...')
scraper = PinterestScraper(cdp_endpoint='http://localhost:9222')
scraper.__enter__()

print('3. 等待5秒...')
time.sleep(5)

print('4. 清理...')
scraper.__exit__(None, None, None)
launcher.__exit__(None, None, None)

print('✓ 测试成功')
"
```
