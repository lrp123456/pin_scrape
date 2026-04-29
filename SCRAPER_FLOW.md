# Pinterest Scraper 完整流程演示

> 本文档描述从命令行/API 调用到图片下载的完整爬虫流程，包含所有自建模块。

---

## 1. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                        入口层（Entry）                             │
│  main.py (CLI)          │  api_service_enhanced/ (FastAPI)        │
│  python main.py -q ...  │  POST /api/scrape/async                │
└────────────┬─────────────┴──────────────┬─────────────────────────┘
             │                            │
             ▼                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    多 Worker 协调层                                │
│  shared/coordinator.py    shared/async_ai_worker.py               │
│  ┌─────────┐ ┌─────────┐ ┌──────────────┐                        │
│  │ 入口队列 │ │ AI缓存  │ │ 终止广播     │ ← Redis/内存 双重模式   │
│  │ entry_q │ │ filter: │ │task_complete │                        │
│  └─────────┘ └──────────┘ └──────────────┘                        │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    核心爬取引擎（PinterestScraper）                 │
│  scraper.py (~3500 行)                                            │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐         │
│  │ search()    │→│ _explore_     │→│ 爬坡循环          │         │
│  │ 导航+分支   │  │ similar_pins │  │ 批量池 AI 收集    │         │
│  └─────────────┘  └──────────────┘  └──────────────────┘         │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│                     AI 筛选层（多 Provider 降级）                   │
│  shared/ai_filter_manager.py                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 豆包(火  │ │ 智谱GLM  │ │ NVIDIA   │ │ Ollama   │            │
│  │ 山引擎)  │ │ (Gitee)  │ │ NIM      │ │ (本地)   │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│        429 限流 → 立即降级下一个，不做重试                          │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    输出层                                          │
│  output.py (JSON)  +  downloader.py (图片下载)                    │
│  output/{关键词}_{时间戳}/                                         │
│    ├── data.json            # 全部采集数据                         │
│    ├── qualified_pins.json  # 达标筛选后的数据                     │
│    ├── images/              # 下载的图片                           │
│    └── scraper.log          # 运行日志                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 初始化管道

### 2.1 流程图

```
main.py / API
    │
    ├─ 1. Chrome 启动
    │   ├─ --auto-launch → ChromeLauncher 自动启动 Chrome(CDP:9222)
    │   ├─ --connect → 连接已有 Chrome
    │   └─ --proxy-server → 代理穿透
    │
    ├─ 2. Redis 连接
    │   ├─ get_redis_client() 单例连接
    │   └─ 失败 → 自动降级为内存模式
    │
    ├─ 3. 加载已收集 ID
    │   └─ init_collected_ids_from_redis() → SMEMBERS 加载到内存
    │
    ├─ 4. 创建 PinterestScraper
    │   ├─ _setup_logger()         → 日志系统
    │   ├─ _init_ai_filter()       → 3 层检查：CLI参数→模块导入→配置文件
    │   └─ _search_page_url = None → URL 栈初始化
    │
    └─ 5. 调用 scraper.search(keyword, max_pins, ...)
```

### 2.2 关键文件

| 模块 | 文件 | 行号 | 职责 |
|------|------|------|------|
| Chrome 启动 | `chrome_launcher.py` | - | 启动/连接 Chrome 调试实例 |
| Chrome 管理 | `api_service_enhanced/chrome_manager.py` | L29 | API 服务中的 Chrome 生命周期 |
| Redis 连接 | `shared/models.py` | L35-L78 | 单例 Redis 客户端 |
| Redis 配置 | `shared/redis_config.py` | L13-L145 | 配置加载/保存/测试 |
| 日志系统 | `scraper.py` | L141-L186 | `_setup_logger()` |

---

## 3. search() 方法 — 导航与分支

### 3.1 流程图

