# 爬虫扩展指南

## 概述

本文档指导你如何扩展多网站爬虫控制系统。你需要：

1. **创建新的爬虫类**：继承 `BaseScraper`
2. **注册网站**：在控制台注册新的网站
3. **配置路由**：API 支持动态路由

---

## 第一部分：创建新爬虫

### 1. 文件位置

```
scrapers/
├── __init__.py
├── base.py              # 基类
├── pinterest.py        # Pinterest 爬虫（现有）
└── your_site.py        # 新网站爬虫
```

### 2. 模板

```python
"""你的网站爬虫"""

import sys
import time
import random
from pathlib import Path
from typing import List, Dict, Any

from .base import BaseScraper

sys.path.insert(0, str(Path(__file__).parent.parent))


class YourSiteScraper(BaseScraper):
    """你的网站爬虫"""

    SITE_NAME = "yoursite"  # 唯一标识
    SITE_DISPLAY_NAME = "YourSite"  # 显示名称
    BASE_URL = "https://www.yoursite.com"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # ========================================
    # 必须实现的方法
    # ========================================

    def _get_search_url(self, keyword: str) -> str:
        """生成搜索页URL"""
        from urllib.parse import quote
        return f"{self.BASE_URL}/search?q={quote(keyword)}"

    def _extract_pin_ids_from_search(self) -> List[str]:
        """从搜索页提取内容ID"""
        js_code = """
        () => {
            const ids = new Set();
            // 根据实际页面结构调整选择器
            document.querySelectorAll('a[href*="/item/"]').forEach(a => {
                const match = a.href.match(/\/item\/([^\/]+)/);
                if (match) ids.add(match[1]);
            });
            return Array.from(ids);
        }
        """
        return self.page.evaluate(js_code) or []

    def _extract_details(self, content_id: str) -> Dict[str, Any]:
        """从详情页提取数据"""
        try:
            details = self.page.evaluate("""
            () => {
                // 根据实际页面结构调整
                const title = document.querySelector('h1')?.textContent || '';
                const desc = document.querySelector('.description')?.textContent || '';
                const img = document.querySelector('.main-image')?.src || '';
                const saves = parseInt(document.querySelector('.saves')?.textContent) || 0;
                
                return {
                    id: window.location.pathname.split('/').pop(),
                    title: title.trim(),
                    description: desc.trim(),
                    image_url: img,
                    saves: saves,
                    likes: 0,
                    comments: 0,
                    author: '',
                    is_video: false,
                    source: 'yoursite'
                };
            }
            """)
            return details if details and details.get('id') else None
        except Exception as e:
            if self.debug:
                print(f"提取详情失败: {e}")
            return None

    def _get_similar_ids(self) -> List[Dict[str, str]]:
        """获取相似内容推荐"""
        js_code = """
        () => {
            const similar = [];
            document.querySelectorAll('.similar-item').forEach(item => {
                const link = item.querySelector('a');
                if (link) {
                    const match = link.href.match(/\/item\/([^\/]+)/);
                    if (match) similar.push({ id: match[1] });
                }
            });
            return similar;
        }
        """
        return self.page.evaluate(js_code) or []

    def _get_media_type(self, content_id: str) -> bool:
        """判断是否为视频"""
        return self.page.evaluate("""
        () => !!document.querySelector('.video-player')
        """)

    def _close_modal(self) -> bool:
        """关闭弹窗"""
        try:
            close_btn = self.page.query_selector('.close-btn, [data-close]')
            if close_btn:
                close_btn.click()
                time.sleep(1)
                return True
        except:
            pass
        return False

    def _go_back(self) -> None:
        """返回上一页"""
        self.page.go_back()
        time.sleep(random.uniform(1.5, 2.5))

    def _scroll_page(self) -> bool:
        """滚动页面"""
        try:
            self.page.keyboard.press("End")
            return True
        except:
            return False

    # ========================================
    # 可选重写的方法
    # ========================================

    def _apply_stealth_mode(self):
        """反检测模式"""
        self.page.evaluate("""
        () => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        }
        """)

    def start(self):
        """启动浏览器（复用现有实现）"""
        # 参考 scraper.py 的启动逻辑
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self._own_browser = True

        if self.debug:
            self.page.on("console", lambda msg: print(f"[Browser] {msg.text}"))

        self._apply_stealth_mode()
```

---

## 第二部分：注册网站到控制台

### 1. 修改 console_gui.py

在 `ScraperConsole` 类中添加新网站选项：

```python
# 在 _create_input_panel 中添加网站选择
ttk.Label(input_frame, text="网站:").grid(row=0, column=0, sticky="w", pady=5)
self.website_var = tk.StringVar(value="pinterest")
website_menu = ttk.OptionMenu(
    input_frame,
    self.website_var,
    "pinterest",
    "pinterest",  # Pinterest
    "yoursite",   # 添加新网站
)
website_menu.grid(row=0, column=1, sticky="ew", pady=5, padx=(5, 0))
```

