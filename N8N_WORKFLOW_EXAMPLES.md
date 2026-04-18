# n8n 工作流配置示例

## 示例 1：基础 Pinterest 爬取

### 节点配置

**节点类型：** HTTP Request

**配置：**
```json
{
  "method": "POST",
  "url": "http://python-runner:5000/execute",
  "authentication": "none",
  "sendBody": true,
  "bodyParameters": {
    "parameters": [
      {
        "name": "script",
        "value": "pinterest_scraper_n8n.py"
      },
      {
        "name": "args",
        "value": {
          "query": "现代简约",
          "max_pins": 100,
          "output": "/tmp/results/pinterest",
          "chrome_profile": "/home/node/.chrome-profile",
          "min_saves": 50
        }
      }
    ]
  }
}
```

### 工作流示例

```
[Schedule Trigger] → [HTTP Request] → [If] → [Google Sheets]
                          ↓                    ↓
                    [Set Variable]      [Slack Notification]
```

**节点详细配置：**

1. **Schedule Trigger** - 每天运行一次
   - Rule: `0 9 * * *`（每天早上 9 点）

2. **HTTP Request** - 调用 Python Runner
   - URL: `http://python-runner:5000/execute`
   - Body: 见上方配置

3. **Set Variable** - 提取结果
   ```javascript
   // Expressions
   {
     "total_pins": $json.body.result.total_pins,
     "output_file": $json.body.result.output_file,
     "query": $json.body.args.query
   }
   ```

4. **If** - 判断是否成功
   - Condition: `{{ $json.success }}` equals `true`

5. **Google Sheets** - 记录结果
   - Operation: Append
   - Sheet: Pinterest Scraping Log
   - Columns: timestamp, query, total_pins, output_file

6. **Slack Notification** - 失败通知
   - Channel: #notifications
   - Message: `Pinterest 爬取失败: {{ $json.error }}`

---

## 示例 2：批量关键词爬取

### 工作流设计

```
[Schedule Trigger]
       ↓
[Code Node - 关键词列表]
       ↓
[Split In Batches]
       ↓
[HTTP Request - Pinterest Scraper]
       ↓
[Wait Node - 30分钟]
       ↓
[Merge]
       ↓
[Google Sheets - 汇总结果]
```

**Code Node 配置：**
```javascript
// 定义关键词列表
const keywords = [
  "现代简约客厅",
  "北欧风格卧室",
  "中式装修",
  "美式厨房",
  "日式浴室"
];

return keywords.map(keyword => ({ json: { keyword } }));
```

**HTTP Request 节点动态参数：**
```json
{
  "script": "pinterest_scraper_n8n.py",
  "args": {
    "query": "={{ $json.keyword }}",
    "max_pins": 50,
    "output": "/tmp/results/pinterest/{{ $json.keyword }}",
    "chrome_profile": "/home/node/.chrome-profile"
  }
}
```

**Wait Node：**
- Wait Amount: 30
- Unit: Minutes

**原因：** Pinterest 有严格的反爬限制，每次爬取后需要休息一段时间。

---

## 示例 3：条件筛选 + 图片下载

### 工作流

```
[Manual Trigger]
       ↓
[HTTP Request - Pinterest Scraper]
       ↓
[Code Node - 解析 JSON]
       ↓
[Filter Node - 高质量筛选]
       ↓
[HTTP Request - 下载图片]
       ↓
[Google Drive - 上传]
```

**Code Node - 解析 JSON：**
```javascript
const fs = require('fs');
const result = $input.first().json;

if (!result.success) {
  throw new Error(result.error);
}

const data = JSON.parse(fs.readFileSync(result.output_file, 'utf8'));

// 提取高质量 pin（按 save 数排序）
const highQualityPins = data.pins
  .filter(pin => pin.saves >= 1000)
  .sort((a, b) => b.saves - a.saves)
  .slice(0, 20);  // 只取前 20 个

return {
  json: {
    pins: highQualityPins,
    total: highQualityPins.length,
    query: data.query
  }
};
```

**Filter Node：**
- Condition: `{{ $json.pins.length }}` greater than `0`

**HTTP Request - 下载图片：**
- 循环模式：Split into items
- URL: `{{ $json.image_url }}`
- Response Format: File

---

## 示例 4：登录状态监控 + 自动告警

### 工作流