```
scraper.search(keyword="现代简约", max_pins=50, min_saves=100, ...)
    │
    ├─ 1. 保存搜索页 URL（用于返回兜底）
    │   ├─ 页面已是搜索结果 → self._search_page_url = self.page.url
    │   └─ 新导航 → goto(url) → self._search_page_url = self.page.url
    │
    ├─ 2. 创建 Worker 协调器
    │   ├─ ScrapeCoordinator(keyword, worker_id)
    │   │   ├─ Redis 可用 → 共享入口队列 + AI 缓存 + 终止广播
    │   │   └─ Redis 不可用 → threading.Lock + 内存（单 Worker）
    │   └─ AsyncAIWorker(ai_manager, coordinator, max_workers=2)
    │
    ├─ 3. 生成动态提示词
    │   └─ ai_manager.generate_dynamic_criteria(keyword)
    │       ├─ Ollama text-only API 调用
    │       ├─ 返回 {criteria, style_keywords, negative_examples}
    │       ├─ 缓存到 PromptGenerator._dynamic_cache
    │       └─ 失败 → 回退 PROMPT_TEMPLATES 静态匹配
    │
    ├─ 4. 模拟用户浏览
    │   └─ 随机等待 5-8 秒 + 登录检测
    │
    └─ 5. 分支选择
        ├─ min_saves > 0 或 climb_mode
        │   └─→ _explore_similar_pins()  [探索/爬坡模式，详见第4章]
        │
        └─ min_saves = 0 且 climb_mode = False
            └─→ _scroll_and_collect()  [快速滚动模式]
```

### 3.2 快速滚动模式 (`_scroll_and_collect`)

```
while 未达标:
    ├─ 滚动页面加载更多 pin
    ├─ _extract_pins_from_page() 提取基础数据
    ├─ AI 评估每个 pin
    │   ├─ 通过 → 创建 Pin 对象 → 加入结果
    │   └─ 未通过 → set_filter_result() 缓存 → 跳过
    └─ 达标 → return
```

---

## 4. 探索/爬坡模式 — `_explore_similar_pins`

> 这是整个系统最核心的方法。入口 pin 从搜索页选取，然后在详情页通过相似推荐不停"爬坡"找更高的 saves。

### 4.1 核心参数

```
target_count      = max_pins         # 达标收集目标（如 50）
min_saves         = 100              # saves 筛选阈值
max_attempts      = max(target*10, 50)  # 外层最大尝试次数
max_depth         = 15               # 爬坡最大深度
BATCH_COLLECT_SIZE = 5               # 批量 AI 收集池大小
```

### 4.2 外层循环 — 入口派发

```
while qualified_count < target_count and attempt < max_attempts:
    │
    ├─ 0. 检查终止广播
    │   └─ coordinator.is_task_complete()? → return（其他 Worker 已完成）
    │
    ├─ 1. 页面状态检查
    │   └─ _ensure_page_alive_and_on_search()（三层恢复：新建页→重连CDP→重启浏览器）
    │
    ├─ 2. 【协调器模式】获取入口 pin
    │   ├─ pop_entry_pin() → 从 Redis 队列原子获取
    │   └─ 队列空 → 回退到本地搜索页遍历
    │
    ├─ 3. 入扣耗尽 → 搜索页滚动加载更多
    │   ├─ PGDN 滚动 2-4 次
    │   ├─ _get_search_page_pin_ids() 重新采集
    │   ├─ 过滤已收集 + 已访问
    │   ├─ push_entry_pins() 推入协调器队列
    │   └─ visited_ids.clear() → continue
    │
    ├─ 4. AI 入口预筛选（在点击前！）
    │   ├─ _get_pin_image_url_from_search(entry_pin_id)
    │   │   └─ 3 种选择器策略：直接链接 → data-pin-id → img 父链接
    │   └─ ai_manager.evaluate_pin(image_url, keyword)
    │       ├─ 使用 BASE_PROMPT_TEMPLATE（入口初筛）
    │       ├─ 3 字段：is_interior / matches_query / is_approved
    │       ├─ 通过 → 继续
    │       └─ 未通过 → set_filter_result() 缓存 → continue 换下一个
    │
    ├─ 5. 点击入口 pin 进入详情页
    │   └─ query_selector → scroll_into_view → click → wait URL contains /pin/{id}
    │
    └─ 6. 进入内层爬坡循环 ↓
```

