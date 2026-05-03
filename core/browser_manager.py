"""统一浏览器管理器

集中管理 Playwright 浏览器实例的创建、连接和销毁。
支持两种模式:
  1. 自有模式: 启动新的 Chromium 实例
  2. CDP 模式: 连接已运行的 Chrome 调试端口

所有插件通过此管理器获取浏览器上下文，避免重复代码。
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
"""

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class BrowserManager:
    """统一浏览器管理器"""

    def __init__(self, headless: bool = True, debug: bool = False):
        self.headless = headless
        self.debug = debug
        self._playwright = None
        self._browser = None
        self._contexts: Dict[str, Any] = {}
        self._own_browser = False

    def start(self, cdp_endpoint: Optional[str] = None,
              chrome_profile: Optional[str] = None) -> None:
        """启动浏览器

        Args:
            cdp_endpoint: Chrome DevTools Protocol 端点 (如 http://localhost:9222)
            chrome_profile: Chrome 用户配置目录路径
        """
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()

        if cdp_endpoint:
            self._connect_cdp(cdp_endpoint)
        else:
            self._launch_browser(chrome_profile)

    def _connect_cdp(self, endpoint: str) -> None:
        """通过 CDP 连接已有浏览器"""
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(endpoint)
            self._own_browser = False
            logger.info(f"已通过 CDP 连接浏览器: {endpoint}")
        except Exception as e:
            logger.error(f"CDP 连接失败: {e}")
            raise

    def _launch_browser(self, chrome_profile: Optional[str] = None) -> None:
        """启动新的 Chromium 实例"""
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--lang=zh-CN",
        ]
        if chrome_profile:
            args.append(f"--user-data-dir={chrome_profile}")

        launch_kwargs = {
            "headless": self.headless,
            "args": args,
        }
        if not self.headless:
            launch_kwargs["slow_mo"] = 100

        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        self._own_browser = True
        logger.info("已启动新浏览器实例")

    def create_context(self, context_id: str = "default",
                       storage_state: Optional[Dict] = None,
                       user_agent: Optional[str] = None,
                       viewport: Optional[Dict] = None) -> Any:
        """创建浏览器上下文

        Args:
            context_id: 上下文标识（用于管理多个上下文）
            storage_state: Playwright storage_state 字典
            user_agent: 自定义 User-Agent
            viewport: 视口大小 {"width": 1280, "height": 900}

        Returns:
            BrowserContext 实例
        """
        kwargs: Dict[str, Any] = {
            "user_agent": user_agent or DEFAULT_USER_AGENT,
            "viewport": viewport or {"width": 1280, "height": 900},
        }

        if storage_state:
            state_file = Path("cookiesFile") / f"_ctx_{context_id}_state.json"
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(storage_state, ensure_ascii=False), encoding="utf-8")
            kwargs["storage_state"] = str(state_file)

        context = self._browser.new_context(**kwargs)
        context.add_init_script(STEALTH_JS)
        self._contexts[context_id] = context
        logger.info(f"已创建浏览器上下文: {context_id}")
        return context

    def get_context(self, context_id: str = "default") -> Optional[Any]:
        """获取已有上下文"""
        return self._contexts.get(context_id)

    def close_context(self, context_id: str) -> None:
        """关闭指定上下文"""
        ctx = self._contexts.pop(context_id, None)
        if ctx:
            try:
                ctx.close()
            except Exception:
                pass

    def stop(self) -> None:
        """停止浏览器并释放资源"""
        for cid in list(self._contexts.keys()):
            self.close_context(cid)

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
        logger.info("浏览器已关闭")

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