```
[Schedule Trigger - 每6小时]
       ↓
[HTTP Request - 测试爬取]
       ↓
[Code Node - 检测登录]
       ↓
[If - 登录失效?]
       ↓
[Slack - 告警通知]
```

**Code Node - 检测登录：**
```javascript
const result = $input.first().json;

// 检查是否因登录失败
const loginRequired = result.error && result.error.includes('需要 Pinterest 登录');

return {
  json: {
    login_ok: !loginRequired,
    last_check: new Date().toISOString(),
    error: loginRequired ? result.error : null
  }
};
```

**If 节点：**
- Condition: `{{ $json.login_ok }}` equals `false`

**Slack 告警：**
```text
⚠️ Pinterest 登录状态已失效

时间: {{ $json.last_check }}
错误: {{ $json.error }}

请立即处理：
1. 连接到 VNC: vnc://localhost:5900
2. 重新登录 Pinterest
3. 重启爬虫任务
```

---

## 部署步骤

### 1. 复制脚本到容器

```bash
# 在宿主机上
cp pinterest_scraper_n8n.py /path/to/scripts/docker/scripts/
cp -r pinterest-scraper /path/to/scripts/docker/scripts/
```

### 2. 修改 docker-compose.yml

确保 volume 正确映射：

```yaml
services:
  python-runner:
    volumes:
      - ./docker/scripts:/home/node/scripts
      - ./data/chrome-profile:/home/node/.chrome-profile
      - ./data/results:/tmp/results
```

### 3. 重启容器

```bash
docker-compose restart python-runner
```

### 4. 在 n8n 中导入工作流

1. 打开 n8n 界面
2. 点击 "Import Workflow"
3. 复制粘贴上面的工作流 JSON
4. 根据需要调整参数

---

## 故障排查

### 问题 1: 脚本找不到

**错误：** `Script not found: pinterest_scraper_n8n.py`

**解决：**
```bash
# 检查脚本是否存在
docker exec n8n-python-runner ls -la /home/node/scripts/

# 如果不存在，检查 volume 映射
docker-compose logs python-runner | grep -i volume
```

### 问题 2: Chrome 启动失败

**错误：** `Chrome 启动失败: FileNotFoundError`

**解决：**
```bash
# 验证 Chromium 是否安装
docker exec n8n-python-runner which chromium

# 如果未安装，重新构建镜像
docker-compose build python-runner
```

### 问题 3: 权限错误

**错误：** `Permission denied: /home/node/.chrome-profile`

**解决：**
```bash
# 在宿主机上设置权限
chmod -R 777 ./data/chrome-profile

# 或在容器内
docker exec n8n-python-runner chmod -R 777 /home/node/.chrome-profile
```

### 问题 4: 端口占用

**错误：** `Address already in use: 9222`

**解决：**
```bash
# 检查是否有残留 Chrome 进程
docker exec n8n-python-runner ps aux | grep chrome

# 杀死残留进程
docker exec n8n-python-runner pkill -9 chrome

# 或使用不同端口
python main.py ... --cdp-endpoint http://localhost:9223
```

---

## 性能优化建议

### 1. 降低爬取频率

Pinterest 有严格的反爬限制，建议：

- 每次爬取不超过 100 个 pin
- 两次爬取间隔至少 30 分钟
- 使用 `--min-saves` 筛选高质量内容，减少请求

### 2. 使用缓存

对相同关键词的结果进行缓存：

```javascript
// 在 n8n 中添加缓存逻辑
const cacheKey = `pinterest_${query}_${Date.now()}`;
// 存储到 Redis，有效期 24 小时
```

### 3. 并发控制

避免同时运行多个爬虫实例：

```javascript
// 使用 Redis 锁
const redis = require('redis');
const client = redis.createClient({ url: process.env.REDIS_URL });

const lock = await client.set('pinterest_lock', '1', 'NX', 'EX', 3600);
if (!lock) {
  throw new Error('另一个爬虫实例正在运行');
}
```

---

## 总结

通过 n8n 工作流集成，你可以：

✅ 定时自动化爬取 Pinterest 内容
✅ 批量处理多个关键词
✅ 自动监控登录状态并告警
✅ 与其他工具（Google Sheets、Slack、Google Drive）无缝集成

关键配置：
- `--chrome-profile /home/node/.chrome-profile` 持久化登录
- `--connect --auto-launch` 自动启动 Chrome
- 适当降低频率避免被封禁