### 4.3 内层循环 — 爬坡与收集

```
while depth < max_depth:
    │
    ├─ 1. 达标检查
    │   └─ coordinator.is_task_complete()? → return
    │
    ├─ 2. 去重检查
    │   ├─ visited_ids.contains(pin_id)? → break
    │   └─ coordinator.is_collected(pin_id)? → break
    │
    ├─ 3. 提取 pin 详情
    │   └─ _extract_pin_details_from_modal()
    │       ├─ PWS_DATA JSON 提取（结构优先）
    │       ├─ DOM 扫描（兜底，parseFlexibleNumber K/M 支持）
    │       └─ 返回 {pin_id, saves, title, image_url, ...}
    │
    ├─ 4. 收集判定
    │   ├─ saves >= min_saves AND media_match → 加入 collected_pins
    │   └─ saves < min_saves → 进入爬坡逻辑（不收集）
    │
    ├─ 5. AI 深度筛选（收集时）
    │   └─ _apply_collection_ai_filter(pin_id, image_url)
    │       ├─ 先查 coordinator.get_filter_result(pin_id) 缓存
    │       ├─ 无缓存 → ai_manager.evaluate_pin_for_collection()
    │       │   ├─ 使用 COLLECTION_PROMPT_TEMPLATE
    │       │   ├─ 4 维度：is_interior / style_match(0-10) / has_human / scene_completeness(0-10)
    │       │   └─ 通过条件：style_match>=7 AND !has_human AND scene_completeness>=6
    │       ├─ 缓存结果 → set_filter_result()
    │       └─ 返回 True/False
    │
    ├─ 6. 达标检查
    │   └─ qualified_count >= target_count? → set_task_complete() → return
    │
    └─ 7. 爬坡循环（见下方）
```

### 4.4 爬坡循环详细流程

```
查找相似推荐
    └─ _find_similar_pins_in_modal(scroll_times=1)
        └─ 最多 8 轮滚动，每轮最多检查 5 个相似 pin

for each 相似推荐:
    │
    ├─ 提取 saves
    │   ├─ PWS_DATA → DOM → aria-label 三重提取
    │   └─ parseFlexibleNumber("1.2k") → 1200
    │
    ├─ saves >= min_saves?
    │   └─ 【加入批量收集池】 pending_collect.append(...)
    │       ├─ 池满(≥5) → _flush_batch_collect_pool()
    │       │   └─ ai_manager.evaluate_pins_batch(5 张图)
    │       │       ├─ 使用 BATCH_COLLECTION_PROMPT_TEMPLATE
    │       │       ├─ 优先级：豆包批量 → Ollama 批量 → 逐个降级
    │       │       └─ 返回每张图的评估结果
    │       └─ 达标 → set_task_complete() → return
    │
    └─ saves > current_saves?
        ├─ 【爬坡升级前 AI 验证】
        │   ├─ 查 coordinator.get_filter_result(sp_id) 缓存
        │   └─ 无缓存 → ai_manager.evaluate_pin() AI 验证
        │       └─ 不合格 → visited_ids.add → continue
        │
        ├─ 升级前冲刷批量池
        │   └─ _flush_batch_collect_pool(pending_collect)
        │
        ├─ 升级：current_saves = sp_saves, current_pin_id = sp_id
        └─ depth += 1 → 重新进入内层循环
```

---

## 5. 导航恢复机制 — URL 深度管理

### 5.1 URL 栈设计

```
启动时：self._search_page_url = None

导航到搜索页时：
    self._search_page_url = self.page.url  # 保存精确搜索页 URL
    示例：https://www.pinterest.com/search/pins/?q=%E7%8E%B0%E4%BB%A3&rs=typed

爬坡升级时：
    depth 递增（跟踪在详情页的深度）
    不保存中间 URL，依赖浏览器原生 history.back()

返回搜索页时：
    见下方 _navigate_back_to_search
```

