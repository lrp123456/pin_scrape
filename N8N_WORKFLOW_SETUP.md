# Pinterest Scraper - n8n 工作流配置

## 📋 工作流功能

这个 n8n 工作流可以：
1. ✅ 传入查询词、数量、save/like/comments 阈值
2. ✅ 输出两个 JSON 文件（完整数据 + 筛选后数据）
3. ✅ 默认下载满足条件的图片
4. ✅ 支持单独命令下载图片
5. ✅ 自动上传到 Google Drive
6. ✅ 记录到 Google Sheets

## 🚀 快速开始

### 步骤 1: 复制脚本到正确位置

```bash
# 脚本已经在正确位置了，检查是否存在
ls -la /home/lrp/n8n/docker/scripts/pinterest_scraper_n8n.py
ls -la /home/lrp/n8n/docker/scripts/pinterest_download_images.py

# 如果没有，复制过去
cp /home/lrp/n8n/docker/scripts/pinterest-scraper/pinterest_scraper_n8n.py /home/lrp/n8n/docker/scripts/
cp /home/lrp/n8n/docker/scripts/pinterest-scraper/pinterest_download_images.py /home/lrp/n8n/docker/scripts/
```

### 步骤 2: 重启 python-runner 容器

```bash
cd /home/lrp/n8n
docker-compose restart python-runner

# 检查脚本是否可访问
docker exec n8n-python-runner ls -la /home/node/scripts/pinterest_scraper_n8n.py
```

### 步骤 3: 在 n8n 中导入工作流

1. 打开 n8n 界面: http://localhost:5678
2. 点击左侧菜单 "Workflows"
3. 点击右上角的 "Import from File"
4. 选择文件: `/home/lrp/n8n/docker/scripts/pinterest-scraper/n8n_workflow_full.json`
5. 点击 "Import"

### 步骤 4: 配置节点

#### Google Sheets 节点
1. 双击 "记录到 Google Sheets" 节点
2. 配置 Credential（OAuth2 或 Service Account）
3. 设置 Spreadsheet ID（你的 Google Sheet 文件 ID）
4. 工作表名称会自动使用查询词

#### Google Drive 节点
1. 双击 "上传到 Google Drive" 节点
2. 配置 Credential
3. 设置 Parent Folder ID（上传到的文件夹 ID）

#### Slack 节点（可选）
1. 双击 "发送错误通知" 节点
2. 配置 Slack Credential
3. 修改 channel 名称

### 步骤 5: 测试运行

1. 点击 "Execute Workflow"
2. 在 "设置参数" 节点中输入：
   ```json
   {
     "query": "现代简约",
     "max_pins": 20,
     "min_saves": 50,
     "min_likes": 10,
     "download_images": true
   }
   ```
3. 查看运行结果

## 📊 工作流节点说明

```
[手动触发] → [设置参数] → [运行爬虫] → [检查结果]
                                     ↓
                              [成功] / [失败]
                                 ↓         ↓
                           [解析结果]   [发送错误通知]
                                 ↓
              ┌──────────────────┼──────────────────┐
              ↓                  ↓                  ↓
      [读取完整JSON]    [读取筛选后JSON]    [是否下载图片?]
              ↓                  ↓                  ↓
      [记录到Sheets]    [记录到Sheets]    [是] / [否]
                                          ↓         ↓
                                    [下载图片]   [跳过]
                                          ↓
                                    [解析下载结果]
                                          ↓
                                    [上传到Drive]
```

## 🔧 节点详细配置

### 1. 设置参数节点

**类型**: Code Node

**代码**:
```javascript
// 配置参数
const query = $input.first().json.query || '现代简约';
const maxPins = $input.first().json.max_pins || 50;
const minSaves = $input.first().json.min_saves || 50;
const minLikes = $input.first().json.min_likes || 10;
const minComments = $input.first().json.min_comments || 0;
const downloadImages = $input.first().json.download_images !== false;

return [{
  json: {
    query,
    max_pins: maxPins,
    min_saves: minSaves,
    min_likes: minLikes,
    min_comments: minComments,
    download_images: downloadImages
  }
}];
```

### 2. 运行 Pinterest 爬虫节点

**类型**: HTTP Request

**配置**:
```json
{
  "method": "POST",
  "url": "http://python-runner:5000/run/pinterest_scraper_n8n.py",
  "body": {
    "args": [
      "--query", "={{ $json.query }}",
      "--max-pins", "={{ $json.max_pins }}",
      "--min-saves", "={{ $json.min_saves }}",
      "--min-likes", "={{ $json.min_likes }}",
      "--min-comments", "={{ $json.min_comments }}",
      "--download-images", "={{ $json.download_images }}"
    ]
  },
  "timeout": 300000
}
```

