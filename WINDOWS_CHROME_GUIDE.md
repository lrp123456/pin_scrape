# Pinterest 爬虫 - Windows Chrome 可视化模式指南

## 快速开始

### 步骤1：在 Windows 上启动 Chrome

以**管理员身份**打开 PowerShell，运行：

```powershell
# 关闭现有 Chrome
taskkill /F /IM chrome.exe

# 启动 Chrome 调试模式（使用你的用户配置）
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\Users\王\AppData\Local\Google\Chrome\User Data"
```

> **注意**：将 `王` 替换为你的 Windows 用户名

### 步骤2：确认 Pinterest 登录状态

1. Chrome 启动后，访问 `https://www.pinterest.com`
2. **确保已登录**（看到主页而不是登录页）
3. **保持 Chrome 窗口打开**

### 步骤3：在 WSL 中运行爬虫

```bash
# 方式1：使用脚本
cd /home/lrp/n8n/docker/scripts/pinterest-scraper
./run_with_windows_chrome.sh

# 方式2：直接运行
curl -X POST http://localhost:5000/run/pinterest_scraper_n8n.py \
  -H "Content-Type: application/json" \
  -d '{
    "args": [
      "--query", "现代简约",
      "--max-pins", "50",
      "--min-saves", "50",
      "--connect",
      "--cdp-endpoint", "http://host.docker.internal:9222"
    ]
  }'
```

## 自动化脚本

### 创建运行脚本

保存为 `run_with_windows_chrome.sh`：

```bash
#!/bin/bash
# 使用 Windows Chrome 运行 Pinterest 爬虫

echo "=========================================="
echo "Pinterest 爬虫 - Windows Chrome 模式"
echo "=========================================="
echo ""

# 检查参数
QUERY="${1:-现代简约}"
MAX_PINS="${2:-50}"
MIN_SAVES="${3:-50}"

echo "搜索关键词: $QUERY"
echo "最大数量: $MAX_PINS"
echo "最小 Saves: $MIN_SAVES"
echo ""

# 测试 Windows Chrome 是否可连接
echo "🔍 检查 Windows Chrome..."
if curl -s http://host.docker.internal:9222/json/version > /dev/null 2>&1; then
    echo "✅ Windows Chrome 已就绪"
else
    echo "❌ 无法连接到 Windows Chrome"
    echo ""
    echo "请确保:"
    echo "  1. 在 Windows PowerShell 中运行:"
    echo "     & \"C:\Program Files\Google\Chrome\Application\chrome.exe\" `"
    echo "       --remote-debugging-port=9222 `"
    echo "       --user-data-dir=\"C:\Users\你的用户名\AppData\Local\Google\Chrome\User Data\""
    echo ""
    echo "  2. Chrome 已启动并保持打开"
    echo "  3. 已登录 Pinterest"
    exit 1
fi

echo ""
echo "🚀 启动爬虫..."
echo ""

# 运行爬虫
curl -X POST http://localhost:5000/run/pinterest_scraper_n8n.py \
  -H "Content-Type: application/json" \
  -d "{
    \"args\": [
      \"--query\", \"$QUERY\",
      \"--max-pins\", \"$MAX_PINS\",
      \"--min-saves\", \"$MIN_SAVES\",
      \"--connect\",
      \"--cdp-endpoint\", \"http://host.docker.internal:9222\"
    ]
  }"

echo ""
echo "=========================================="
echo "完成！"
echo "=========================================="
```

## 常见问题

### Q1: 提示 "无法连接到 Windows Chrome"

**解决**: 
1. 检查 Windows 防火墙是否允许 9222 端口
2. 确保 Chrome 真的在运行: `netstat -an | findstr 9222`
3. 尝试使用 IP 地址代替 host.docker.internal:
   ```bash
   # 获取 Windows IP
   ip route | grep default
   # 使用 IP 如: http://192.168.1.100:9222
   ```

### Q2: 仍然被检测为机器人

**解决**:
1. 在 Chrome 中多浏览几个 Pinterest 页面（模拟真人行为）
2. 减少 `max_pins` 数量（建议 20-30）
3. 增加操作间隔：修改 scraper.py 中的 `time.sleep()` 时间

### Q3: Windows 用户名错误

**解决**:
```powershell
# 查看你的用户名
$env:USERNAME

# 完整的 Chrome 配置路径
$env:LOCALAPPDATA + "\Google\Chrome\User Data"
```

## 使用示例

### 示例1: 快速测试
```bash
./run_with_windows_chrome.sh "现代简约" 20 50
```

### 示例2: 批量查询
```bash
# 查询列表
queries=("原木风" "奶油风" "北欧风")

for query in "${queries[@]}"; do
    echo "查询: $query"
    ./run_with_windows_chrome.sh "$query" 30 30
    sleep 60  # 等待1分钟
done
```

### 示例3: n8n 工作流

在 n8n 中，修改 HTTP Request 节点:
```json
{
  "method": "POST",
  "url": "http://python-runner:5000/run/pinterest_scraper_n8n.py",
  "body": {
    "args": [
      "--query", "={{ $json.query }}",
      "--max-pins", "={{ $json.max_pins }}",
      "--min-saves", "={{ $json.min_saves }}",
      "--connect",
      "--cdp-endpoint", "http://host.docker.internal:9222"
    ]
  }
}
```

**注意**: n8n 工作流需要 Windows Chrome 保持运行。

## 优势

✅ **可视化浏览器** - 更难被检测为机器人  
✅ **使用已有登录状态** - 无需重新登录  
✅ **简单配置** - 只需一行命令启动 Chrome  
✅ **实时监控** - 可以在 Windows 上看到爬取过程  

## 提示

💡 **建议**: 每次爬取后，在 Chrome 中正常浏览几分钟，模拟真人行为  
💡 **频率**: 每次爬取间隔至少 5-10 分钟  
💡 **数量**: 单次不超过 100 个 pins  