### 2. 修改 _start_scrape 方法

```python
def _start_scrape(self):
    website = self.website_var.get()
    query = self.query_entry.get()

    # 根据网站选择对应的爬虫
    if website == "pinterest":
        from scraper import PinterestScraper
        scraper_class = PinterestScraper
    elif website == "yoursite":
        from scrapers.yoursite import YourSiteScraper
        scraper_class = YourSiteScraper
    else:
        messagebox.showerror("错误", f"不支持的网站: {website}")
        return

    # 启动爬取...
```

---

## 第三部分：API 路由扩展

### 1. 修改 routes/scrape.py

```python
# 在 scrape.py 中添加动态路由

SCRAPER_REGISTRY = {
    "pinterest": "scraper.PinterestScraper",
    "yoursite": "scrapers.yoursite.YourSiteScraper",
}

@router.post("/scrape/{website}")
async def scrape_multi_website(website: str, req: ScrapeRequest):
    """多网站爬取"""
    if website not in SCRAPER_REGISTRY:
        raise HTTPException(status_code=400, detail=f"不支持的网站: {website}")

    # 动态导入并调用对应的爬虫
    # ...
```

---

## 第四部分：UI 多窗口支持

### 概念设计

```
主窗口（控制台）
├── [Tab1] Pinterest 爬虫
├── [Tab2] YourSite 爬虫
├── [Tab3] ...
└── [设置] 全局配置
```

### 实现思路

```python
class MultiSiteConsole:
    """多网站控制台"""

    def __init__(self):
        self.tabs = {}
        self.current_site = None

    def add_site(self, site_name: str, display_name: str):
        """添加网站标签页"""
        tab = SiteTab(site_name, display_name)
        self.tabs[site_name] = tab
        return tab

    def switch_site(self, site_name: str):
        """切换网站"""
        self.current_site = site_name
        # 更新UI显示
```

---

## 第五部分：清单

创建新网站爬虫时，需要确认以下内容：

### 必需实现

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `_get_search_url()` | 生成搜索页URL | str |
| `_extract_pin_ids_from_search()` | 提取内容ID列表 | List[str] |
| `_extract_details()` | 提取详情数据 | Dict |
| `_get_similar_ids()` | 获取相似推荐 | List[Dict] |
| `_get_media_type()` | 判断媒体类型 | bool |
| `_close_modal()` | 关闭弹窗 | bool |
| `_go_back()` | 返回上一页 | None |
| `_scroll_page()` | 滚动页面 | bool |

### 详情数据格式

```python
{
    "id": str,           # 内容ID
    "title": str,        # 标题
    "description": str,  # 描述
    "image_url": str,    # 原图URL
    "image_url_736x": str,  # 缩略图
    "saves": int,        # 收藏数
    "likes": int,        # 点赞数
    "comments": int,     # 评论数
    "author": str,       # 作者
    "is_video": bool,    # 是否视频
    "video_url": str,    # 视频URL
    "source": str,       # 来源标识
}
```

### 可选重写

| 方法 | 说明 |
|------|------|
| `_apply_stealth_mode()` | 自定义反检测逻辑 |
| `start()` | 自定义浏览器启动 |
| `_get_search_page_ids()` | 自定义搜索页ID提取 |

---

## 第六部分：测试

### 1. 单元测试

```python
def test_yoursite_scraper():
    scraper = YourSiteScraper(debug=True)
    with scraper:
        results = scraper.search("test keyword", max_count=5)
        assert len(results) > 0
        assert results[0]["id"]
```

### 2. 集成测试

```bash
python -c "from scrapers.yoursite import YourSiteScraper; print('Import OK')"
```

---

## 文件结构

```
pinterest-scraper/
├── scrapers/
│   ├── __init__.py
│   ├── base.py           # 通用爬虫基类
│   ├── pinterest.py     # Pinterest 爬虫
│   └── yoursite.py      # 你的新网站爬虫
├── tray_app/
│   ├── console_gui.py   # 控制台（修改添加多网站支持）
│   └── ...
├── api_service_enhanced/
│   └── routes/
│       └── scrape.py    # API（添加动态路由）
└── main.py              # CLI（保持不变）
```

---

## 示例：新网站扩展清单

- [ ] 在 `scrapers/` 创建 `yoursite.py`
- [ ] 实现所有必需方法
- [ ] 测试导入：`python -c "from scrapers.yoursite import YourSiteScraper"`
- [ ] 测试爬取：单个内容ID提取
- [ ] 测试搜索：收集10个内容
- [ ] 在控制台添加网站选择
- [ ] 在 API 添加路由
- [ ] 更新文档