### 5.2 `_navigate_back_to_search` 三层兜底

```
def _navigate_back_to_search(keyword):
    │
    ├─ 第0层：页面状态检查
    │   ├─ 页面已失效？→ return
    │   └─ URL 已含 /search/？→ return（已到达）
    │
    ├─ 第1层：关闭模态弹窗（首选，不破坏 SPA 状态）
    │   ├─ _close_pin_modal()
    │   │   ├─ 点击背景遮罩
    │   │   ├─ 点击关闭按钮
    │   │   ├─ 按 Escape 键
    │   │   └─ 等待 1.5-2.5 秒
    │   └─ URL 含 /search/？→ 成功
    │
    ├─ 第2层：浏览器后退
    │   ├─ _safe_go_back()
    │   │   ├─ page.go_back()
    │   │   └─ wait_until="domcontentloaded"
    │   ├─ 等待 1-2 秒
    │   └─ URL 含 /search/？→ 成功
    │
    └─ 第3层：用保存的 URL 直接跳转（最后手段）
        └─ self.page.goto(self._search_page_url, timeout=30000)
            └─ URL 是当初离开搜索页时保存的精确地址，
                包含 Pinterest 可能追加的参数，比重新构造更可靠
```

### 5.3 调用点（6 处）

| 场景 | 行号 | 触发条件 |
|------|------|----------|
| 搜索页被重定向 | L197 | 页面不在搜索页 |
| 详情提取失败 | L1335 | `_extract_pin_details_from_modal` 失败 |
| 收集达标后返回 | L1424 | `qualified_count >= target_count` |
| 爬坡批量收集后返回 | L1649 | 批量冲刷后达标 |
| 未找到更优跳板 | L1907 | 爬坡循环结束没有升级 |
| 未找到达标 pin | L1914 | 相似推荐全部检查完毕 |

---

## 6. AI 筛选管道

### 6.1 三套提示词模板

```
查询词 "奶油风"
    │
    ▼
┌─────────────────────────────────────────────┐
│ generate_dynamic_criteria("奶油风")           │  ← shared/dynamic_prompt.py
│ Ollama text-only API → 结构化筛选标准          │
│                                              │
│ 输出：                                       │
│ {                                            │
│   "criteria": "【主色调】低饱和度暖色系...",    │
│   "style_keywords": ["奶油色", "米白", ...],  │
│   "negative_examples": "大面积高饱和度亮色..."  │
│ }                                            │
│                                              │
│ ↓ 缓存到 PromptGenerator._dynamic_cache      │
└────────────┬────────────────────────────────┘
             │
             ▼
    ┌────────────────────┬────────────────────┬────────────────────┐
    │                    │                    │                    │
    ▼                    ▼                    ▼                    │
┌──────────┐     ┌────────────────┐    ┌──────────────────────┐  │
│ 入口初筛  │     │ 收集深度筛选    │    │ 批量收集              │  │
│ BASE_    │     │ COLLECTION_    │    │ BATCH_COLLECTION_    │  │
│ PROMPT_  │     │ PROMPT_        │    │ PROMPT_              │  │
│ TEMPLATE │     │ TEMPLATE       │    │ TEMPLATE             │  │
├──────────┤     ├────────────────┤    ├──────────────────────┤  │
│ 3 字段：  │     │ 4 维度：       │    │ 同上，一次多张        │  │
│ is_interior│   │ is_interior    │    │ 输出 JSON 数组       │  │
│ matches_  │     │ style_match    │    │                      │  │
│ query     │     │ has_human      │    │                      │  │
│ is_approved│   │ scene_         │    │                      │  │
│           │     │ completeness   │    │                      │  │
│ 通过条件： │     │ is_approved    │    │                      │  │
│ is_interior│   ├────────────────┤    │                      │  │
│ AND       │     │ 通过条件：       │    │                      │  │
│ matches_  │     │ style>=7 AND   │    │                      │  │
│ query     │     │ !has_human AND │    │                      │  │
│           │     │ scene>=6 AND   │    │                      │  │
│           │     │ is_interior    │    │                      │  │
└──────────┘     └────────────────┘    └──────────────────────┘  │
```

