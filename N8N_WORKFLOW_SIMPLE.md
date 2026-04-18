# Pinterest Scraper - n8n 工作流配置（简洁版）

## 📋 工作流功能

简洁版工作流，只保留核心功能：
1. ✅ 传入查询词、数量、save/like/comments 阈值
2. ✅ 输出两个 JSON 文件（完整数据 + 筛选后数据）
3. ✅ 默认下载满足条件的图片到本地
4. ✅ 支持单独命令下载图片
5. ❌ 不上传到任何外部服务（Google Drive/Sheets 等）

你可以用钉钉模块自行处理输出结果。

## 🚀 快速开始

### 步骤 1: 重启容器

```bash
cd /home/lrp/n8n
docker-compose restart python-runner
```

### 步骤 2: 导入工作流

1. 打开 n8n: http://localhost:5678
2. Workflows → Import from File
3. 选择: `n8n_workflow_simple.json`

### 步骤 3: 运行测试

点击 "Execute Workflow"，输入参数：

```json
{
  "query": "现代简约",
  "max_pins": 50,
  "min_saves": 50,
  "min_likes": 10,
  "download_images": true
}
```

## 📁 输出文件位置

工作流运行后，文件保存在容器内：

```
/tmp/results/pinterest/
├── data.json              # 完整数据（所有 pins）
├── filtered_data.json     # 筛选后数据（满足条件的 pins）
└── images/                # 下载的图片
    ├── pin1_saves100_likes20.jpg
    ├── pin2_saves200_likes50.jpg
    └── ...
```

从宿主机访问：
```bash
ls -la /home/lrp/n8n/data/results/pinterest/
```

## 🔌 API 调用

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

## 🎯 工作流节点

```
[手动触发] → [设置参数] → [运行爬虫] → [成功?]
                              ↓
                    [解析结果] ← [失败] → [错误处理]
                         ↓
              ┌──────────┼──────────┐
              ↓          ↓          ↓
      [完整JSON]  [筛选JSON]  [下载图片?]
                                      ↓
                                [是] → [下载]
                                [否] → [结束]
```

## 📝 节点输出数据

### 读取完整JSON 节点输出：

```json
{
  "file_type": "full",
  "file_path": "/tmp/results/pinterest/data.json",
  "file_name": "data.json",
  "query": "现代简约",
  "total_pins": 100,
  "main_pins": 50,
  "similar_pins": 50,
  "filtered_pins": 20,
  "timestamp": "2024-01-15T10:30:00",
  "pins": [...]
}
```

### 读取筛选后JSON 节点输出：

```json
{
  "file_type": "filtered",
  "file_path": "/tmp/results/pinterest/filtered_data.json",
  "file_name": "filtered_data.json",
  "query": "现代简约",
  "total_pins": 20,
  "timestamp": "2024-01-15T10:30:00",
  "pins": [...]
}
```

### 解析下载结果 节点输出：

```json
{
  "download_success": true,
  "total_images": 20,
  "downloaded_images": 18,
  "images_dir": "/tmp/results/pinterest/images"
}
```

## 💡 使用钉钉发送结果

你可以在任何节点后添加钉钉节点，例如：

```javascript
// 在"读取筛选后JSON"节点后添加钉钉节点
// 消息内容示例：
`Pinterest 爬取完成

查询词: {{ $json.query }}
总数量: {{ $json.total_pins }}
文件路径: {{ $json.file_path }}
图片目录: /tmp/results/pinterest/images`
```

## 🐛 故障排查

### 脚本找不到

```bash
docker exec n8n-python-runner ls -la /home/node/scripts/pinterest_scraper_n8n.py
```

### 检查输出

```bash
# 在宿主机查看
ls -la /home/lrp/n8n/data/results/pinterest/

# 在容器内查看
docker exec n8n-python-runner ls -la /tmp/results/pinterest/
```

## 📂 相关文件

- 主脚本: `/home/lrp/n8n/docker/scripts/pinterest_scraper_n8n.py`
- 下载脚本: `/home/lrp/n8n/docker/scripts/pinterest_download_images.py`
- 工作流: `/home/lrp/n8n/docker/scripts/pinterest-scraper/n8n_workflow_simple.json`
