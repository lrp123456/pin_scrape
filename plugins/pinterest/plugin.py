"""Pinterest 爬虫插件

实现 ScraperPlugin 接口，组合:
  - PinterestAuth: 认证管理
  - PinterestNavigator: 页面导航
  - PinterestExtractor: 数据提取
  - PinterestCollector: 收集与筛选
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from core.plugin_interface import PluginInfo, ScraperPlugin, ScrapeResult, TaskStatus
from shared.models import Pin
from plugins.pinterest.auth import PinterestAuth
from plugins.pinterest.navigator import PinterestNavigator
from plugins.pinterest.extractor import PinterestExtractor
from plugins.pinterest.collector import PinterestCollector

logger = logging.getLogger(__name__)


class PinterestPlugin(ScraperPlugin):
    """Pinterest 爬虫插件

    通过插件接口统一管理 Pinterest 爬取流程。
    """

    BASE_URL = "https://kr.pinterest.com/search/pins/"

    def __init__(self, **kwargs):
        self.headless = kwargs.get("headless", True)
        self.debug = kwargs.get("debug", False)
        self.cdp_endpoint = kwargs.get("cdp_endpoint")
        self.media_type = kwargs.get("media_type", "all")
        self.worker_id = kwargs.get("worker_id", "worker-0")
        self.enable_ai_filter = kwargs.get("ai_filter", True)
        self.user_data_dir = kwargs.get("user_data_dir")
        self.proxy_server = kwargs.get("proxy_server")

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._own_browser = True

        self._auth: Optional[PinterestAuth] = None
        self._nav: Optional[PinterestNavigator] = None
        self._ext: Optional[PinterestExtractor] = None
        self._collector: Optional[PinterestCollector] = None

        self._cancelled = False
        self._status: Dict[str, Any] = {"state": "idle"}

    @classmethod
    def info(cls) -> PluginInfo:
        return PluginInfo(
            name="pinterest",
            version="2.0.0",
            description="Pinterest 图片爬虫（插件化架构）",
            supported_sites=["pinterest.com", "kr.pinterest.com"],
            config_schema={
                "max_pins": {"type": "int", "default": 100},
                "min_saves": {"type": "int", "default": 0},
                "climb_mode": {"type": "bool", "default": False},
                "ai_filter": {"type": "bool", "default": True},
                "headless": {"type": "bool", "default": True},
                "workers": {"type": "int", "default": 1},
            },
        )

    @classmethod
    def validate_config(cls, config: Dict[str, Any]) -> bool:
        required_keys = []
        for key in required_keys:
            if key not in config:
                return False
        return True

    @classmethod
    def default_config(cls) -> Dict[str, Any]:
        return {
            "max_pins": 100,
            "min_saves": 0,
            "climb_mode": False,
            "ai_filter": True,
            "headless": True,
            "workers": 1,
        }

    def start(self) -> None:
        """启动浏览器和子模块"""
        self._playwright = sync_playwright().start()

        if self.cdp_endpoint:
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_endpoint)
            self._own_browser = False
        else:
            args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--lang=zh-CN",
            ]
            if self.user_data_dir:
                args.append(f"--user-data-dir={self.user_data_dir}")

            launch_kwargs = {"headless": self.headless, "args": args}
            if not self.headless:
                launch_kwargs["slow_mo"] = 100

            self._browser = self._playwright.chromium.launch(**launch_kwargs)
            self._own_browser = True

        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        stealth_js = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        window.chrome = {runtime: {}};
        """
        self._context.add_init_script(stealth_js)

        self._page = self._context.new_page()

        self._auth = PinterestAuth(self._page, self._context, self.worker_id, self.debug)
        self._nav = PinterestNavigator(self._page, self.debug)
        self._ext = PinterestExtractor(self._page, self.debug)
        self._collector = PinterestCollector(
            self._page, self._nav, self._ext, self.debug, self.worker_id
        )

        self._status = {"state": "ready"}
        logger.info(f"[{self.worker_id}] Pinterest 插件已启动")

    def stop(self) -> None:
        """停止并释放资源"""
        if self._auth:
            self._auth.save_cookie_state()
            self._auth.release_cookie()

        if self._own_browser and self._browser:
            try:
                self._browser.close()
            except Exception:
                pass

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

        self._browser = None
        self._playwright = None
        self._context = None
        self._page = None
        self._status = {"state": "stopped"}
        logger.info(f"[{self.worker_id}] Pinterest 插件已停止")

    def run(self, task_config: Dict[str, Any],
            progress_callback: Optional[Callable] = None) -> ScrapeResult:
        """执行爬取任务

        Args:
            task_config: 任务配置，需包含:
                - query: 搜索关键词
                - max_pins: 最大收集数量 (默认 100)
                - min_saves: 最小收藏数 (默认 0)
                - climb_mode: 爬坡模式 (默认 False)
                - output_dir: 输出目录
            progress_callback: 进度回调

        Returns:
            爬取结果
        """
        query = task_config.get("query", "")
        max_pins = task_config.get("max_pins", 100)
        min_saves = task_config.get("min_saves", 0)
        climb_mode = task_config.get("climb_mode", False)
        output_dir = task_config.get("output_dir", f"output/{query}")

        if not query:
            return ScrapeResult(status=TaskStatus.FAILED, error="缺少搜索关键词")

        self._cancelled = False
        self._status = {"state": "running", "query": query}

        try:
            if progress_callback:
                progress_callback("auth", 0, 1, f"[{self.worker_id}] 检查登录状态...")

            if self._auth.check_login_required():
                storage_state = self._auth.load_cookie_from_db()
                if storage_state:
                    self._auth.inject_cookies(storage_state)
                    self._page.goto("https://kr.pinterest.com/", wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2)
                    if self._auth.check_login_required():
                        self._auth.launch_login_browser()

            if progress_callback:
                progress_callback("search", 0, 1, f"[{self.worker_id}] 搜索: {query}")

            self._nav.navigate_to_search(query)
            self._nav.wait_for_content()

            if progress_callback:
                progress_callback("collecting", 0, max_pins, f"[{self.worker_id}] 收集Pin...")

            collected = self._collector.scroll_and_collect(max_pins, query, progress_callback)

            if climb_mode and collected:
                if progress_callback:
                    progress_callback("exploring", 0, len(collected), f"[{self.worker_id}] 爬坡探索...")

                similar = self._collector.explore_similar_pins(collected, progress_callback=progress_callback)
                collected.extend(similar)

            if self.enable_ai_filter and collected:
                if progress_callback:
                    progress_callback("filtering", 0, len(collected), f"[{self.worker_id}] AI筛选...")

                collected = self._collector.batch_filter(collected, query, progress_callback)

            if min_saves > 0:
                collected = [p for p in collected if (p.saves or 0) >= min_saves]

            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            result_data = [p.to_dict() if hasattr(p, "to_dict") else vars(p) for p in collected]
            json_file = output_path / "pins.json"
            json_file.write_text(
                json.dumps({"query": query, "total": len(result_data), "items": result_data},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self._status = {"state": "completed", "query": query, "count": len(collected)}

            return ScrapeResult(
                items=result_data,
                total_found=len(collected),
                total_collected=len(collected),
                output_dir=str(output_path),
                status=TaskStatus.COMPLETED,
            )

        except Exception as e:
            logger.error(f"[{self.worker_id}] 任务失败: {e}")
            self._status = {"state": "failed", "error": str(e)}
            return ScrapeResult(status=TaskStatus.FAILED, error=str(e))

    def get_status(self) -> Dict[str, Any]:
        return self._status.copy()

    def cancel(self) -> None:
        self._cancelled = True
        self._status = {"state": "cancelled"}