### 3. 解析结果节点

**代码**:
```javascript
const stdout = $input.first().json.stdout;
const result = JSON.parse(stdout);

if (!result.success) {
  throw new Error(result.error || '爬取失败');
}

return [{
  json: {
    success: result.success,
    query: result.query,
    output_dir: result.output_dir,
    full_file: result.files.full.path,
    filtered_file: result.files.filtered.path,
    total_pins: result.files.full.total_pins,
    filtered_pins: result.files.filtered.total_pins,
    download_info: result.download
  }
}];
```

### 4. 下载图片节点

**配置**:
```json
{
  "method": "POST",
  "url": "http://python-runner:5000/run/pinterest_download_images.py",
  "body": {
    "args": [
      "--json", "={{ $json.filtered_file }}",
      "--min-saves", "={{ $json.min_saves }}",
      "--min-likes", "={{ $json.min_likes }}",
      "--min-comments", "={{ $json.min_comments }}"
    ]
  },
  "timeout": 600000
}
```

## 📁 输出文件

工作流运行后会生成以下文件：

```
/tmp/results/pinterest/
├── data.json              # 完整数据（所有爬取的 pins）
├── filtered_data.json     # 筛选后数据（满足条件的 pins）
└── images/                # 下载的图片
    ├── pin1_saves100_likes20.jpg
    ├── pin2_saves200_likes50.jpg
    └── ...
```

## 🎯 使用示例

### 示例 1: 基础爬取

```json
{
  "query": "现代简约",
  "max_pins": 50,
  "min_saves": 50,
  "download_images": true
}
```

### 示例 2: 高质量筛选

```json
{
  "query": "北欧风卧室",
  "max_pins": 100,
  "min_saves": 200,
  "min_likes": 50,
  "min_comments": 5,
  "download_images": true
}
```

### 示例 3: 仅爬取不下载

```json
{
  "query": "美式厨房",
  "max_pins": 30,
  "min_saves": 100,
  "download_images": false
}
```

## 🔌 API 调用方式

你也可以通过 HTTP API 直接调用：

### 爬取数据

```bash
curl -X POST http://python-runner:5000/run/pinterest_scraper_n8n.py \
  -H "Content-Type: application/json" \
  -d '{
    "args": [
      "--query", "现代简约",
      "--max-pins", "50",
      "--min-saves", "50",
      "--download-images", "true"
    ]
  }'
```

### 单独下载图片

```bash
curl -X POST http://python-runner:5000/run/pinterest_download_images.py \
  -H "Content-Type: application/json" \
  -d '{
    "args": [
      "--json", "/tmp/results/pinterest/filtered_data.json",
      "--min-saves", "50"
    ]
  }'
```

## 🐛 故障排查

### 问题 1: 脚本找不到

**错误**: `Script not found`

**解决**:
```bash
docker exec n8n-python-runner ls -la /home/node/scripts/
# 如果脚本不存在，检查 volume 映射
docker-compose logs python-runner | grep -i volume
```

### 问题 2: 超时错误

**错误**: `Execution timed out`

**解决**:
1. 增加 HTTP Request 节点的 timeout 值
2. 减少 max_pins 数量
3. 检查网络连接

### 问题 3: 下载失败

**错误**: `Download failed`

**解决**:
1. 检查磁盘空间
2. 检查网络连接
3. 查看下载器日志

### 问题 4: 权限错误

**错误**: `Permission denied`

**解决**:
```bash
chmod -R 777 /home/lrp/n8n/data/results
```

## 📝 更新日志

- **v1.0**: 初始版本，支持基础爬取和图片下载
- **v1.1**: 添加单独下载脚本，支持后续补充下载
- **v1.2**: 优化错误处理和日志输出

## 🔗 相关文件

- 主脚本: `/home/lrp/n8n/docker/scripts/pinterest_scraper_n8n.py`
- 下载脚本: `/home/lrp/n8n/docker/scripts/pinterest_download_images.py`
- 工作流: `/home/lrp/n8n/docker/scripts/pinterest-scraper/n8n_workflow_full.json`

## 💡 提示

1. **首次运行建议**: 先用少量 pins（20-30）测试
2. **频率控制**: 每次间隔至少 5-10 分钟，避免被封
3. **Chrome 配置**: 确保已登录 Pinterest，避免登录提示
4. **存储空间**: 定期检查 `/tmp/results` 目录，清理旧数据
