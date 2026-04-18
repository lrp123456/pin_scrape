# Pinterest Scraper - Windows Native FastAPI Architecture

## 概述 (Overview)

本项目重构为 **FastAPI 本地服务 + Windows Chrome 原生调试** 架构，彻底解决 Docker 网络访问 Windows localhost 的问题。

## 架构图 (Architecture)

```
Windows Host (原生 Chrome)
├─ 1. Chrome 调试模式 (端口 9222)
│   ├─ 访问: http://localhost:9222/json/version
│   └─ WebSocket: ws://localhost:9222/...
│
├─ 2. FastAPI 服务 (端口 8000)
│   ├─ URL: http://localhost:8000/api/scrape
│   ├─ 方法: POST
│   └─ Body: {"query": "...", "max_pins": 50, ...}
│
└─ 3. n8n (Docker 容器)
    └─ HTTP 请求 → http://localhost:8000/api/scrape
```

## 文件清单 (File List)

| 文件 | 用途 | 运行位置 |
|------|------|----------|
| `start_chrome.bat` | 启动 Chrome 调试模式 | Windows |
| `stop_chrome.bat` | 停止 Chrome | Windows |
| `run_scrape.bat` | 运行一次爬虫 | Windows |
| `api_service.py` | FastAPI HTTP 服务 | Windows |
| `pinterest_local.py` | 本地 HTTP 客户端 | Windows |

## 快速开始 (Quick Start)

### 步骤 1: 启动 Chrome 调试模式

```cmd
C:\scripts\start_chrome.bat
```

### 步骤 2: 启动 FastAPI 服务

```cmd
C:\scripts\api_service.py --port 8000
```

### 步骤 3: n8n 工作流配置

```json
{
  "nodes": [
    {
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8000/api/scrape",
        "body": {"query": "{{$json.query}}"}
      },
      "type": "n8n-nodes-base.httpRequest"
    }
  ]
}
```

### 步骤 4: 运行爬虫

```cmd
C:\scripts\run_scrape.bat "简约风格" 50 100
```

## n8n 节点配置 (n8n Workflow)

```json
{
  "nodes": [
    {
      "name": "设置参数",
      "type": "n8n-nodes-base.code",
      "parameters": {
        "jsCode": "return [{ json: {\n          query: $input.first().json.query || '现代简约',\n          max_pins: $input.first().json.max_pins || 50,\n          min_saves: $input.first().json.min_saves || 50,\n          min_likes: $input.first().json.min_likes || 10,\n          min_comments: $input.first().json.min_comments || 0,\n          download_images: $input.first().json.download_images !== false\n        } }];"
      }
    },
    {
      "name": "调用 FastAPI",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8000/api/scrape",
        "body": "={{ JSON.stringify($json) }}",
        "contentType": "json"
      }
    }
  ],
  "connections": {
    "设置参数": { "main": [[{ "node": "调用 FastAPI", "type": "main", "index": 0 }]] }
  }
}
```

## API 端点 (API Endpoints)

### POST /api/scrape

**请求体 (Body):**
```json
{
  "query": "搜索关键词",
  "max_pins": 50,
  "min_saves": 100,
  "min_likes": 50,
  "min_comments": 0,
  "download_images": true
}
```

**响应 (Response):**
```json
{
  "success": true,
  "query": "简约风格",
  "chrome_version": "Chrome/147.0.7727.102",
  "websocket": "ws://localhost:9222/devtools/browser/..."
}
```

## 常见问题 (FAQ)

**Q: 为什么 n8n 容器可以直接访问 `localhost:8000`？**
A: FastAPI 在 Windows 主机运行，n8n 通过 `http://localhost:8000` 直接连接，绕过 Docker 网络。

**Q: 是否需要复制配置文件？**
A: 不需要。Chrome 使用原始配置，登录状态完全保留。

**Q: 如何停止服务？**
A: 运行 `stop_chrome.bat` 停止 Chrome，关闭 FastAPI 终端窗口。

## 迁移历史 (Migration)

- **旧方案**: Docker 容器运行爬虫 → VNC/RDP 到 Windows → 浏览器自动化
- **新方案**: n8n → FastAPI → Chrome CDP → Pinterest
  - 优点: 无需远程桌面，更简单稳定
  - 缺点: 需要 Windows 主机始终运行
