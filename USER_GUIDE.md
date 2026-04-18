# Pinterest Scraper - 用户使用指南

## 系统要求

### 必需环境
- ✅ **Windows 10/11** 操作系统
- ✅ **Chrome浏览器**（任意版本）
- ✅ **网络连接**（首次运行需要）

### 可选环境
- Python 3.8+（仅开发环境需要）

## 快速开始

### 方式1：直接运行打包版本（推荐）

1. **准备文件**
   ```
   确保以下文件在同一个目录：
   - tray_app.exe
   - api_service.exe
   ```

2. **首次运行**
   ```
   双击 tray_app.exe

   首次运行会自动：
   ✓ 检测浏览器驱动
   ✓ 自动下载安装（约1-2分钟）
   ✓ 完成后显示托盘图标
   ```

3. **后续使用**
   ```
   双击 tray_app.exe
   → 托盘图标立即显示
   → 右键图标控制服务
   ```

### 方式2：开发环境运行

```bash
# 1. 安装Python依赖
pip install -r requirements.txt

# 2. 安装浏览器驱动（首次运行）
playwright install

# 3. 运行托盘应用
python tray_app/tray_main.py
```

## 使用步骤

### 1. 启动服务

1. 右键托盘图标
2. 点击"启动服务"
3. 等待服务就绪（状态显示"运行中"）

### 2. 调用API爬取

**方法A：浏览器访问**
```
打开浏览器访问：http://localhost:8000/docs
在Swagger UI中测试API
```

**方法B：使用curl命令**
```bash
# 爬取Pinterest图片
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "query": "简约风格",
    "max_pins": 50,
    "min_saves": 100
  }'
```

**方法C：集成到其他应用**
```python
import requests

# 调用API
response = requests.post(
    'http://localhost:8000/api/scrape',
    json={
        'query': 'cat',
        'max_pins': 100
    }
)

result = response.json()
print(result)
```

### 3. 查看进度

- **托盘状态**：右键图标查看实时进度
- **API查询**：访问 `http://localhost:8000/api/progress`

### 4. 查看结果

- 右键托盘图标 → "打开输出目录"
- 默认位置：`C:\Users\你的用户名\PinterestScraper\output`

## 常见问题

### Q1: 首次运行提示安装失败？

**原因**：网络问题或权限不足

**解决**：
```bash
# 方法1：以管理员身份运行
右键 tray_app.exe → 以管理员身份运行

# 方法2：手动安装
打开命令提示符，运行：
python -m playwright install
```

### Q2: 服务启动失败？

**检查项**：
1. Chrome浏览器是否已安装
2. 8000端口是否被占用
   ```
   打开浏览器访问：http://localhost:8000
   如果能访问，说明端口被占用
   ```
3. 防火墙是否允许

**解决**：
- 修改配置文件，更改端口
  ```
  右键托盘 → 配置设置
  修改 "api_port": 8001
  保存并重启服务
  ```

### Q3: Chrome启动失败？

**原因**：
- Chrome未安装
- Chrome路径不正确

**解决**：
1. 确认Chrome已安装
2. 在配置中指定Chrome路径：
   ```json
   {
     "chrome_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
   }
   ```

### Q4: 爬取时提示需要登录？

**原因**：Pinterest要求登录

**解决**：
1. 手动登录一次Pinterest
   ```
   方法1：使用Chrome调试模式
   运行 start_chrome.bat
   在打开的浏览器中登录Pinterest
   ```

2. 配置持久化Chrome配置
   ```
   右键托盘 → 配置设置
   设置 "chrome_profile": "C:\\pinterest_chrome_profile"
   ```

### Q5: 如何在其他电脑上使用？

**步骤**：
1. 复制整个程序文件夹到新电脑
2. 确保新电脑有Chrome浏览器
3. 首次运行会自动安装驱动
4. 开始使用

**注意事项**：
- 不需要安装Python
- 不需要手动配置
- 只需要Chrome浏览器

## 高级配置

### 自定义配置文件

位置：`%APPDATA%\PinterestScraper\config.json`

```json
{
  "api_port": 8000,
  "output_dir": "C:\\PinterestOutput",
  "chrome_port": 9222,
  "chrome_headless": false,
  "chrome_profile": "C:\\pinterest_profile",
  "default_query": "",
  "default_max_pins": 100,
  "default_min_saves": 0,
  "default_min_likes": 0,
  "default_min_comments": 0,
  "auto_start": false,
  "custom_icon_path": ""
}
```

### 开机自启

1. 右键托盘图标
2. 勾选"开机自启"
3. 下次开机自动运行

### 修改托盘图标

1. 右键托盘图标 → "修改图标"
2. 选择图标文件（.ico, .png, .jpg等）
3. 重启应用生效

## 性能优化建议

1. **Chrome配置**
   - 使用持久化配置（避免重复登录）
   - 首次使用非无头模式调试

2. **爬取参数**
   - `max_pins`: 建议100-500（太大会很慢）
   - `min_saves`: 设置合理阈值过滤低质量图片

3. **资源管理**
   - 任务完成后Chrome会自动关闭（空闲5分钟）
   - 可以手动停止服务释放资源

## 技术支持

如遇问题，请查看：
1. 托盘应用日志：`%APPDATA%\PinterestScraper\logs\`
2. API服务日志：`service.log`
3. Chrome日志：Chrome调试控制台

---

**版本**: 2.0.0
**更新日期**: 2026-04-17