### 6.2 Provider 降级链

```
配置优先级：ai_provider_priority = [
    "doubao_batch",      # 1. 豆包批量（火山引擎，最快）
    "doubao_base64",     # 2. 豆包单张
    "zhipu_base64",      # 3. 智谱 GLM（Gitee AI）
    "nvidia_base64",     # 4. NVIDIA NIM
    "ollama"             # 5. 本地 Ollama（兜底）
]

对每个 Provider：
    ├─ 调用 API
    ├─ 成功 → 返回结果
    ├─ 429 限流 → 不重试，立即跳下一个
    ├─ 超时 → 跳下一个
    └─ 全部失败 → 默认不通过（入口筛选）/ 默认通过（收集筛选）
```

### 6.3 AI 筛选缓存机制

```
任何 pin 的 AI 筛选结果都写入协调器缓存：
    coordinator.set_filter_result(pin_id, result)
    → Redis: SET ps:{query}:filter:{pin_id} <json> EX 86400 (24h 过期)

后续 Worker 检查同一个 pin 时：
    cached = coordinator.get_filter_result(pin_id)
    → 命中 → 毫秒级返回，跳过 AI 调用（40-70s → <1ms）
    → 未命中 → 正常 AI 调用 → 写回缓存
```

### 6.4 三阶段 AI 调用位置

| 阶段 | 调用位置 | 提示词 | 调用方式 | 缓存 |
|------|---------|--------|---------|------|
| 入口预筛 | `_explore_similar_pins` L1207 | BASE_PROMPT | 单图，点击前 | ✅ |
| 收集筛选 | `_apply_collection_ai_filter` L2277 | COLLECTION_PROMPT | 单图 | ✅ |
| 批量收集 | `_flush_batch_collect_pool` L2286 | BATCH_COLLECTION_PROMPT | 5 张一批 | ✅ |

---

## 7. 多 Worker 协调

### 7.1 Redis Key 完整 Schema

```
ps:{query}:collected          Set       已收集 pin ID（去重）
ps:{query}:filter:{pin_id}    String    AI 筛选缓存（24h TTL）
ps:{query}:entry_q            List      入口队列（RPUSH/LPOP 原子竞争）
ps:{query}:assigned           Set       分配锁（防并发处理同一 pin）
ps:{query}:pending_climb      List      待爬坡队列
ps:{query}:saves              ZSet      saves 排行榜（saves 为 score）
ps:{query}:workers            Hash      Worker 心跳（60s 过期）
ps:{query}:task_complete      String    任务终止广播
```

### 7.2 协调器双模式

```
┌─────────────────────────────────────┐
│  Redis 可用                          │
│  ├─ 所有操作走 Redis                │
│  ├─ 多 Worker 共享入口队列 + AI缓存  │
│  └─ 终止广播：任一 Worker 达标→通知  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Redis 不可用（自动降级）            │
│  ├─ 使用 threading.Lock + 内存字典  │
│  ├─ 仅支持单 Worker 模式            │
│  └─ 入口队列降至本地 set() 遍历      │
└─────────────────────────────────────┘
```

### 7.3 跨 Worker 终止流程

```
Worker-0 收集达标：
    ├─ coordinator.set_task_complete(qualified_count)
    │   └─ Redis: SET ps:{query}:task_complete "..."
    │
    └─ return

Worker-1 正在循环：
    ├─ 每轮外层 while 起始：is_task_complete()? → True
    ├─ 每轮内层 while 起始：is_task_complete()? → True
    ―→ 发现广播 → 立即停止 → return
```

---

## 8. 数据输出

### 8.1 输出目录结构

```
output/现代简约_20260428_083720/
├── data.json              # 全部采集的原始数据
│   └── {"pins": [{"id": "...", "saves": 161, "image_url": "...", ...}]}
│
├── qualified_pins.json    # 达标筛选后的数据（saves >= min_saves）
│   └── {"pins": [{"id": "...", "saves": 161, ...}]}
│
├── filtered_data.json     # AI 筛选后的最终数据
│
├── images/                # 下载的图片文件
│   ├── 161_0_pinid.jpg
│   └── ...
│
├── scraper.log            # 完整运行日志
│
└── debug/                 # （debug 模式）截图 + HTML
    ├── screenshot_001.png
    └── page_001.html
```

### 8.2 进度输出

```
子进程通过环境变量 PROGRESS_FILE 写入进度 JSON：
%TEMP%/pinterest_scraper_progress.json

{
    "running": true,
    "stage": "climbing",
    "percentage": 45,
    "current": 23,
    "total": 50,
    "query": "现代简约",
    "message": "已收集 23/50 个 pin",
    "output_dir": "output/现代简约_20260428_083720",
    "collected_count": 23
}
```

API 服务通过轮询 `/api/progress` 读取此文件。

---

## 9. 完整命令参考

### 9.1 CLI 直接运行

```bash
# 基础爬取（连接已有 Chrome，50 个 pin）
python main.py -q "现代简约" -n 50 --connect --auto-launch

# 带 saves 阈值 + 爬坡模式
python main.py -q "奶油风" -n 30 --min-saves 100 --climb-mode --connect --auto-launch

# 显示浏览器 + 调试 + 禁用 AI（排查用）
python main.py -q "原木风" -n 10 --connect --auto-launch --no-headless --debug --no-ai-filter

# 多 Worker 并行（不同终端各运行一个）
python main.py -q "现代简约" -n 50 --connect --auto-launch --worker-id worker-0
python main.py -q "现代简约" -n 50 --connect --auto-launch --worker-id worker-1
```

### 9.2 API 调用

```bash
# 异步启动爬取
curl -X POST http://localhost:8000/api/scrape/async \
  -H "Content-Type: application/json" \
  -d '{
    "query": "现代简约",
    "max_pins": 50,
    "min_saves": 100,
    "download_images": true,
    "worker_id": "worker-0"
  }'

# 查询进度
curl http://localhost:8000/api/progress

# 停止任务
curl -X POST http://localhost:8000/api/stop
```

---

## 10. 关键常量速查

| 常量 | 值 | 位置 | 说明 |
|------|-----|------|------|
| `BATCH_COLLECT_SIZE` | 5 | `scraper.py:38` | 批量 AI 收集池大小 |
| `max_depth` | 15 | `scraper.py:990` | 爬坡最大深度 |
| `max_attempts` | `target*10 或 50` | `scraper.py:988` | 外层最大尝试 |
| `max_search_scroll_rounds` | 10 | `scraper.py:991` | 搜索页最大滚动轮数 |
| `max_consecutive_recovery_failures` | 5 | `scraper.py:816` | 连续恢复失败阈值 |
| `ai_filter_timeout` | 180s | `main.py:158` | AI 筛选超时 |
| `PROGRESS_FILE` | `%TEMP%/pinterest_scraper_progress.json` | 系统临时目录 | 进程间进度通信 |
| AI 缓存 TTL | 86400s (24h) | `coordinator.py:155` | 筛选结果缓存有效期 |
| Worker 心跳 TTL | 60s | `coordinator.py:338` | 心跳过期时间 |
| 图片下载并发数 | 4 | `ollama_client.py` | ThreadPoolExecutor workers |
| AsyncAIWorker 线程数 | 2 | `async_ai_worker.py:52` | 后台 AI 线程池 |
| 相似推荐滚动轮数 | 8 | `scraper.py:1849` | 每轮最多检查 |
| 每轮相似检查数 | 5 | `scraper.py:1472` | 每轮爬坡最多检查 |

---

## 11. 异常恢复全景

```
┌───────────────────────────────────────────────────────┐
│                    异常 → 恢复策略                       │
├───────────────────┬───────────────────────────────────┤
│ 页面失效（eval     │ _is_page_alive() → 区分"导航中"    │
│ context destroyed）│ 与"真失效"，导航中等待 domcontent   │
├───────────────────┼───────────────────────────────────┤
│ 浏览器崩溃（CDP    │ _ensure_page_alive_and_on_search() │
│ socket hang up）   │ 新建页→重连CDP→重启浏览器           │
├───────────────────┼───────────────────────────────────┤
│ 多次恢复失败       │ consecutive_recovery_failures 计数器│
│                   │ ≥5 → 优雅退出，避免无限重试          │
├───────────────────┼───────────────────────────────────┤
│ 返回搜索页失败     │ _navigate_back_to_search() 三层兜底  │
│                   │ 弹窗关闭→浏览器后退→URL 直接跳转      │
├───────────────────┼───────────────────────────────────┤
│ AI Provider 429   │ 不重试，即时降级到下一个 provider     │
├───────────────────┼───────────────────────────────────┤
│ AI 全部失败        │ 入口筛选→不通过；收集筛选→默认通过    │
│                   │ 均写入缓存避免重复失败               │
├───────────────────┼───────────────────────────────────┤
│ Redis 不可用       │ 自动降级到 threading.Lock + 内存     │
│                   │ 功能受限但程序不崩溃                  │
├───────────────────┼───────────────────────────────────┤
│ 提取数据失败       │ 多种提取策略降级（PWS→DOM→aria→flex）│
│                   │ 每种失败自动尝试下一种                │
└───────────────────┴───────────────────────────────────┘
```

---

## 12. 文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `scraper.py` | ~3566 | 核心爬取引擎（PinterestScraper 类） |
| `main.py` | ~521 | CLI 入口 |
| `shared/coordinator.py` | ~430 | 多 Worker 协调器（Redis + 内存双模） |
| `shared/async_ai_worker.py` | ~346 | 异步 AI 筛选线程池 |
| `shared/prompt_templates.py` | ~291 | 三套 AI 提示词模板 + 动态匹配 |
| `shared/dynamic_prompt.py` | ~209 | LLM 生成动态视觉筛选清单 |
| `shared/ai_filter_manager.py` | ~380 | 多 Provider 降级管理器 |
| `shared/ollama_client.py` | ~200 | Ollama HTTP 客户端 |
| `shared/ollama_config.py` | ~155 | AI 配置管理 |
| `shared/doubao_client.py` | ~180 | 豆包/火山引擎视觉模型客户端 |
| `shared/zhipu_glm_client.py` | ~130 | 智谱 GLM 客户端 |
| `shared/nvidia_nim_client.py` | ~120 | NVIDIA NIM 客户端 |
| `shared/models.py` | ~160 | Pin 数据模型 + Redis 基础操作 |
| `shared/redis_config.py` | ~161 | Redis 配置管理 |
| `shared/config_manager.py` | - | 通用配置管理 |
| `shared/progress_state.py` | - | 进度状态 |
| `downloader.py` | - | 图片下载器 |
| `output.py` | - | JSON 输出处理 |
| `chrome_launcher.py` | - | Chrome 调试实例启动器 |
| `api_service_enhanced/service_main.py` | ~113 | FastAPI 入口 |
| `api_service_enhanced/task_manager.py` | ~397 | 子进程任务管理 |
| `api_service_enhanced/chrome_manager.py` | - | Chrome 生命周期管理 |
| `api_service_enhanced/routes/scrape.py` | ~108 | 爬取接口 |
| `api_service_enhanced/routes/status.py` | ~86 | 状态/进度接口 |
| `api_service_enhanced/routes/config.py` | ~173 | 配置接口 |
| `api_service_enhanced/routes/stop.py` | ~24 | 停止接口 |
| `api_service_enhanced/progress_tracker.py` | - | 进度追踪 |
| `ollama_config.json` | ~34 | AI Provider 配置 |
| `redis_config.json` | ~12 | Redis 连接配置 |
