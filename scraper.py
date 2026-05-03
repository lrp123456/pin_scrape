"""Pinterest 搜索爬虫"""

import json
import logging
import os
import random
import signal
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Callable, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from shared.models import Pin

try:
    from shared.cookie_manager import CookieManager
    _cookie_manager_available = True
    COOKIES_DIR = Path(__file__).parent / "cookiesFile"
except ImportError:
    _cookie_manager_available = False
    COOKIES_DIR = None

# AI 筛选模块（可选，如果配置启用）
try:
    from shared.ai_filter_manager import AIFilterManager
    from shared.ollama_config import get_ollama_config
    _ai_filter_available = True
except ImportError:
    _ai_filter_available = False

# 多 Worker 协调模块（可选）
try:
    from shared.coordinator import ScrapeCoordinator
    from shared.async_ai_worker import AsyncAIWorker
    _coordinator_available = True
except ImportError:
    _coordinator_available = False

# 全局停止标志
_stop_requested = False

# 批量 AI 收集筛选批次大小（一次 API 调用评估多张图）
BATCH_COLLECT_SIZE = 5


def setup_logging(log_file: str = None):
    """配置日志：同时输出到控制台和文件"""
    logger = logging.getLogger("pinterest_scraper")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 默认 logger
logger = logging.getLogger("pinterest_scraper")


def signal_handler(signum, frame):
    """处理停止信号"""
    global _stop_requested
    print("\n⚠️  收到停止信号，正在安全退出...")
    _stop_requested = True
    # 使用 os._exit(1) 强制退出，避免 Playwright 阻塞导致无法退出
    os._exit(1)


# 注册信号处理器
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def apply_stealth(page: Page):
    """应用 stealth 模式隐藏自动化特征"""
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'permissions', {
            get: () => ({
                query: () => Promise.resolve({ state: 'granted' })
            })
        });
    """)


class PinterestScraper:
    """Pinterest 搜索爬虫"""

    BASE_URL = "https://kr.pinterest.com/search/pins/"

    def __init__(
        self,
        headless: bool = True,
        debug: bool = False,
        cdp_endpoint: str = None,
        progress_callback: Callable[[str, int, int, str], None] = None,
        media_type: str = "all",
        log_file: str = None,
        user_data_dir: str = None,
        enable_ai_filter: bool = True,
        ai_filter_timeout: int = 180,
        worker_id: str = "worker-0",
        proxy_server: str = None,
    ):
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.progress_callback = progress_callback
        self.media_type = media_type
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
        self._own_browser = True
        self.log_file = log_file
        self.user_data_dir = user_data_dir
        self.enable_ai_filter = enable_ai_filter
        self.ai_filter_timeout = ai_filter_timeout
        self.worker_id = worker_id
        self.proxy_server = proxy_server
        self._ai_available = False
        self._coordinator: Optional["ScrapeCoordinator"] = None
        self._async_ai: Optional["AsyncAIWorker"] = None
        self._search_page_url: Optional[str] = None
        self._search_image_map: dict = {}
        self._cookie_manager: Optional["CookieManager"] = None
        self._cookie_account_id: Optional[int] = None
        self._setup_logger()
        self._init_cookie_manager()
        self._init_ai_filter()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _is_page_alive(self) -> bool:
        """检查页面是否仍然存活且有效

        注意：页面正在导航（navigating）不算失效，只是暂时不可用。
        这与页面/浏览器真正关闭是不同的情况，需要区分处理。

        Returns:
            True - 页面可用，False - 页面已关闭或失效
        """
        if not self.page:
            return False
        try:
            self.page.evaluate("1")
            return True
        except Exception as e:
            error_msg = str(e)
            # 页面正在导航中（Pinterest 可能在自动刷新），不算真正失效
            if "navigation" in error_msg.lower() or "execution context was destroyed" in error_msg.lower():
                self.logger.debug(f"[_is_page_alive] 页面正在导航中（非真正失效）: {e}")
                # 等待导航完成，最多等 5 秒
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=5000)
                    self.page.evaluate("1")
                    self.logger.debug("[_is_page_alive] 导航完成后页面恢复")
                    return True
                except Exception:
                    self.logger.warning(f"[_is_page_alive] 导航等待后页面仍无效: {e}")
                    return False
            # 其他错误：页面可能真正失效
            self.logger.debug(f"[_is_page_alive] 页面无效: {e}")
            return False

    def _ensure_page_alive_and_on_search(self, keyword: str = None) -> bool:
        """确保页面存活且在搜索页，如果失效则尝试恢复

        恢复策略（逐层递进）：
        1. 当前浏览器中新建页面
        2. 重连 CDP（连接模式）
        3. Playwright 启动新浏览器（最后手段，连接/自有模式均适用）

        Args:
            keyword: 搜索关键词，用于重新导航

        Returns:
            True - 页面可用，False - 无法恢复
        """
        if self._is_page_alive():
            if "/search/" in self.page.url:
                return True
            if keyword:
                try:
                    self.logger.info("[ensure_page_alive] 当前不在搜索页，尝试返回...")
                    self._navigate_back_to_search(keyword)
                    return self._is_page_alive()
                except Exception:
                    pass
            return True

        self.logger.warning("[ensure_page_alive] 页面已失效，尝试恢复...")

        # ── 第1层：当前浏览器中新建页面 ──
        try:
            if self.browser and keyword:
                search_url = f"https://www.pinterest.com/search/pins/?q={keyword}"
                self.logger.info(f"[ensure_page_alive] 尝试在当前浏览器中新建页面: {keyword}")
                self.page = self.browser.new_page()
                self.page.goto(search_url, timeout=30000)
                time.sleep(random.uniform(5, 8))
                apply_stealth(self.page)
                if self._is_page_alive():
                    self.logger.info("[ensure_page_alive] 新建页面成功，已恢复")
                    return True
        except Exception as e:
            self.logger.warning(f"[ensure_page_alive] 新建页面失败 ({e})，尝试重连浏览器...")

        # ── 第2层：重连 CDP（仅连接模式） ──
        if self.cdp_endpoint and keyword:
            try:
                self.logger.info(f"[ensure_page_alive] 尝试重连 CDP: {self.cdp_endpoint}")
                self.browser = self._playwright.chromium.connect_over_cdp(
                    self.cdp_endpoint
                )
                contexts = self.browser.contexts
                if contexts:
                    self.context = contexts[0]
                else:
                    self.context = self.browser.new_context()
                self.page = self.context.new_page()

                search_url = f"https://www.pinterest.com/search/pins/?q={keyword}"
                self.logger.info(f"[ensure_page_alive] 重连成功，导航到搜索页: {keyword}")
                self.page.goto(search_url, timeout=30000)
                time.sleep(random.uniform(5, 8))
                apply_stealth(self.page)
                if self._is_page_alive():
                    self.logger.info("[ensure_page_alive] 重连浏览器成功，已恢复")
                    return True
            except Exception as e:
                self.logger.error(f"[ensure_page_alive] 重连 CDP 失败: {e}")

        # ── 第3层：Playwright 启动新浏览器（最后手段，连接/自有模式均适用） ──
        if keyword:
            try:
                self.logger.info("[ensure_page_alive] 尝试用 Playwright 启动新浏览器（最后手段）...")

                # 优先使用持久化上下文（保留登录状态），失败则退回到普通启动
                if self.user_data_dir:
                    try:
                        self.context = self._playwright.chromium.launch_persistent_context(
                            user_data_dir=self.user_data_dir,
                            headless=self.headless,
                            args=[
                                "--disable-blink-features=AutomationControlled",
                                "--no-sandbox",
                                "--disable-setuid-sandbox",
                            ],
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            viewport={"width": 1920, "height": 1080},
                        )
                        self.browser = self.context.browser
                        pages = self.context.pages
                        self.page = pages[0] if pages else self.context.new_page()
                        self.logger.info("[ensure_page_alive] 使用持久化上下文启动浏览器（保留登录状态）")
                    except Exception as persist_err:
                        self.logger.warning(
                            f"[ensure_page_alive] 持久化上下文失败 ({persist_err})，退回到普通启动"
                        )
                        self.browser = self._playwright.chromium.launch(
                            headless=self.headless,
                            args=[
                                "--disable-blink-features=AutomationControlled",
                                "--no-sandbox",
                            ],
                        )
                        self.context = self.browser.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            viewport={"width": 1920, "height": 1080},
                        )
                        self.page = self.context.new_page()
                else:
                    self.browser = self._playwright.chromium.launch(
                        headless=self.headless,
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                        ],
                    )
                    self.context = self.browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080},
                    )
                    self.page = self.context.new_page()

                # 导航到搜索页
                search_url = f"https://www.pinterest.com/search/pins/?q={keyword}"
                self.logger.info(f"[ensure_page_alive] 导航到搜索页: {keyword}")
                self.page.goto(search_url, timeout=30000)
                time.sleep(random.uniform(5, 8))
                apply_stealth(self.page)

                if self._is_page_alive():
                    # 标记为自己启动的浏览器，close() 时正确清理
                    self._own_browser = True
                    self.cdp_endpoint = None  # 清空 CDP 端点，已切换到新浏览器
                    self.logger.info("[ensure_page_alive] Playwright 启动新浏览器成功，已恢复")
                    return True
                else:
                    self.logger.error("[ensure_page_alive] Playwright 启动浏览器后页面仍无效")
            except Exception as e:
                self.logger.error(f"[ensure_page_alive] Playwright 启动浏览器失败: {e}")

        self.logger.error("[ensure_page_alive] 所有恢复方式均失败")
        return False

    def _safe_go_back(self, fallback_url: str = None) -> bool:
        """安全地执行浏览器后退，如果失败则尝试恢复

        Args:
            fallback_url: 后退失败时的回退导航URL

        Returns:
            True - 成功，False - 失败
        """
        if not self._is_page_alive():
            self.logger.warning("[safe_go_back] 页面已失效，跳过后退")
            return False

        try:
            self.page.go_back()
            time.sleep(random.uniform(2, 3))

            # 检查后退后页面是否仍然有效
            if not self._is_page_alive():
                self.logger.warning("[safe_go_back] 后退后页面失效")
                return False

            current_url = self.page.url
            # 如果退到了 about:blank 或 chrome 内部页面，说明历史栈异常
            if current_url in ("about:blank", "") or current_url.startswith(("chrome://", "edge://", "data:")):
                self.logger.warning(f"[safe_go_back] 后退到异常页面: {current_url}")
                if fallback_url:
                    self.logger.info(f"[safe_go_back] 尝试导航到回退URL: {fallback_url}")
                    self.page.goto(fallback_url)
                    time.sleep(3)
                return False

            return True
        except Exception as e:
            self.logger.warning(f"[safe_go_back] 后退出错: {e}")
            if fallback_url and self._is_page_alive():
                try:
                    self.page.goto(fallback_url)
                    time.sleep(3)
                    return True
                except Exception as nav_err:
                    self.logger.error(f"[safe_go_back] 回退导航也失败: {nav_err}")
            return False

    def _ensure_page_alive(self, fallback_url: str = None) -> bool:
        """确保页面存活，如果失效尝试恢复

        Args:
            fallback_url: 页面失效时的回退导航URL

        Returns:
            True - 页面可用，False - 无法恢复
        """
        if self._is_page_alive():
            return True

        self.logger.warning("[ensure_page_alive] 页面已失效")
        if fallback_url and self.page:
            try:
                self.logger.info(f"[ensure_page_alive] 尝试重新导航到: {fallback_url}")
                self.page.goto(fallback_url)
                time.sleep(3)
                return self._is_page_alive()
            except Exception as e:
                self.logger.error(f"[ensure_page_alive] 重新导航失败: {e}")
        return False

    def _setup_logger(self):
        """配置日志记录器"""
        self.logger = logging.getLogger(f"pinterest_scraper.{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        if self.log_file:
            file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def _init_cookie_manager(self):
        """初始化 Cookie 管理器，为当前 Worker 分配账号"""
        if not _cookie_manager_available:
            self.logger.warning("[Cookie] CookieManager 模块不可用，使用传统模式")
            return

        try:
            self._cookie_manager = CookieManager()
            account = self._cookie_manager.get_account_for_worker(self.worker_id)
            if account:
                self._cookie_account_id = account["id"]
                status_label = {1: "有效", 0: "失效", -1: "待登录"}.get(account["status"], "未知")
                self.logger.info(
                    f"[Cookie] Worker {self.worker_id} 分配到账号 #{account['id']} "
                    f"(标签={account['label']}, 状态={status_label})"
                )
            else:
                new_id = self._cookie_manager.add_account(label=f"auto_{self.worker_id}")
                self._cookie_account_id = new_id
                self._cookie_manager.get_account_for_worker(self.worker_id)
                self.logger.info(
                    f"[Cookie] Worker {self.worker_id} 无可用账号，已创建待登录账号 #{new_id}"
                )
        except Exception as e:
            self.logger.warning(f"[Cookie] CookieManager 初始化失败: {e}")
            self._cookie_manager = None

    def _init_ai_filter(self):
        """初始化 AI 筛选模块"""
        if not self.enable_ai_filter:
            self.logger.warning("[AI筛选] 已通过参数禁用，跳过初始化")
            self._ai_available = False
            return

        if not _ai_filter_available:
            self.logger.warning("[AI筛选] AI 筛选模块导入失败，AI 筛选不可用")
            self._ai_available = False
            return

        try:
            config = get_ollama_config()
            if not config.enabled:
                self.logger.warning("[AI筛选] 配置中 enabled=False，AI 筛选已禁用")
                self._ai_available = False
                return

            self._ai_manager = AIFilterManager(timeout=self.ai_filter_timeout)
            self._ai_available = True
        except Exception as e:
            self.logger.warning(f"[AI筛选] 初始化失败: {e}，AI 筛选将降级处理")
            self._ai_available = False

    def start(self):
        """启动浏览器"""
        self._playwright = sync_playwright().start()

        if self.cdp_endpoint:
            # 连接到已有的 Chrome 浏览器
            self.logger.info(f"正在连接到已有浏览器: {self.cdp_endpoint}")
            try:
                self.browser = self._playwright.chromium.connect_over_cdp(
                    self.cdp_endpoint
                )
                self._own_browser = False
                self.logger.info("成功连接到已有浏览器")

                # 获取现有的上下文和页面
                contexts = self.browser.contexts
                if contexts:
                    self.context = contexts[0]
                    pages = self.context.pages
                    if pages:
                        candidate_page = pages[0]
                        # 检查页面是不是 Chrome 内部特殊页面（如 chrome://omnibox-popup）
                        if candidate_page.url.startswith('http'):
                            # 正常HTTP页面，复用它，避免反爬检测
                            self.page = candidate_page
                            self.logger.info(f"复用已有正常页面: {self.page.url}")
                        else:
                            # 内部特殊页面，新建页面
                            self.page = self.context.new_page()
                            self.logger.info(f"检测到内部特殊页面 {candidate_page.url}，新建正常页面")
                    else:
                        self.page = self.context.new_page()
                else:
                    self.context = self.browser.new_context()
                    self.page = self.context.new_page()

                self.page.set_viewport_size({"width": 1920, "height": 1080})
                self.logger.info(f"已设置视口大小: 1920x1080")

                # CDP 连接模式下注入 Cookie
                if self._cookie_manager and self._cookie_account_id:
                    state = self._cookie_manager.load_storage_state(self._cookie_account_id)
                    if state and state.get("cookies"):
                        self._inject_cookies_to_context(state)
                        self.logger.info(
                            f"[Cookie] CDP模式：已注入 {len(state.get('cookies', []))} 个 cookie"
                        )
                    else:
                        self.logger.info("[Cookie] CDP模式：数据库中无有效 cookie")

                apply_stealth(self.page)
                self.logger.info("已启用 stealth 模式 (连接模式)")

                # CDP 模式下，注入 Cookie 后导航到 Pinterest 首页以触发 Cookie 生效
                self.logger.info("[Cookie] 导航到 Pinterest 首页以激活 Cookie...")
                self.page.goto("https://www.pinterest.com/", timeout=30000)
                time.sleep(2)

                # 检查登录状态
                if self._check_login_required():
                    self.logger.warning("[Cookie] Cookie 无效，需要重新登录")
                else:
                    self.logger.info("[Cookie] Cookie 有效，已成功登录")

            except Exception as e:
                self.logger.error(f"连接失败: {e}")
                self.logger.error("请确保 Chrome 已以调试模式启动:")
                self.logger.error("  chrome.exe --remote-debugging-port=9222")
                raise
        else:
            # 启动新的浏览器
            self._own_browser = True

            # 尝试从 CookieManager 加载 storage_state
            storage_state_path = None
            if self._cookie_manager and self._cookie_account_id:
                state = self._cookie_manager.load_storage_state(self._cookie_account_id)
                if state and state.get("cookies"):
                    state_file = Path(self._cookie_manager.get_all_accounts()[0]["full_path"]).parent / f"_worker_{self.worker_id}_state.json"
                    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                    storage_state_path = str(state_file)
                    self.logger.info(f"[Cookie] 已加载 storage_state，包含 {len(state.get('cookies', []))} 个 cookie")
                else:
                    self.logger.info("[Cookie] 数据库中无有效 cookie，将使用空状态启动")

            if storage_state_path:
                self.browser = self._playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                self.context = self.browser.new_context(
                    storage_state=storage_state_path,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
            else:
                self.browser = self._playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                self.context = self.browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
            self.page = self.context.new_page()

            apply_stealth(self.page)
            self.logger.info("已启用 stealth 模式")

        self.page.set_default_timeout(60000)

        # 从Redis加载已收集的Pin ID到内存（避免频繁创建Redis连接）
        from shared.models import init_collected_ids_from_redis, get_redis_client

        init_collected_ids_from_redis()
        redis_client = get_redis_client()
        if redis_client is not None:
            self.logger.info("[Redis] 已连接，去重数据将持久化")
        else:
            self.logger.warning("[Redis] 未连接，使用内存去重模式（重启后数据丢失）")

    def close(self):
        """关闭浏览器，安全处理各组件（任一失败不影响其他组件的清理）"""
        # 保存当前浏览器的 storage_state 到数据库
        self._save_cookie_state()

        if self._own_browser:
            # 只关闭自己启动的浏览器（含恢复后自动启动的浏览器）
            try:
                if self.page:
                    self.page.close()
            except Exception:
                pass
            try:
                if self.context:
                    self.context.close()
            except Exception:
                pass
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                pass
        else:
            # 连接的浏览器，只关闭页面，不关闭浏览器
            try:
                if self.page:
                    self.page.close()
            except Exception:
                pass
            self.logger.info("保持浏览器运行（连接模式）")

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

    def search(
        self,
        keyword: str,
        max_pins: int = 100,
        min_saves: int = 0,
        progress_callback: Callable[[str, int, int, str], None] = None,
        climb_mode: bool = False,
        media_type: str = "all",  # all, images, videos
    ) -> List[Pin]:
        if not self.page:
            raise RuntimeError("浏览器未启动，请先调用 start() 或使用 with 语句")

        if progress_callback is not None:
            self.progress_callback = progress_callback

        self.media_type = media_type

        # 进度回调：开始搜索
        if self.progress_callback:
            self.progress_callback("searching", 0, max_pins, f"开始搜索: {keyword}")

        self._current_keyword = keyword

        # ── 多 Worker 协调器 ──
        # 每个查询创建独立的协调器，Worker 之间通过 Redis 竞争入口队列
        if _coordinator_available:
            try:
                self._coordinator = ScrapeCoordinator(keyword, worker_id=self.worker_id)
                # 清除上次运行残留的任务终止标记
                self._coordinator.clear_task_complete()
                self.logger.info(
                    f"[协调器] 已创建，Worker={self.worker_id}, "
                    f"已收集={self._coordinator.collected_count()}, "
                    f"入口队列={self._coordinator.entry_queue_size()}"
                )
                # 如果 AI 可用，也创建异步 AI 工作池
                if self._ai_available:
                    self._async_ai = AsyncAIWorker(
                        self._ai_manager, self._coordinator, max_workers=2
                    )
                    self.logger.info(f"[异步AI] 工作池已启动")
            except Exception as e:
                self.logger.warning(f"[协调器] 创建失败，使用独立模式: {e}")
                self._coordinator = None
                self._async_ai = None

        # 动态提示词：将查询词转化为详细视觉筛选清单（首次评估前生成）
        if self._ai_available:
            try:
                success = self._ai_manager.generate_dynamic_criteria(keyword)
                if success:
                    from shared.prompt_templates import PromptGenerator
                    crit_data = PromptGenerator._resolve_template(keyword)
                    criteria_text = crit_data.get("criteria", "")
                    keywords = crit_data.get("style_keywords", [])
                    negative = crit_data.get("negative_examples", "")
                    self.logger.info(
                        f"[动态提示词] ✓ 已为「{keyword}」生成视觉筛选标准"
                    )
                    self.logger.info(f"[动态提示词] 关键词: {', '.join(keywords)}")
                    self.logger.info(f"[动态提示词] 一票否决项: {negative}")
                    self.logger.info(
                        f"[动态提示词] 筛选标准:\n{criteria_text}"
                    )
            except Exception as e:
                self.logger.warning(f"[AI筛选] 动态提示词生成失败，使用静态模板: {e}")

        encoded_keyword = urllib.parse.quote(keyword)
        url = f"{self.BASE_URL}?q={encoded_keyword}"

        # 检查当前页面是否已经是搜索结果页
        current_url = self.page.url
        if keyword in current_url and "/search/" in current_url:
            print(f"当前页面已是搜索结果页，直接开始收集数据")
            self._search_page_url = current_url  # 保存精确搜索页 URL
        else:
            print(f"正在访问: {url}")
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                self._search_page_url = self.page.url  # 保存导航后的精确搜索页 URL
            except Exception as e:
                print(f"页面加载警告: {e}")
                # 尝试继续，页面可能已经部分加载

        # 模拟真实用户浏览行为，等待页面完全加载
        wait_time = random.uniform(5, 8)
        print(f"等待页面加载 ({wait_time:.1f}秒)...")
        time.sleep(wait_time)

        # 检测是否需要登录
        self._check_login_required()

        # 进度回调：开始收集
        if self.progress_callback:
            self.progress_callback("collecting", 0, max_pins, "开始收集数据")

        # 根据min_saves和climb_mode决定使用哪种收集方式：
        # - 有 min_saves 过滤或爬坡模式 → 探索模式（逐个点击pin获取详情）
        # - 纯数量收集（min_saves=0, climb_mode=False） → 滚动模式（更快）
        if min_saves > 0 or climb_mode:
            mode_str = (
                "纯爬坡模式"
                if climb_mode
                else f"相似推荐探索模式 (min_saves={min_saves})"
            )
            print(f"使用{mode_str}")
            return self._explore_similar_pins(
                max_pins, min_saves, climb_mode=climb_mode
            )
        else:
            print(f"使用滚动收集模式")
            return self._scroll_and_collect(max_pins)

    def _check_login_required(self):
        """检测是否需要登录，如果需要则启动可见浏览器让用户登录

        流程：
        1. 检测当前页面是否需要登录
        2. 如果需要登录，弹出可见浏览器等待用户登录
        3. 登录成功后，保存 storage_state 到数据库
        4. 将 cookie 注入到当前浏览器上下文
        """
        try:
            login_required = self.page.evaluate("""
                () => {
                    const loginModal = document.querySelector('[data-test-id="login-modal"]');
                    const signupButton = document.querySelector('[data-test-id="signup-button"]');
                    const loginButton = document.querySelector('[data-test-id="login-button"]');
                    const isLoginPage = window.location.pathname.includes('/login');
                    const isSignupPage = window.location.pathname.includes('/signup');
                    const hasSearchResults = document.querySelectorAll('[data-test-id="pin"]').length > 0
                        || document.querySelectorAll('div[data-grid-item]').length > 0
                        || document.querySelectorAll('div[data-test-id="homefeed-feed"]').length > 0;
                    const hasLoginWall = document.querySelector('[data-test-id="unauth-bottom-login-button"]') !== null
                        || document.querySelector('div[data-test-id="login-modal"]') !== null
                        || document.querySelector('button[data-test-id="signup-button"]') !== null;
                    const pageBody = document.body ? document.body.innerText : '';
                    const hasLoginText = pageBody.includes('Log in to') || pageBody.includes('登录以')
                        || pageBody.includes('Sign up to') || pageBody.includes('注册以');
                    return {
                        hasModal: !!loginModal,
                        hasButtons: !!(signupButton || loginButton),
                        isLoginPage: isLoginPage || isSignupPage,
                        hasSearchResults: hasSearchResults,
                        hasLoginWall: hasLoginWall,
                        hasLoginText: hasLoginText,
                        requiresLogin: (isLoginPage || isSignupPage || hasLoginWall || (hasLoginText && !hasSearchResults)) && !hasSearchResults
                    };
                }
            """)

            if login_required["requiresLogin"]:
                is_primary = self.worker_id == "worker-0" or not self.worker_id
                if not is_primary:
                    print(f"\n[Worker {self.worker_id}] 需要登录Pinterest")
                self._launch_visible_chrome_for_login()
                return

            if not login_required.get("hasSearchResults", True):
                time.sleep(3)
                still_no_results = self.page.evaluate("""
                    () => {
                        return document.querySelectorAll('[data-test-id="pin"]').length === 0
                            && document.querySelectorAll('div[data-grid-item]').length === 0
                            && document.querySelectorAll('div[data-test-id="homefeed-feed"]').length === 0;
                    }
                """)
                if still_no_results:
                    current_url = self.page.url
                    self.logger.warning(f"[登录检测] 搜索页无任何结果，可能需要登录 (URL: {current_url})")
                    self._launch_visible_chrome_for_login()

        except Exception as e:
            if self.debug:
                print(f"登录检测出错: {e}")

    def _launch_visible_chrome_for_login(self):
        """启动可见浏览器让用户登录，登录成功后保存 storage_state 到数据库

        借鉴 social-auto-upload-main 的认证模式：
        - 使用 Playwright 启动可见浏览器
        - 监听 URL 变化检测登录成功
        - 登录成功后调用 context.storage_state() 保存完整浏览器状态
        - 将 storage_state 写入数据库，供后续 Worker 复用
        """
        worker_label = f" [Worker {self.worker_id}]" if self.worker_id and self.worker_id != "worker-0" else ""
        print("\n" + "=" * 60)
        print(f"⚠️  检测到需要 Pinterest 登录{worker_label}")
        print("=" * 60)
        print(f"\n正在启动可见浏览器让您登录{worker_label}...")
        print("\n请在新打开的浏览器窗口中登录 Pinterest")
        print("登录完成后，程序将自动继续...")
        print("\n提示：")
        print("  1. 使用邮箱/密码登录")
        print("  2. 或使用Google/Facebook账号登录")
        print("  3. 登录成功后会自动保存到数据库，其他Worker可复用")
        print("=" * 60 + "\n")

        login_browser = None
        login_context = None
        login_page = None

        try:
            login_browser = self._playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--lang=zh-CN",
                    "--start-maximized",
                ],
            )

            login_context_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "viewport": {"width": 1280, "height": 900},
            }

            if self._cookie_manager and self._cookie_account_id:
                existing_state = self._cookie_manager.load_storage_state(self._cookie_account_id)
                if existing_state and existing_state.get("cookies"):
                    temp_state = Path(COOKIES_DIR) / f"_login_temp_{self.worker_id}.json"
                    temp_state.write_text(json.dumps(existing_state, ensure_ascii=False), encoding="utf-8")
                    login_context_kwargs["storage_state"] = str(temp_state)
                    print(f"[Cookie] 已加载已有Cookie ({len(existing_state.get('cookies', []))} 个)，尝试复用登录状态...")

            login_context = login_browser.new_context(**login_context_kwargs)
            login_page = login_context.new_page()
            apply_stealth(login_page)

            login_page.goto("https://www.pinterest.com/login/", timeout=60000)
            original_url = login_page.url

            print("等待登录中...")
            max_wait = 300
            wait_interval = 3
            waited = 0

            while waited < max_wait:
                time.sleep(wait_interval)
                waited += wait_interval

                try:
                    current_url = login_page.url
                    still_needs_login = (
                        "/login" in current_url
                        or login_page.get_by_text("登录").count() > 0
                        or login_page.get_by_text("Log in").count() > 0
                    )

                    if not still_needs_login and current_url != original_url:
                        print(f"\n✓ 登录成功！当前页面: {current_url}")

                        time.sleep(3)

                        storage_state = login_context.storage_state()

                        if self._cookie_manager and self._cookie_account_id:
                            self._cookie_manager.update_storage_state(
                                self._cookie_account_id, storage_state
                            )
                            print(f"[Cookie] storage_state 已保存到数据库 (账号 #{self._cookie_account_id})")
                        else:
                            print("[Cookie] CookieManager 不可用，storage_state 未持久化")

                        self._inject_cookies_to_context(storage_state)

                        try:
                            self.page.reload(timeout=30000)
                            time.sleep(3)
                            print("[Cookie] 已将登录状态注入到爬虫浏览器")
                        except Exception as reload_err:
                            print(f"[Cookie] 刷新页面失败: {reload_err}")

                        return

                    if waited % 30 == 0:
                        print(f"  仍在等待登录... ({waited}秒)")

                except Exception as check_err:
                    if self.debug:
                        print(f"检查登录状态出错: {check_err}")

            print("登录等待超时")
            raise RuntimeError(f"登录等待超时（{max_wait}秒）。请重新运行程序并完成登录。")

        finally:
            try:
                if login_page:
                    login_page.close()
            except Exception:
                pass
            try:
                if login_context:
                    login_context.close()
            except Exception:
                pass
            try:
                if login_browser:
                    login_browser.close()
            except Exception:
                pass

    def _inject_cookies_to_context(self, storage_state: dict):
        """将 storage_state 中的 cookie 注入到当前浏览器上下文

        Args:
            storage_state: Playwright storage_state 字典
        """
        if not self.context or not storage_state:
            return

        try:
            cookies = storage_state.get("cookies", [])
            for cookie in cookies:
                try:
                    cookie_dict = {k: v for k, v in cookie.items() if v is not None}
                    self.context.add_cookies([cookie_dict])
                except Exception as e:
                    if self.debug:
                        print(f"[Cookie] 注入单个 cookie 失败: {e}")

            origins = storage_state.get("origins", [])
            if origins and self.page:
                for origin in origins:
                    local_storage = origin.get("localStorage", [])
                    for item in local_storage:
                        try:
                            self.page.evaluate(
                                f"localStorage.setItem('{item['name']}', '{item['value']}')"
                            )
                        except Exception:
                            pass

            print(f"[Cookie] 已注入 {len(cookies)} 个 cookie 到当前上下文")
        except Exception as e:
            print(f"[Cookie] cookie 注入失败: {e}")

    def _save_cookie_state(self):
        """保存当前浏览器上下文的 storage_state 到数据库"""
        if not self._cookie_manager or not self._cookie_account_id:
            return

        if not self.context:
            return

        try:
            storage_state = self.context.storage_state()
            if storage_state and storage_state.get("cookies"):
                self._cookie_manager.update_storage_state(
                    self._cookie_account_id, storage_state
                )
                self.logger.info(
                    f"[Cookie] 已保存当前 session 状态到数据库 (账号 #{self._cookie_account_id}, "
                    f"{len(storage_state.get('cookies', []))} 个 cookie)"
                )
        except Exception as e:
            if self.debug:
                self.logger.debug(f"[Cookie] 保存 session 状态失败: {e}")

        try:
            self._cookie_manager.release_worker(self.worker_id)
        except Exception:
            pass

    def _ensure_and_click_pin(self, clicked_pins, keyword):
        visible_pins = self._get_visible_pin_elements(self.media_type)
        if not visible_pins:
            return False
        unclicked = [p for p in visible_pins if p["id"] not in clicked_pins]
        if not unclicked:
            return False
        selected = random.choice(unclicked)
        pin_id = selected["id"]
        clicked_pins.add(pin_id)
        self._interact_with_pin(pin_id, 0, {}, keyword)
        return True

    def _scroll_and_collect(self, max_pins: int) -> List[Pin]:
        """滚动页面并收集数据（拟人化浏览模式）"""
        collected_pins = {}
        main_pin_count = 0  # 主 pin 计数
        scroll_count = 0
        max_scrolls = 50  # 最大滚动次数限制
        no_new_pins_count = 0  # 连续没有新数据的次数
        clicked_pins = set()  # 已点击查看的 pin ID

        # 先滚动1-2次加载数据，模拟用户浏览（根据需求调整）
        init_scrolls = 1 if max_pins <= 10 else 2
        print(f"正在加载页面内容...")
        for i in range(init_scrolls):
            try:
                self._scroll_page()
            except Exception as e:
                print(f"滚动时出错: {e}")
            wait_time = random.uniform(2, 4)
            print(f"等待 {wait_time:.1f}秒...")
            time.sleep(wait_time)

        while main_pin_count < max_pins and scroll_count < max_scrolls:
            scroll_count += 1  # 每次循环递增，确保有最大次数限制
            try:
                # 提取当前页面的 Pin 数据（基本信息）
                pins = self._extract_pins_from_page()

                new_pins_found = False
                for pin in pins:
                    # Redis查重：跳过已收集的pin（使用协调器）
                    if self._coordinator and self._coordinator.is_collected(pin.id):
                        continue

                    # AI 筛选：评估图片质量
                    if self._ai_available:
                        try:
                            if pin.image_url:
                                self.logger.info(f"[AI筛选] 正在评估: {pin.id[:12]}...")
                                result = self._ai_manager.evaluate_pin(pin.image_url, self._current_keyword)

                                if not result.get("is_approved"):
                                    self.logger.info(f"[AI筛选] ❌ 未通过: {result.get('reasoning')}")
                                    if self._coordinator:
                                        self._coordinator.mark_collected(pin.id, saves=0)
                                        self._coordinator.set_filter_result(pin.id, result)
                                    continue
                                else:
                                    self.logger.info(f"[AI筛选] ✅ 通过: {result.get('reasoning')}")
                        except Exception as e:
                            self.logger.warning(f"[AI筛选] 评估失败: {e}")

                    collected_pins[pin.id] = pin
                    if self._coordinator:
                        self._coordinator.mark_collected(pin.id, saves=getattr(pin, 'saves', 0))
                    new_pins_found = True
                    main_pin_count += 1  # 计数主 pin
                    print(
                        f"已收集 {main_pin_count}/{max_pins} 个主 Pin，总计 {len(collected_pins)} 个..."
                    )

                    # 进度回调：更新收集进度
                    if self.progress_callback:
                        self.progress_callback(
                            "collecting",
                            main_pin_count,
                            max_pins,
                            f"已收集 {main_pin_count}/{max_pins} 个Pin",
                            collected_count=len(collected_pins),
                        )

                    if main_pin_count >= max_pins:
                        break

                if main_pin_count >= max_pins:
                    break

                # 如果没有新数据，计数
                if not new_pins_found:
                    no_new_pins_count += 1
                    if no_new_pins_count >= 5:
                        print("连续多次没有新数据，停止爬取")
                        break
                else:
                    no_new_pins_count = 0

                # 随机滚动策略：模拟真实用户行为
                # 30%概率：滚动一次后选择
                # 30%概率：滚动多次后选择
                # 40%概率：不滚动直接选择
                scroll_strategy = random.random()
                if scroll_strategy < 0.3:
                    # 滚动一次
                    self._scroll_page()
                    time.sleep(random.uniform(1, 2))
                elif scroll_strategy < 0.6:
                    # 滚动多次（2-4次）
                    scroll_times = random.randint(2, 4)
                    for _ in range(scroll_times):
                        self._scroll_page()
                        time.sleep(random.uniform(1, 2))
                # else: 40%概率不额外滚动

                # 强制点击一个可见 pin，确保每次循环都有采集
                if not self._ensure_and_click_pin(clicked_pins, self._current_keyword):
                    try:
                        self._scroll_page()
                        time.sleep(random.uniform(2, 3))
                        self._ensure_and_click_pin(clicked_pins, self._current_keyword)
                    except Exception:
                        pass

                # 根据滚动策略做可选额外滚动
                scroll_strategy = random.random()
                if scroll_strategy < 0.4:
                    self._scroll_page()
                    time.sleep(random.uniform(1, 2))
                elif scroll_strategy < 0.7:
                    scroll_times = random.randint(2, 4)
                    for _ in range(scroll_times):
                        self._scroll_page()
                        time.sleep(random.uniform(1, 2))

                # 统一等待
                time.sleep(random.uniform(2, 4))

                # 每爬取 20 个主 pin，额外休息
                if main_pin_count > 0 and main_pin_count % 20 == 0:
                    time.sleep(random.uniform(15, 30))

            except Exception as e:
                print(f"收集数据时出错: {e}")
                time.sleep(3)
                continue

        print(f"搜索页面收集完成")
        print(f"滚动次数: {scroll_count}/{max_scrolls}")
        print(f"主 Pin: {main_pin_count} 个")
        print(f"相似推荐: {len(collected_pins) - main_pin_count} 个")
        print(f"总计: {len(collected_pins)} 个")

        # 返回所有收集的 pins（包括主 pin 和相似推荐）
        # 注意：不再需要 enrich_pins_with_details，因为详情已在交互过程中收集
        return list(collected_pins.values())

    def _explore_similar_pins(
        self, target_count: int, min_saves: int, climb_mode: bool = False
    ) -> List[Pin]:
        """通过相似推荐链进行贪心爬山探索

        逻辑：
        1. 搜索关键词 → 在搜索页随机点击一个pin（当前主体）
        2. 提取当前主体的saves等数据
        3. 如果saves >= min_saves → 找到达标pin，在当前详情页爬取所有相似推荐数据
        4. 如果saves < min_saves → 查看相似推荐：
           - 点击一个相似推荐，提取其saves
           - 如果相似推荐的saves > 当前主体的saves → 更换主体为该相似推荐
           - 如果不大于 → 保持当前主体，继续看下一个相似推荐
        5. 返回搜索页，选下一个起始pin，重复直到收集足够多的达标pin

        Args:
            target_count: 目标收集数量
            min_saves: 最小保存数阈值
            climb_mode: 纯爬坡模式，不检查min_saves，持续找更优直到收集够数量
        """
        global _stop_requested
        collected_pins = {}  # 存所有收集到的 pin（含相似推荐）
        qualified_count = 0  # 只统计真正达标且符合媒体类型的 pin 数量
        visited_ids = set()  # 已访问过的pin（防止重复点击）
        collected_pin_ids = set()  # 已收集的pin ID（防止重复收集）
        max_attempts = max(target_count * 10, 50)  # 给足够的尝试次数
        max_depth = 9999  # 爬坡最大深度（无限制，仅靠saves无法提升时自然终止）
        attempt = 0
        max_search_scroll_rounds = 10  # 搜索页最大滚动轮数，避免无限滚动
        search_scroll_round = 0  # 当前搜索页滚动轮数

        try:
            self.logger.info(f"=" * 60)
            self.logger.info(
                f"开始探索模式 | 目标: {target_count}个 | min_saves: {min_saves} | climb_mode: {climb_mode}"
            )
            self.logger.info(f"=" * 60)

            # 初始随机滚动 0-5 次，让入口更多变
            init_pgdn = random.randint(0, 5)
            self.logger.info(f"初始随机滚动 {init_pgdn} 次...")
            for _ in range(init_pgdn):
                self._scroll_page_with_pgdn()
            time.sleep(random.uniform(0.5, 1))

            search_pin_ids, _ = self._get_search_page_pins()
            if not search_pin_ids:
                self.logger.warning("搜索页面没有找到任何pin，尝试滚动加载...")
                for _ in range(3):
                    self._scroll_page_with_pgdn()
                search_pin_ids, _ = self._get_search_page_pins()

            if not search_pin_ids:
                self.logger.error("搜索页面没有找到任何pin，无法开始探索")
                return []

            random.shuffle(search_pin_ids)
            self.logger.info(
                f"搜索页发现 {len(search_pin_ids)} 个pin，开始贪心探索模式"
            )

            # 将入口 pin 推送到协调器队列（多 Worker 共享）
            if self._coordinator:
                pushed_count = 0
                for pid in search_pin_ids:
                    if not self._coordinator.is_collected(pid):
                        self._coordinator.push_entry_pin(pid)
                        pushed_count += 1
                self.logger.info(f"已推送 {pushed_count} 个入口 pin 到协调器队列")

            # 连续恢复失败计数器，防止浏览器关闭后无限重试
            consecutive_recovery_failures = 0
            max_consecutive_recovery_failures = 5

            while qualified_count < target_count and attempt < max_attempts:
                self.logger.info(
                    f"[外层循环开始] qualified_count={qualified_count}, target_count={target_count}, attempt={attempt}/{max_attempts}"
                )

                # 检查是否有其他 Worker 已标记任务完成
                if self._coordinator and self._coordinator.is_task_complete():
                    info = self._coordinator.get_task_complete_info()
                    self.logger.info(
                        f"[任务终止] 检测到其他 Worker {info.get('completed_by', '?')} 已完成任务，当前 Worker 停止"
                    )
                    print(f"\n⚠️ 其他 Worker 已完成任务，当前 Worker 停止")
                    return list(collected_pins.values())

                if qualified_count >= target_count:
                    self.logger.info(
                        f"外层循环检查: qualified_count({qualified_count}) >= target_count({target_count}) → 退出"
                    )
                    print(f"已收集{target_count}个，停止探索")
                    break

                if _stop_requested:
                    self.logger.warning("检测到停止请求，正在退出探索模式...")
                    print("\n⚠️  检测到停止请求，正在退出探索模式...")
                    return list(collected_pins.values())

                # 连续恢复失败达到阈值，彻底终止
                if consecutive_recovery_failures >= max_consecutive_recovery_failures:
                    self.logger.error(
                        f"连续 {consecutive_recovery_failures} 次恢复失败，浏览器可能已彻底关闭，终止探索"
                    )
                    print(f"\n❌ 连续 {consecutive_recovery_failures} 次恢复失败，浏览器可能已关闭，停止探索")
                    break

                attempt += 1
                self.logger.info(f"attempt 递增: attempt={attempt}")

                # 检查当前页面状态，如果失效或不在搜索页则重新导航
                if not self._is_page_alive() or ("/search/" not in self.page.url and self.page.url):
                    self.logger.warning(
                        f"当前页面状态异常(alive={self._is_page_alive()}, URL={self.page.url})，重新导航到搜索页"
                    )
                    try:
                        if self._ensure_page_alive_and_on_search(self._current_keyword):
                            consecutive_recovery_failures = 0  # 恢复成功，重置计数器
                            search_pin_ids, _ = self._get_search_page_pins()
                            if not search_pin_ids:
                                self.logger.warning("重新导航后未获取到pin，等待后重试")
                                time.sleep(3)
                                search_pin_ids, _ = self._get_search_page_pins()
                        else:
                            consecutive_recovery_failures += 1
                            self.logger.error(
                                f"页面恢复失败 ({consecutive_recovery_failures}/{max_consecutive_recovery_failures})，跳过当前轮次"
                            )
                            time.sleep(1)  # 避免无意义的高速重试
                            continue
                    except Exception as e:
                        consecutive_recovery_failures += 1
                        self.logger.error(f"重新导航到搜索页失败: {e} ({consecutive_recovery_failures}/{max_consecutive_recovery_failures})")
                        time.sleep(1)
                        continue
                else:
                    # 页面正常，重置失败计数器
                    consecutive_recovery_failures = 0

                # 优先从协调器队列获取入口 pin（多 Worker 竞争），队列空时回退到本地搜索页遍历
                entry_pin_id = None
                if self._coordinator:
                    entry_pin_id = self._coordinator.pop_entry_pin()
                    if entry_pin_id:
                        self.logger.info(
                            f"从协调器队列获取入口 pin: {entry_pin_id}"
                        )

                # 队列空：回退到本地搜索页遍历
                if entry_pin_id is None:
                    for pid in search_pin_ids:
                        if pid not in visited_ids:
                            entry_pin_id = pid
                            break

                if entry_pin_id is None:
                    # 所有可见的 pin 都已探索过，尝试滚动加载更多
                    search_scroll_round += 1
                    if search_scroll_round >= max_search_scroll_rounds:
                        self.logger.warning(
                            f"搜索页已滚动 {search_scroll_round} 轮仍无新 pin，停止探索"
                        )
                        print(
                            f"搜索页已滚动 {search_scroll_round} 轮仍无新内容，停止探索"
                        )
                        break

                    self.logger.info(
                        f"搜索页上所有 {len(search_pin_ids)} 个 pin 都已探索过，"
                        f"第 {search_scroll_round}/{max_search_scroll_rounds} 轮滚动加载新内容..."
                    )
                    print(
                        f"所有可见 pin 都已探索过，滚动加载新内容..."
                        f"(第 {search_scroll_round}/{max_search_scroll_rounds} 轮)"
                    )

                    # 滚动页面加载更多 pin
                    scroll_times = random.randint(2, 4)
                    for _ in range(scroll_times):
                        self._scroll_page_with_pgdn()
                        time.sleep(random.uniform(1, 2))

                    # 重新获取搜索页的 pin ID 列表
                    new_search_pin_ids, _ = self._get_search_page_pins()
                    if new_search_pin_ids:
                        # 过滤出真正新加载的 pin
                        new_pins = [
                            pid
                            for pid in new_search_pin_ids
                            if pid not in search_pin_ids
                        ]
                        if new_pins:
                            self.logger.info(f"滚动后发现 {len(new_pins)} 个新 pin")
                            print(f"滚动后发现 {len(new_pins)} 个新 pin，继续探索")
                            # 添加新 pin 到列表
                            search_pin_ids.extend(new_pins)
                            random.shuffle(search_pin_ids)
                            # 推送新入口 pin 到协调器队列
                            if self._coordinator:
                                for pid in new_pins:
                                    if not self._coordinator.is_collected(pid):
                                        self._coordinator.push_entry_pin(pid)
                                self.logger.info(f"已推送 {len(new_pins)} 个新入口 pin 到协调器")
                        else:
                            self.logger.info("滚动后未发现新 pin，继续尝试未访问的")
                            print("滚动后未发现新 pin，继续尝试...")
                    else:
                        self.logger.warning("滚动后未获取到任何 pin")
                        print("滚动后未获取到任何 pin，继续尝试...")

                    # 重新获取并过滤搜索页 pin：排除 Redis 中已收集的（使用协调器）
                    search_pin_ids, _ = self._get_search_page_pins()
                    if search_pin_ids:
                        if self._coordinator:
                            search_pin_ids = [
                                pid for pid in search_pin_ids
                                if not self._coordinator.is_collected(pid)
                            ]
                        else:
                            search_pin_ids = [
                                pid for pid in search_pin_ids
                                if not Pin.is_collected(pid)
                            ]
                        if search_pin_ids:
                            random.shuffle(search_pin_ids)
                            visited_ids.clear()
                            self.logger.info(
                                f"过滤 Redis 后剩余 {len(search_pin_ids)} 个可用 pin"
                            )
                        else:
                            self.logger.info("所有 pin 都在 Redis 中，继续滚动...")
                    continue

                self.logger.info(
                    f"选择起始pin: {entry_pin_id} (visited_ids已有{len(visited_ids)}个)"
                )
                print(f"\n{'=' * 50}")
                print(
                    f"[已收集:{len(collected_pins)}/{target_count}] 从搜索页进入 pin: {entry_pin_id}"
                )
                print(f"{'=' * 50}")

                # AI 筛选：评估起始 pin 图片质量
                if self._ai_available:
                    try:
                        # 从一次性提取的 ID→图片映射中获取（与 pin ID 列表同一次 DOM 快照，100% 匹配）
                        image_url = self._search_image_map.get(entry_pin_id, "")
                        # 如果映射中没有（极少情况），回退到 DOM 直接查找
                        if not image_url:
                            try:
                                pin_elem = self.page.query_selector(f'a[href*="/pin/{entry_pin_id}"]')
                                if pin_elem:
                                    img_url_attrs = self.page.evaluate("""
                                        (el) => {
                                            const img = el.querySelector('img');
                                            if (!img) return '';
                                            return img.src || img.srcset || img.getAttribute('src') || img.getAttribute('data-src') || '';
                                        }
                                    """, pin_elem)
                                    if img_url_attrs:
                                        # 取第一个可用 URL（srcset 可能包含多分辨率）
                                        for part in img_url_attrs.split(','):
                                            url_part = part.trim().split(' ')[0]
                                            if 'pinimg' in url_part:
                                                image_url = url_part
                                                break
                                        if not image_url and img_url_attrs.startswith('http'):
                                            image_url = img_url_attrs.split(',')[0].split(' ')[0]
                            except Exception:
                                pass
                        if image_url:
                            self.logger.info(f"[AI筛选] 正在评估图片质量: {entry_pin_id[:12]}...")
                            result = self._ai_manager.evaluate_pin(image_url, self._current_keyword)

                            if not result.get("is_approved"):
                                self.logger.info(f"[AI筛选] ❌ 未通过: {result.get('reasoning')}")
                                visited_ids.add(entry_pin_id)
                                # 缓存失败结果到协调器，避免其他 Worker 重复 AI 调用
                                if self._coordinator:
                                    self._coordinator.set_filter_result(entry_pin_id, result)
                                continue
                            else:
                                self.logger.info(f"[AI筛选] ✅ 通过: {result.get('reasoning')}")
                        else:
                            # 无法获取图片 URL 时不跳过，直接进入详情页用大图判定
                            self.logger.info(f"[AI筛选] 入口图片URL缺失，跳过预览评估，直接进入详情页判定 | pin={entry_pin_id[:12]}...")
                    except Exception as e:
                        self.logger.warning(f"[AI筛选] 评估失败: {e}, 当前页面URL: {self.page.url[:100]}")

                # 点击搜索页上的pin，进入详情页
                try:
                    pin_link = self.page.query_selector(
                        f'a[href*="/pin/{entry_pin_id}"]'
                    )
                    if not pin_link:
                        # 链接不在当前页面（可能已滚动出DOM或被回收），直接导航到 pin 详情页
                        self.logger.info(f"搜索页未找到 pin {entry_pin_id} 的链接，直接导航到详情页")
                        pin_url = f"https://www.pinterest.com/pin/{entry_pin_id}/"
                        try:
                            self.page.goto(pin_url, wait_until="domcontentloaded", timeout=15000)
                            time.sleep(random.uniform(3, 5))
                        except Exception as nav_e:
                            self.logger.warning(f"直接导航到 pin {entry_pin_id} 失败: {nav_e}")
                            visited_ids.add(entry_pin_id)
                            continue
                    else:
                        # 链接在页面上，正常点击
                        # 滚动到元素可见
                        try:
                            pin_link.scroll_into_view_if_needed()
                            time.sleep(random.uniform(0.5, 1))
                        except Exception:
                            pass

                        # 记录点击前的URL
                        before_url = self.page.url
                        pin_link.click()

                        # 等待URL变化，确认进入详情页
                        try:
                            self.page.wait_for_function(
                                f'() => window.location.href.includes("/pin/{entry_pin_id}")',
                                timeout=8000,
                            )
                        except Exception as e:
                            print(f"  点击后未进入详情页，URL未变化: {e}")
                            visited_ids.add(entry_pin_id)
                            continue

                    time.sleep(random.uniform(4, 6))
                except Exception as e:
                    print(f"  点击pin {entry_pin_id} 失败: {e}")
                    visited_ids.add(entry_pin_id)
                    continue

                # 当前主体：从搜索页进入的pin
                current_pin_id = entry_pin_id
                current_saves = 0
                depth = 0
                found_qualified = False
                pending_collect = []

                while depth < max_depth:
                    self.logger.debug(
                        f"[内层循环开始] depth={depth}, qualified_count={qualified_count}/{target_count}"
                    )

                    # 检查是否有其他 Worker 已标记任务完成
                    if self._coordinator and self._coordinator.is_task_complete():
                        self.logger.info(
                            f"[任务终止] 检测到其他 Worker 已完成，深度循环停止"
                        )
                        return list(collected_pins.values())

                        if qualified_count >= target_count:
                            self.logger.info(
                                f"内层循环检查: qualified_count({qualified_count}) >= target_count({target_count}) → 立即返回"
                            )
                            if self._coordinator:
                                self._coordinator.set_task_complete(qualified_count)
                            return list(collected_pins.values())

                    depth += 1
                    self.logger.debug(f"depth 递增: depth={depth}")

                    if _stop_requested:
                        self.logger.warning("检测到停止请求，正在退出深度探索...")
                        print("\n⚠️  检测到停止请求，正在退出深度探索...")
                        return list(collected_pins.values())

                    # 双重去重检查：内存已访问 + Redis已收集
                    # 爬坡升级的pin可能已在visited_ids中，此时应继续作为跳板而非中断
                    if current_pin_id in visited_ids and depth > 1:
                        self.logger.debug(
                            f"pin {current_pin_id} 已访问过，作为跳板继续爬坡"
                        )
                    elif current_pin_id in visited_ids and not found_qualified:
                        self.logger.warning(
                            f"pin {current_pin_id} 已访问过（内存），跳过"
                        )
                        break
                    # 已收集过的 pin 不重复收集，但可作为跳板继续爬坡找更多优质 pin
                    already_collected = False
                    if self._coordinator and self._coordinator.is_collected(current_pin_id):
                        self.logger.info(
                            f"pin {current_pin_id} 已收集过（协调器），作为跳板继续爬坡"
                        )
                        already_collected = True
                        # 不 break，继续用这个 pin 找相似推荐
                    visited_ids.add(current_pin_id)
                    self.logger.debug(
                        f"visited_ids 添加 {current_pin_id}，共 {len(visited_ids)} 个"
                    )

                    self.logger.info(
                        f"[深度{depth}] 提取 pin {current_pin_id} 的数据..."
                    )
                    print(f"  [深度{depth}] 提取 pin {current_pin_id} 的数据...")
                    details = self._extract_pin_details_from_modal()

                    # 如果第一次提取失败，等待后重试一次
                    if not details or not details.get("id"):
                        self.logger.info(f"[深度{depth}] 首次提取失败，等待页面加载后重试...")
                        time.sleep(5)
                        details = self._extract_pin_details_from_modal()

                    if not details or not details.get("id"):
                        self.logger.warning(f"[深度{depth}] 无法提取详情，中断当前深度")
                        print(f"  [深度{depth}] 无法提取详情，中断当前深度")
                        self.logger.warning(f"[深度{depth}] 当前URL: {self.page.url}")
                        # 提取失败时返回搜索页，避免后续操作在错误页面执行
                        try:
                            self._navigate_back_to_search(self._current_keyword)
                        except Exception as nav_err:
                            self.logger.warning(f"返回搜索页失败: {nav_err}")
                        break

                    saves = details.get("saves", 0) or 0
                    title = details.get("title", "无标题")[:40]
                    is_video = details.get("is_video", False)
                    self.logger.info(f"[深度{depth}] '{title}...' Saves: {saves}")
                    print(f"  [深度{depth}] '{title}...' Saves: {saves}")

                    current_saves = saves
                    self.logger.debug(f"current_saves 更新: {current_saves}")

                    media_match = True
                    if self.media_type == "images" and is_video:
                        media_match = False
                    if self.media_type == "video" and not is_video:
                        media_match = False

                    self.logger.info(
                        f"[深度{depth}] 检查收集条件: saves({saves}) >= min_saves({min_saves}) = {saves >= min_saves}, media_match={media_match}"
                    )

                    if saves >= min_saves and media_match:
                        if already_collected:
                            self.logger.info(
                                f"[深度{depth}] 该 pin 已在其他上下文中收集，跳过收集，继续爬坡"
                            )
                        elif current_pin_id not in collected_pins:
                            images = details.get("images", {})
                            image_url = (
                                images.get("orig", {}).get("url", "")
                                if isinstance(images, dict)
                                else ""
                            )

                            pending_collect.append({
                                "pin_id": current_pin_id,
                                "image_url": image_url,
                                "sp_saves": saves,
                                "sp_details": details,
                                "sp_images": images,
                                "sp_is_video": is_video,
                            })
                            self.logger.info(
                                f"[深度{depth}] pin {current_pin_id} 达标(saves={saves})，加入批量收集池(当前{len(pending_collect)}张)"
                            )

                    self.logger.info(
                        f"[深度{depth}] 开始寻找更优跳板 (目标 Saves > {current_saves})..."
                    )
                    print(
                        f"  [深度{depth}] 开始寻找更优跳板 (目标 Saves > {current_saves})..."
                    )

                    similar_pins = self._find_similar_pins_in_modal(scroll_times=1)

                    # 【修复】提前过滤媒体类型不匹配的相似推荐，避免无效点击
                    filtered_similar_pins = []
                    for sp in similar_pins:
                        if sp["id"] in visited_ids:
                            continue
                        # 快速检查媒体类型（通过 DOM 属性判断，避免点击进入）
                        try:
                            sp_element = self.page.query_selector(
                                f'a[href*="/pin/{sp["id"]}"]'
                            )
                            if sp_element:
                                is_video_elem = sp_element.query_selector(
                                    '[data-test-id="pinrep-video"], [data-test-id="PinTypeIdentifier"]'
                                )
                                sp_is_video = is_video_elem is not None

                                # 媒体类型过滤
                                if self.media_type == "images" and sp_is_video:
                                    visited_ids.add(
                                        sp["id"]
                                    )  # 标记为已访问，避免重复检查
                                    continue
                                if self.media_type == "video" and not sp_is_video:
                                    visited_ids.add(sp["id"])
                                    continue
                                filtered_similar_pins.append(sp)
                        except Exception:
                            # 如果无法判断，默认保留
                            filtered_similar_pins.append(sp)

                    unvisited = filtered_similar_pins

                    upgraded = False
                    checked_count = 0
                    max_checks_before_scroll = 5
                    # 智能滚动轮数：当前 saves 越高，相似推荐中超过它的概率越低，无需滚满 8 轮
                    if max(current_saves, 0) >= 200:
                        max_scroll_rounds = 2
                    elif max(current_saves, 0) >= 100:
                        max_scroll_rounds = 3
                    elif max(current_saves, 0) >= 50:
                        max_scroll_rounds = 5
                    else:
                        max_scroll_rounds = 8
                    scroll_round = 0

                    self.logger.info(
                        f"[爬坡循环开始] unvisited={len(unvisited)}个, max_scroll_rounds={max_scroll_rounds}"
                    )

                    while not upgraded and scroll_round < max_scroll_rounds:
                        scroll_round += 1
                        self.logger.debug(
                            f"[爬坡轮次{scroll_round}] 检查条件: upgraded={upgraded}, scroll_round={scroll_round} < max_scroll_rounds={max_scroll_rounds}"
                        )

                        if _stop_requested:
                            self.logger.warning("检测到停止请求，正在退出爬坡寻路...")
                            print("\n⚠️  检测到停止请求，正在退出爬坡寻路...")
                            return list(collected_pins.values())

                        batch_checked = 0
                        for sp in unvisited[:max_checks_before_scroll]:
                            if upgraded:
                                break

                            sp_id = sp["id"]

                            # 双重去重检查
                            if sp_id in visited_ids:
                                continue
                            if self._coordinator and self._coordinator.is_collected(sp_id):
                                self.logger.debug(
                                    f"  [爬坡] {sp_id} 已收集过（协调器），跳过"
                                )
                                visited_ids.add(sp_id)
                                continue

                            checked_count += 1
                            batch_checked += 1
                            self.logger.debug(
                                f"  [爬坡轮次{scroll_round}] 检查第{checked_count}个推荐: {sp_id}"
                            )
                            print(f"    尝试点击推荐：{sp_id} (第{checked_count}个)")

                            # 检查页面是否仍然存活
                            if not self._is_page_alive():
                                self.logger.warning("  [爬坡] 页面已失效，尝试恢复...")
                                print("    页面已失效，尝试恢复...")
                                if self._ensure_page_alive_and_on_search(self._current_keyword):
                                    self.logger.info("  [爬坡] 页面恢复成功，重新进入详情页...")
                                    try:
                                        self.page.goto(f"https://www.pinterest.com/pin/{current_pin_id}/", timeout=15000)
                                        time.sleep(random.uniform(4, 6))
                                        if self._is_page_alive():
                                            continue
                                    except Exception as e:
                                        self.logger.warning(f"  [爬坡] 重新进入详情页失败: {e}")
                                self.logger.error("  [爬坡] 页面恢复失败，终止当前爬坡轮次")
                                upgraded = False
                                break

                            try:
                                similar_link = self.page.query_selector(
                                    f'a[href*="/pin/{sp_id}"]'
                                )
                                if not similar_link:
                                    self.logger.debug(f"  未找到 {sp_id} 的链接")
                                    visited_ids.add(sp_id)
                                    continue

                                similar_link.scroll_into_view_if_needed()
                                time.sleep(random.uniform(0.5, 1))
                                similar_link.click()
                                time.sleep(random.uniform(3, 5))

                                sp_details = self._extract_pin_details_from_modal()
                                if not sp_details or not sp_details.get("id"):
                                    self.logger.warning(
                                        f"  [爬坡] 提取失败 {sp_id}，后退"
                                    )
                                    print("      提取失败，后退")
                                    visited_ids.add(sp_id)
                                    self._safe_go_back()
                                    continue

                                sp_saves = sp_details.get("saves", 0) or 0

                                # 如果模态框提取 saves=0，用 pin 卡片上预先提取的 saves 作为兜底
                                # （Pinterest 模态框 PWS_DATA 不更新，DOM 正则可能匹配不到）
                                if sp_saves == 0:
                                    card_saves = sp.get("card_saves", 0)
                                    if card_saves > 0:
                                        sp_saves = card_saves
                                        self.logger.debug(
                                            f"  [爬坡] {sp_id} 使用卡片 saves={card_saves}（模态框提取失败）"
                                        )

                                # 先检查媒体类型
                                sp_is_video = sp_details.get("is_video", False)
                                media_match = True
                                if self.media_type == "images" and sp_is_video:
                                    media_match = False
                                if self.media_type == "video" and not sp_is_video:
                                    media_match = False

                                # 始终提取图片 URL（入口预筛选也需要）
                                sp_images = sp_details.get("images", {})
                                sp_image_url = (
                                    sp_images.get("orig", {}).get("url", "")
                                    if isinstance(sp_images, dict)
                                    else ""
                                )

                                # 检查是否满足 min_saves → 加入批量收集池
                                if (
                                    sp_saves >= min_saves
                                    and media_match
                                    and sp_id not in collected_pin_ids
                                ):
                                    pending_collect.append({
                                        "pin_id": sp_id,
                                        "image_url": sp_image_url,
                                        "sp_saves": sp_saves,
                                        "sp_details": sp_details,
                                        "sp_images": sp_images,
                                        "sp_is_video": sp_is_video,
                                    })

                                    # 池满时自动冲刷
                                    if len(pending_collect) >= BATCH_COLLECT_SIZE:
                                        self.logger.info(
                                            f"  [批量池] 已达 {BATCH_COLLECT_SIZE} 张，触发批量评估..."
                                        )
                                        flush_result = self._flush_batch_collect_pool(
                                            pending_collect, self._current_keyword
                                        )
                                        q_delta, should_stop = self._apply_flush_result(
                                            flush_result, collected_pins, collected_pin_ids,
                                            visited_ids, target_count, source_label="爬坡批量"
                                        )
                                        qualified_count += q_delta
                                        if q_delta > 0:
                                            found_qualified = True
                                            self.logger.info(f"  📊 已收集 {qualified_count}/{target_count} 个")
                                            print(f"      [爬坡批量] 进度：{qualified_count}/{target_count}")
                                        if should_stop:
                                            self.logger.info(f"爬坡中已达到目标数量：{qualified_count}/{target_count}")
                                            print(f"  已达到目标数量，停止任务")
                                            if self._coordinator:
                                                self._coordinator.set_task_complete(qualified_count)
                                            try:
                                                self._navigate_back_to_search(self._current_keyword)
                                            except Exception as e:
                                                self.logger.warning(f"返回搜索页出错：{e}")
                                            return list(collected_pins.values())
                                        pending_collect = []

                                self.logger.debug(
                                    f"  [爬坡] {sp_id} 的 saves: {sp_saves}"
                                )

                                if sp_saves > current_saves:
                                    # AI 爬坡筛选：验证升级目标 pin 是否合格（室内/风格匹配）
                                    can_upgrade = True
                                    if self._ai_available and sp_image_url:
                                        # 先查协调器缓存
                                        cached = None
                                        if self._coordinator:
                                            cached = self._coordinator.get_filter_result(sp_id)
                                        if cached:
                                            can_upgrade = cached.get("is_approved", True)
                                            self.logger.info(
                                                f"  [爬坡AI筛选] 缓存命中: {'✅ 合格' if can_upgrade else '❌ 不合格'}"
                                            )
                                        else:
                                            try:
                                                climb_result = self._ai_manager.evaluate_pin(
                                                    sp_image_url, self._current_keyword
                                                )
                                                can_upgrade = climb_result.get("is_approved", True)
                                                # 缓存结果
                                                if self._coordinator:
                                                    self._coordinator.set_filter_result(
                                                        sp_id, climb_result
                                                    )
                                                self.logger.info(
                                                    f"  [爬坡AI筛选] {'✅ 合格' if can_upgrade else '❌ 不合格'}: "
                                                    f"{climb_result.get('reasoning', '')}"
                                                )
                                            except Exception as e:
                                                self.logger.warning(f"  [爬坡AI筛选] 评估失败: {e}")
                                                # 失败时默认允许升级（不让AI阻塞爬坡）
                                    if not can_upgrade:
                                        print(f"      爬坡AI筛选未通过，跳过此 pin")
                                        visited_ids.add(sp_id)
                                        self._safe_go_back()
                                        checked_count += 1
                                        continue

                                    # 刷新批量收集池（升级前先收集已累积的达标 pin）
                                    if pending_collect:
                                        self.logger.info(
                                            f"  [批量池] 升级前冲刷 {len(pending_collect)} 张"
                                        )
                                        flush_result = self._flush_batch_collect_pool(
                                            pending_collect, self._current_keyword
                                        )
                                        q_delta, should_stop = self._apply_flush_result(
                                            flush_result, collected_pins, collected_pin_ids,
                                            visited_ids, target_count, source_label="爬坡批量"
                                        )
                                        qualified_count += q_delta
                                        if q_delta > 0:
                                            found_qualified = True
                                            self.logger.info(f"  📊 已收集 {qualified_count}/{target_count} 个")
                                            print(f"      [爬坡批量] 进度：{qualified_count}/{target_count}")
                                        if should_stop:
                                            self.logger.info(f"爬坡中已达到目标数量：{qualified_count}/{target_count}")
                                            if self._coordinator:
                                                self._coordinator.set_task_complete(qualified_count)
                                            return list(collected_pins.values())
                                        pending_collect = []

                                    self.logger.info(
                                        f"  → 发现更优跳板！{sp_saves} > {current_saves}"
                                    )
                                    print(
                                        f"      → 发现更优跳板！{sp_saves} > {current_saves}"
                                    )
                                    # 【修复】升级时不加入visited_ids，因为这个pin还要在内层循环处理
                                    # 【重要】不要 go_back()！我们已经在这个更优 pin 的详情页了
                                    current_pin_id = sp_id
                                    upgraded = True
                                    break
                                else:
                                    self.logger.debug(
                                        f"  → 不够优 ({sp_saves} <= {current_saves})，后退"
                                    )
                                    print(
                                        f"      → 不够优 ({sp_saves} <= {current_saves})，后退查看下一个"
                                    )
                                    visited_ids.add(sp_id)
                                    self._safe_go_back()

                            except Exception as e:
                                self.logger.error(f"  [爬坡] 检查跳板时出错：{e}")
                                print(f"      检查跳板时出错：{e}，尝试后退")
                                visited_ids.add(sp_id)
                                self._safe_go_back()
                                continue

                        # 爬坡轮次结束：冲刷剩余批量收集池
                        if pending_collect:
                            self.logger.info(
                                f"  [批量池] 轮次结束冲刷 {len(pending_collect)} 张剩余"
                            )
                            flush_result = self._flush_batch_collect_pool(
                                pending_collect, self._current_keyword
                            )
                            q_delta, should_stop = self._apply_flush_result(
                                flush_result, collected_pins, collected_pin_ids,
                                visited_ids, target_count, source_label="爬坡批量"
                            )
                            qualified_count += q_delta
                            if q_delta > 0:
                                found_qualified = True
                                self.logger.info(f"  📊 已收集 {qualified_count}/{target_count} 个")
                                print(f"      [爬坡批量] 进度：{qualified_count}/{target_count}")
                            if should_stop:
                                self.logger.info(f"爬坡中已达到目标数量：{qualified_count}/{target_count}")
                                if self._coordinator:
                                    self._coordinator.set_task_complete(qualified_count)
                                return list(collected_pins.values())
                            pending_collect = []

                        self.logger.info(
                            f"[爬坡轮次{scroll_round}] 完成，已检查{batch_checked}个，upgraded={upgraded}"
                        )

                        if not upgraded and scroll_round < max_scroll_rounds:
                            self.logger.info(
                                f"  未发现更优，PGDN 滚动加载更多相似推荐..."
                            )
                            print(
                                f"    已检查{batch_checked}个，未发现更优，PGDN 滚动加载更多相似推荐..."
                            )
                            self._scroll_page_with_pgdn()
                            time.sleep(random.uniform(2, 3))

                            similar_pins = self._find_similar_pins_in_modal(
                                scroll_times=1
                            )

                            filtered_similar_pins = []
                            for sp in similar_pins:
                                if sp["id"] in visited_ids:
                                    continue
                                try:
                                    sp_element = self.page.query_selector(
                                        f'a[href*="/pin/{sp["id"]}"]'
                                    )
                                    if sp_element:
                                        is_video_elem = sp_element.query_selector(
                                            '[data-test-id="pinrep-video"], [data-test-id="PinTypeIdentifier"]'
                                        )
                                        sp_is_video = is_video_elem is not None

                                        if self.media_type == "images" and sp_is_video:
                                            visited_ids.add(sp["id"])
                                            continue
                                        if (
                                            self.media_type == "video"
                                            and not sp_is_video
                                        ):
                                            visited_ids.add(sp["id"])
                                            continue
                                        filtered_similar_pins.append(sp)
                                except Exception:
                                    filtered_similar_pins.append(sp)

                            unvisited = filtered_similar_pins

                            if not unvisited:
                                print(
                                    "    滚动后没有新的相似推荐了，当前节点已是局部最优"
                                )
                                break

                    if not upgraded:
                        # 爬坡终止前冲刷剩余批量收集池
                        if pending_collect:
                            self.logger.info(
                                f"  [批量池] 爬坡终止前冲刷 {len(pending_collect)} 张"
                            )
                            flush_result = self._flush_batch_collect_pool(
                                pending_collect, self._current_keyword
                            )
                            q_delta, should_stop = self._apply_flush_result(
                                flush_result, collected_pins, collected_pin_ids,
                                visited_ids, target_count, source_label="爬坡终止"
                            )
                            qualified_count += q_delta
                            if q_delta > 0:
                                found_qualified = True
                                self.logger.info(f"  📊 已收集 {qualified_count}/{target_count} 个")
                                print(f"      [爬坡终止] 进度：{qualified_count}/{target_count}")
                            if should_stop:
                                self.logger.info(f"爬坡终止时已达到目标数量：{qualified_count}/{target_count}")
                                if self._coordinator:
                                    self._coordinator.set_task_complete(qualified_count)
                                return list(collected_pins.values())
                            pending_collect = []

                        if scroll_round >= max_scroll_rounds:
                            print(
                                f"  [深度{depth}] 已滚动{max_scroll_rounds}轮仍未找到更优跳板，已检查{checked_count}个推荐。返回搜索页更换起点。"
                            )
                        else:
                            print(
                                f"  [深度{depth}] 当前节点已是局部最优，已检查{checked_count}个推荐均不更优。返回搜索页更换起点。"
                            )
                        self._navigate_back_to_search(self._current_keyword)
                        break

                # 内层循环结束后冲刷剩余批量收集池
                if pending_collect:
                    self.logger.info(
                        f"  [批量池] 内层循环结束冲刷 {len(pending_collect)} 张"
                    )
                    flush_result = self._flush_batch_collect_pool(
                        pending_collect, self._current_keyword
                    )
                    q_delta, should_stop = self._apply_flush_result(
                        flush_result, collected_pins, collected_pin_ids,
                        visited_ids, target_count, source_label="深度循环"
                    )
                    qualified_count += q_delta
                    if q_delta > 0:
                        found_qualified = True
                        self.logger.info(f"  📊 已收集 {qualified_count}/{target_count} 个")
                        print(f"      [深度循环] 进度：{qualified_count}/{target_count}")
                    if should_stop:
                        self.logger.info(f"深度循环结束时已达到目标数量：{qualified_count}/{target_count}")
                        if self._coordinator:
                            self._coordinator.set_task_complete(qualified_count)
                        try:
                            self._navigate_back_to_search(self._current_keyword)
                        except Exception as e:
                            self.logger.warning(f"返回搜索页出错：{e}")
                        return list(collected_pins.values())
                    pending_collect = []

                if not found_qualified:
                    try:
                        self._close_pin_modal()
                        time.sleep(random.uniform(1, 2))
                        # 不再无条件返回搜索页
                        # 如果是因为爬坡无法继续（upgraded=False）而退出内层循环，
                        # _navigate_back_to_search 已在 not upgraded 分支中调用
                        # 如果是因为其他原因退出（如已访问pin），页面可能仍在详情页，
                        # 由外层循环的页面状态检查来处理
                    except Exception:
                        pass

                # 检查是否需要完全停止（每次内层循环结束后都要检查）
                if qualified_count >= target_count:
                    print(f"已收集{target_count}个，完全停止")
                    return list(collected_pins.values())

                time.sleep(random.uniform(2, 4))

        except Exception as e:
            print(f"\n探索过程出错: {e}")
            import traceback

            traceback.print_exc()

        self.logger.info(f"探索完成: 共收集 {len(collected_pins)} 个pin (尝试 {attempt} 次, 达标 {qualified_count} 个)")
        print(f"\n探索完成: 共收集 {len(collected_pins)} 个pin (尝试 {attempt} 次)")
        return list(collected_pins.values())

    def _scrape_similar_from_current_page(
        self, source_pin_id: str, collected_pins: dict, visited_ids: set
    ):
        """在当前达标pin的详情页爬取所有可见的相似推荐数据

        点击每个相似推荐 → 提取数据 → go_back → 继续下一个
        """
        similar_pins = self._find_similar_pins_in_modal()
        if not similar_pins:
            print("  当前详情页无相似推荐")
            return

        print(f"  发现 {len(similar_pins)} 个相似推荐，开始逐个提取数据...")

        for i, sp in enumerate(similar_pins):
            sp_id = sp["id"]
            if sp_id in collected_pins:
                print(f"    [{i + 1}/{len(similar_pins)}] pin {sp_id} 已收集，跳过")
                continue

            try:
                # 尝试多种选择器匹配详情链接
                similar_link = None
                selectors = [
                    f'a[href*="/pin/{sp_id}"]',
                    f'a[href*="pin/{sp_id}"]',
                    f'[href*="/pin/{sp_id}"]',
                ]
                for selector in selectors:
                    try:
                        el = self.page.query_selector(selector)
                        if el and el.is_visible():
                            similar_link = el
                            break
                    except:
                        continue

                if not similar_link:
                    print(f"      未找到 pin {sp_id} 的链接")
                    continue

                print(f"      点击相似推荐: {sp_id}")
                # 滚动到元素可见
                similar_link.scroll_into_view_if_needed()
                time.sleep(random.uniform(0.5, 1))
                similar_link.click()
                time.sleep(random.uniform(2, 4))

                sp_details = self._extract_pin_details_from_modal()
                if sp_details and sp_details.get("id"):
                    saves = sp_details.get("saves", 0) or 0
                    comments = sp_details.get("comments", 0) or 0
                    sp_is_video = sp_details.get("is_video", False)
                    video_url = sp_details.get("video_url", "")
                    images = sp_details.get("images", {})
                    sp_image_url = (
                        images.get("orig", {}).get("url", "")
                        if isinstance(images, dict)
                        else ""
                    )
                    sp_image_736x = (
                        images.get("736x", {}).get("url", "")
                        if isinstance(images, dict)
                        else ""
                    )

                similar_pin = Pin(
                    id=str(sp_id),
                    title=sp_details.get("title", ""),
                    description=sp_details.get("description", ""),
                    image_url=sp_image_url,
                    image_url_736x=sp_image_736x,
                    saves=saves,
                    comments=comments,
                    link=f"https://kr.pinterest.com/pin/{sp_id}/",
                    pinner=sp_details.get("pinner", ""),
                    source=f"similar_from_{source_pin_id}",
                    is_video=sp_is_video,
                    video_url=video_url,
                )
                collected_pins[sp_id] = similar_pin
                visited_ids.add(sp_id)
                print(f"      Saved: {saves} | Comments: {comments}")

            except Exception as e:
                print(f"    [{i + 1}/{len(similar_pins)}] 提取失败: {e}")
                self._safe_go_back()

    def _collect_similar_pins_from_qualified(
        self,
        qualified_pin_id: str,
        collected_pins: dict,
        visited_ids: set,
        target_count: int,
        min_saves: int = 0,
        qualified_count: int = 0,
    ) -> int:
        """在达标的详情页中收集相似推荐数据，返回更新后的 qualified_count"""
        print(f"    在达标详情页 {qualified_pin_id} 中收集相似推荐...")

        processed_in_this_page = set()
        batch_size = 8
        max_batches = 5

        for batch in range(max_batches):
            similar_pins = self._find_similar_pins_in_modal(scroll_times=1)
            if not similar_pins:
                print(f"    第{batch + 1}批: 没有更多推荐")
                break

            new_pins = [
                sp for sp in similar_pins if sp["id"] not in processed_in_this_page
            ]
            if not new_pins:
                print(f"    第{batch + 1}批: 本页已处理完")
                break

            batch_pins = new_pins[:batch_size]
            print(
                f"    第{batch + 1}批: 处理{len(batch_pins)}个，当前达标({qualified_count}/{target_count})"
            )

            for sp in batch_pins:
                sp_id = sp["id"]

                if sp_id in processed_in_this_page or sp_id in visited_ids:
                    continue
                processed_in_this_page.add(sp_id)

                # 用达标计数判断是否已完成
                if qualified_count >= target_count:
                    print(f"    已达标{qualified_count}个，停止")
                    return qualified_count

                try:
                    similar_link = self.page.query_selector(f'a[href*="/pin/{sp_id}"]')
                    if not similar_link:
                        continue

                    print(f"      点击相似推荐: {sp_id}")
                    similar_link.click()
                    time.sleep(random.uniform(2, 4))

                    sp_details = self._extract_pin_details_from_modal()
                    if sp_details and sp_details.get("id"):
                        saves = sp_details.get("saves", 0) or 0
                        comments = sp_details.get("comments", 0) or 0
                        sp_is_video = sp_details.get("is_video", False)

                        # 媒体类型筛选
                        if self.media_type != "all":
                            if self.media_type == "images" and sp_is_video:
                                print(f"        是视频，跳过")
                                self._back_to_parent_pin()
                                continue
                            if self.media_type == "video" and not sp_is_video:
                                print(f"        是图片，跳过")
                                self._back_to_parent_pin()
                                continue

                        # min_saves 筛选：不达标的不计入 qualified_count
                        if saves < min_saves:
                            print(
                                f"        saves={saves} < min_saves={min_saves}，跳过"
                            )
                            self._back_to_parent_pin()
                            continue

                        images = sp_details.get("images", {})
                        image_url = (
                            images.get("orig", {}).get("url", "")
                            if isinstance(images, dict)
                            else ""
                        )
                        image_736x = (
                            images.get("736x", {}).get("url", "")
                            if isinstance(images, dict)
                            else ""
                        )

                        if sp_id not in collected_pins:
                            pin = Pin(
                                id=str(sp_id),
                                title=sp_details.get("title", ""),
                                description=sp_details.get("description", ""),
                                image_url=image_url,
                                image_url_736x=image_736x,
                                saves=saves,
                                comments=comments,
                                link=f"https://kr.pinterest.com/pin/{sp_id}/",
                                pinner=sp_details.get("pinner", ""),
                                source=f"similar_from_{qualified_pin_id}",
                                is_video=sp_is_video,
                                video_url=sp_details.get("video_url", ""),
                            )
                            collected_pins[sp_id] = pin
                            visited_ids.add(sp_id)
                            qualified_count += 1
                            self.logger.info(
                                f"📊 已收集 {qualified_count}/{target_count} 个 (saves={saves}, is_video={sp_is_video})"
                            )
                            print(
                                f"        已收集({qualified_count}/{target_count}): saves={saves} is_video={sp_is_video}"
                            )

                            if self.progress_callback:
                                self.progress_callback(
                                    "enriching",
                                    qualified_count,
                                    target_count,
                                    f"达标页收集: {qualified_count}/{target_count}个",
                                )

                            if qualified_count >= target_count:
                                self._back_to_parent_pin()
                                return qualified_count

                    self._back_to_parent_pin()

                except Exception as e:
                    print(f"      收集失败: {e}")
                    self._back_to_parent_pin()

            print(f"    第{batch + 1}批完成")

            if not new_pins:
                break

            if batch < max_batches - 1:
                print(f"    滚动加载第{batch + 2}批...")
                try:
                    viewport = self.page.viewport_size
                    if viewport:
                        self.page.mouse.move(
                            viewport["width"] // 2, viewport["height"] // 2
                        )
                        self.page.mouse.wheel(0, 800)
                    time.sleep(random.uniform(2, 3))
                except Exception as e:
                    print(f"    滚动失败: {e}")
                    break

        print(f"    达标详情页收集完成，qualified_count={qualified_count}")
        return qualified_count

    def _back_to_parent_pin(self):
        """返回到原详情页（支持多种方式）"""
        print("      返回原详情页...")

        # 首先尝试浏览器后退（最可靠的方式回到上一页）
        if self._safe_go_back():
            print("      ✓ 已返回")
            return

        # 备用方式1: 按Escape关闭当前modal
        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
        except:
            pass

        # 备用方式2: 点击关闭按钮
        try:
            close_btn = self.page.query_selector('[data-test-id="close-button"]')
            if close_btn:
                close_btn.click()
                time.sleep(0.5)
        except:
            pass

        # 等待页面稳定
        time.sleep(random.uniform(1, 2))

    def _get_search_page_pins(self) -> tuple:
        """从搜索页同时提取 pin ID 列表和 ID→图片URL 映射（一次 JS 调用，确保一致性）
        
        Returns:
            (pin_ids: list, image_map: dict{str: str}) — {pin_id: image_url}
        """
        try:
            time.sleep(random.uniform(1, 2))

            result = self.page.evaluate("""
                () => {
                    // 辅助：从 img 提取有效 URL（懒加载支持：src → srcset → data-src → getAttribute）
                    const getImgUrl = (img) => {
                        if (!img) return '';
                        if (img.src && !img.src.startsWith('data:') && img.src.includes('pinimg'))
                            return img.src;
                        if (img.srcset) {
                            const parts = img.srcset.split(',');
                            for (const p of parts) {
                                const url = p.trim().split(' ')[0];
                                if (url && url.includes('pinimg')) return url;
                            }
                            const first = parts[0].trim().split(' ')[0];
                            if (first && first.startsWith('http')) return first;
                        }
                        const ds = img.getAttribute('data-src') || img.dataset?.src;
                        if (ds && ds.startsWith('http') && ds.includes('pinimg')) return ds;
                        const attr = img.getAttribute('src');
                        if (attr && attr.startsWith('http') && attr.includes('pinimg')) return attr;
                        return '';
                    };
                    
                    const ids = [];
                    const imageMap = {};
                    const seen = new Set();
                    const links = document.querySelectorAll('a[href*="/pin/"]');
                    let imgFound = 0, imgMiss = 0;

                    links.forEach(link => {
                        const match = link.href.match(/\\/pin\\/([0-9]+)/);
                        if (match && !seen.has(match[1])) {
                            seen.add(match[1]);
                            ids.push(match[1]);
                            // 在同一个 DOM 快照中提取图片
                            let img = link.querySelector('img');
                            if (!img) {
                                const parent = link.closest('[data-test-id="pin"], [data-testid="pin"], div');
                                if (parent) img = parent.querySelector('img');
                            }
                            if (!img) {
                                const container = link.closest('div');
                                if (container) img = container.querySelector('img');
                            }
                            const imgUrl = getImgUrl(img);
                            if (imgUrl) {
                                imageMap[match[1]] = imgUrl;
                                imgFound++;
                            } else {
                                imgMiss++;
                            }
                        }
                    });
                    
                    return {
                        ids,
                        imageMap,
                        totalLinks: links.length,
                        matchedIds: ids.length,
                        imgFound,
                        imgMiss
                    };
                }
            """)
            
            pin_ids = result.get("ids", []) if result else []
            image_map = result.get("imageMap", {}) if result else {}
            total = result.get("totalLinks", 0) if result else 0
            matched = result.get("matchedIds", 0) if result else 0
            img_ok = result.get("imgFound", 0) if result else 0
            img_fail = result.get("imgMiss", 0) if result else 0
            
            print(f"[DEBUG] 搜索页pin检测: 总链接={total}, pin数={matched}, 有图={img_ok}, 无图={img_fail}")
            
            # 保存到实例变量，供后续 AI 入口预筛使用
            self._search_image_map = image_map
            
            return pin_ids if pin_ids else [], image_map
        except Exception as e:
            print(f"[DEBUG] 获取搜索页pin失败: {e}")
            return [], {}

    def _apply_collection_ai_filter(self, pin_id: str, image_url: str) -> bool:
        """收集阶段 AI 深度筛选：风格匹配度、人物排除、场景完整性

        Args:
            pin_id: Pin ID
            image_url: 图片 URL

        Returns:
            True - 通过筛选，False - 未通过
        """
        if not self._ai_available or not image_url:
            return True

        try:
            # 先查协调器缓存（其他 Worker 可能已经筛选过此 pin）
            if self._coordinator:
                cached = self._coordinator.get_filter_result(pin_id)
                if cached is not None:
                    self.logger.info(f"[AI收集筛选] 🔄 命中缓存: {pin_id[:12]}... → approved={cached.get('is_approved', False)}")
                    is_interior_c = cached.get("is_interior", False)
                    is_approved_c = cached.get("is_approved", False)
                    if not is_interior_c or not is_approved_c:
                        return False
                    return True

            self.logger.info(f"[AI收集筛选] 正在评估: {pin_id[:12]}...")
            result = self._ai_manager.evaluate_pin_for_collection(
                image_url, self._current_keyword
            )

            # 写入协调器缓存（复用筛选结果）
            if self._coordinator and result:
                self._coordinator.set_filter_result(pin_id, result)

            is_interior = result.get("is_interior", False)
            style_match = result.get("style_match", 0)
            has_human = result.get("has_human", True)
            scene_completeness = result.get("scene_completeness", 0)
            is_approved = result.get("is_approved", False)
            reasoning = result.get("reasoning", "")

            self.logger.info(
                f"[AI收集筛选] 评分: is_interior={is_interior}, style_match={style_match}, "
                f"has_human={has_human}, scene_completeness={scene_completeness}, "
                f"approved={is_approved}"
            )

            if not is_interior:
                self.logger.info(f"[AI收集筛选] ❌ 非室内场景: {reasoning}")
                return False

            if not is_approved:
                self.logger.info(f"[AI收集筛选] ❌ 未通过: {reasoning}")
                return False

            self.logger.info(f"[AI收集筛选] ✅ 通过: {reasoning}")
            return True

        except Exception as e:
            self.logger.warning(f"[AI收集筛选] 评估失败: {e}，默认通过")
            return True

    def _apply_flush_result(
        self, flush_result, collected_pins, collected_pin_ids, visited_ids, target_count, source_label="批量"
    ):
        """处理批量冲刷结果：将通过的pin加入收集集，失败的加入已访问集

        Args:
            flush_result: _flush_batch_collect_pool 的返回值
            collected_pins: 已收集pin字典（可变，会被修改）
            collected_pin_ids: 已收集pin ID集合（可变，会被修改）
            visited_ids: 已访问ID集合（可变，会被修改）
            target_count: 目标数量
            source_label: 日志标签

        Returns:
            (qualified_delta, should_stop): 新增达标数量 / 是否达到目标应停止
        """
        qualified_delta = 0

        for item, result in flush_result["passed"]:
            sp_image_736x = (
                item["sp_images"].get("736x", {}).get("url", "")
                if isinstance(item["sp_images"], dict)
                else ""
            )
            similar_pin = Pin(
                id=str(item["pin_id"]),
                title=item["sp_details"].get("title", ""),
                description=item["sp_details"].get("description", ""),
                image_url=item["image_url"],
                image_url_736x=sp_image_736x,
                saves=item["sp_saves"],
                comments=item["sp_details"].get("comments", 0) or 0,
                link=f"https://kr.pinterest.com/pin/{item['pin_id']}/",
                pinner=item["sp_details"].get("pinner", ""),
                source=source_label,
                is_video=item["sp_is_video"],
                video_url=item["sp_details"].get("video_url", ""),
            )
            collected_pins[item["pin_id"]] = similar_pin
            qualified_delta += 1
            collected_pin_ids.add(item["pin_id"])
            if self._coordinator:
                self._coordinator.mark_collected(
                    item["pin_id"],
                    saves=item["sp_saves"],
                    title=item["sp_details"].get("title", ""),
                )
            self.logger.info(
                f"  [{source_label}] 收集达标 pin: {item['pin_id']} (saves={item['sp_saves']})"
            )

        for failed_id in flush_result["failed"]:
            visited_ids.add(failed_id)

        total_qualified = len([p for p in collected_pins.values() if p.saves >= 0])
        should_stop = total_qualified >= target_count if qualified_delta > 0 else False

        return qualified_delta, should_stop

    def _flush_batch_collect_pool(self, pool: list, keyword: str) -> dict:
        """冲刷批量收集池 — 一次 API 调用评估多张图

        已通过爬坡AI筛选的pin会从协调器缓存中获取结果，跳过重复评估。

        Args:
            pool: 待评估列表，每项为 {pin_id, image_url, sp_saves, sp_details, sp_images, sp_is_video}
            keyword: 当前查询词

        Returns:
            {"passed": [(item, result_dict), ...], "failed": [pin_id, ...]}
        """
        if not pool:
            return {"passed": [], "failed": []}

        passed = []
        failed = []
        need_eval = []  # 需要AI评估的项

        for item in pool:
            pin_id = item["pin_id"]
            if not item["image_url"]:
                failed.append(pin_id)
                continue

            cached_result = None
            if self._coordinator:
                cached_result = self._coordinator.get_filter_result(pin_id)

            if cached_result is not None:
                is_approved = cached_result.get("is_approved", False)
                is_interior = cached_result.get("is_interior", True)
                if is_approved and is_interior:
                    self.logger.info(
                        f"[批量收集] 🔄 缓存命中✅: {pin_id[:12]}... → 直接通过"
                    )
                    passed.append((item, cached_result))
                else:
                    self.logger.info(
                        f"[批量收集] 🔄 缓存命中❌: {pin_id[:12]}... → {cached_result.get('reasoning', '')}"
                    )
                    failed.append(pin_id)
            else:
                need_eval.append(item)

        if not need_eval:
            self.logger.info(
                f"[批量收集] 全部{len(pool)}张已有缓存结果，无需AI评估 (通过{len(passed)}/未通过{len(failed)})"
            )
            return {"passed": passed, "failed": failed}

        image_urls = [item["image_url"] for item in need_eval]
        self.logger.info(
            f"[批量收集] 开始评估 {len(image_urls)} 张 (缓存命中{len(pool) - len(need_eval)}张，共{len(pool)}张)"
        )

        try:
            results = self._ai_manager.evaluate_pins_batch(
                image_urls, keyword, batch_size=len(image_urls)
            )
        except Exception as e:
            self.logger.warning(f"[批量收集] 批量评估异常: {e}，全部跳过")
            failed.extend(item["pin_id"] for item in need_eval)
            return {"passed": passed, "failed": failed}

        for result in results:
            idx = result.get("index", -1)
            if idx < 0 or idx >= len(need_eval):
                continue
            item = need_eval[idx]
            if result.get("is_approved"):
                if result.get("is_interior", True):
                    passed.append((item, result))
                    if self._coordinator:
                        self._coordinator.set_filter_result(item["pin_id"], result)
                else:
                    self.logger.info(
                        f"[批量收集] ❌ {item['pin_id'][:12]}... 非室内: {result.get('reasoning', '')}"
                    )
                    failed.append(item["pin_id"])
                    if self._coordinator:
                        self._coordinator.set_filter_result(item["pin_id"], result)
            else:
                self.logger.info(
                    f"[批量收集] ❌ {item['pin_id'][:12]}...: {result.get('reasoning', '')}"
                )
                failed.append(item["pin_id"])
                if self._coordinator:
                    self._coordinator.set_filter_result(item["pin_id"], result)

        self.logger.info(
            f"[批量收集] ✅ 完成: {len(passed)} 通过 / {len(failed)} 未通过"
        )
        return {"passed": passed, "failed": failed}

    def _get_pin_image_url_from_search(self, pin_id: str) -> str:
        """从搜索页获取指定 pin 的图片 URL
        
        Args:
            pin_id: Pin ID
            
        Returns:
            图片 URL 或空字符串
        """
        try:
            # 先记录页面 URL，排查页面是否在搜索页
            page_url = ""
            try:
                page_url = self.page.url
            except Exception:
                pass

            result = self.page.evaluate(
                """
                (pinId) => {
                    const debugInfo = { found: false, hasImgElement: false, hasImgSrc: false, imgSrc: '', totalLinks: 0, matchedLink: false, searchMethods: [] };

                    // 辅助函数：从 img 元素提取可用 URL（处理懒加载：src → srcset → data-src → getAttribute）
                    const getImgUrl = (img) => {
                        if (!img) return '';
                        // 1. 直接 src
                        if (img.src && !img.src.startsWith('data:')) return img.src;
                        // 2. srcset（Pinterest 主流懒加载属性）
                        if (img.srcset) {
                            const parts = img.srcset.split(',');
                            for (const part of parts) {
                                const url = part.trim().split(' ')[0];
                                if (url && url.includes('pinimg')) return url;
                            }
                            // 没有 pinimg 的，取第一个图片 URL
                            const firstUrl = parts[0].trim().split(' ')[0];
                            if (firstUrl && firstUrl.startsWith('http')) return firstUrl;
                        }
                        // 3. data-src（某些懒加载库）
                        const dataSrc = img.getAttribute('data-src') || img.dataset.src;
                        if (dataSrc && dataSrc.startsWith('http')) return dataSrc;
                        // 4. getAttribute('src') （Playwright 可能返回实际加载的 URL）
                        const attrSrc = img.getAttribute('src');
                        if (attrSrc && !attrSrc.startsWith('data:') && attrSrc.startsWith('http')) return attrSrc;
                        return '';
                    };
                    
                    // 方法1: 直接查找 a[href*="/pin/"]
                    let links = document.querySelectorAll('a[href*="/pin/"');
                    debugInfo.totalLinks = links.length;
                    debugInfo.searchMethods.push('direct-link');
                    
                    for (const link of links) {
                        const match = link.href.match(/\\/pin\\/([0-9]+)/);
                        if (match && match[1] === pinId) {
                            debugInfo.found = true;
                            debugInfo.matchedLink = true;
                            // 查找图片 - 可能在link内或父级容器内
                            let img = link.querySelector('img');
                            if (!img) {
                                // 尝试在父级容器查找
                                const parent = link.closest('[data-test-id="pin"], [data-testid="pin"], div[style]');
                                if (parent) img = parent.querySelector('img');
                            }
                            if (!img) {
                                // 尝试在相邻元素查找
                                const container = link.closest('div');
                                if (container) img = container.querySelector('img');
                            }
                            if (img) {
                                debugInfo.hasImgElement = true;
                                const imgUrl = getImgUrl(img);
                                if (imgUrl) {
                                    debugInfo.hasImgSrc = true;
                                    debugInfo.imgSrc = imgUrl;
                                    return { url: imgUrl.replace('/236x/', '/736x/').replace('/474x/', '/736x/'), debug: debugInfo };
                                }
                            }
                            break; // 找到匹配链接就停止，不用继续搜索
                        }
                    }
                    
                    // 方法2: 通过 data-pin-id 属性查找
                    debugInfo.searchMethods.push('data-pin-id');
                    const pinElements = document.querySelectorAll('[data-pin-id="' + pinId + '"]');
                    for (const el of pinElements) {
                        debugInfo.found = true;
                        debugInfo.matchedLink = true;
                        const img = el.querySelector('img');
                        if (img) {
                            debugInfo.hasImgElement = true;
                            const imgUrl = getImgUrl(img);
                            if (imgUrl) {
                                debugInfo.hasImgSrc = true;
                                debugInfo.imgSrc = imgUrl;
                                return { url: imgUrl.replace('/236x/', '/736x/').replace('/474x/', '/736x/'), debug: debugInfo };
                            }
                        }
                    }
                    
                    // 方法3: 查找所有图片，通过父级链接匹配
                    debugInfo.searchMethods.push('img-parent-link');
                    const allImgs = document.querySelectorAll('img[src*="pinimg"], img[srcset*="pinimg"]');
                    for (const img of allImgs) {
                        const parentLink = img.closest('a[href*="/pin/"');
                        if (parentLink) {
                            const match = parentLink.href.match(/\\/pin\\/([0-9]+)/);
                            if (match && match[1] === pinId) {
                                debugInfo.found = true;
                                debugInfo.matchedLink = true;
                                debugInfo.hasImgElement = true;
                                const imgUrl = getImgUrl(img);
                                if (imgUrl) {
                                    debugInfo.hasImgSrc = true;
                                    debugInfo.imgSrc = imgUrl;
                                    return { url: imgUrl.replace('/236x/', '/736x/').replace('/474x/', '/736x/'), debug: debugInfo };
                                }
                            }
                        }
                    }
                    
                    return { url: '', debug: debugInfo };
                }
                """,
                pin_id
            )
            if isinstance(result, dict):
                debug = result.get('debug', {})
                url = result.get('url', '')
                if not url:
                    self.logger.warning(
                        f"[AI筛选] pin {pin_id} 图片获取失败 | "
                        f"页面={page_url[:80]} | "
                        f"页面上总链接={debug.get('totalLinks', '?')} | "
                        f"找到匹配链接={debug.get('matchedLink', '?')} | "
                        f"有img元素={debug.get('hasImgElement', '?')} | "
                        f"有imgSrc={debug.get('hasImgSrc', '?')}"
                    )
                return url
            return result if result else ""
        except Exception as e:
            self.logger.warning(f"[AI筛选] 获取 pin {pin_id} 图片URL异常: {e}")
            return ""

    def _scroll_page(self):
        """滚动页面 - 使用 PageDown 键"""
        self._scroll_page_with_pgdn()

    def _scroll_page_with_pgdn(self):
        """使用 PageDown 键滚动页面 - 单次点击，确保一次调用只滚动一次"""
        try:
            # 点击 PGDN 键滚动一次
            self.page.keyboard.press("PageDown")
            print(f"  页面滚动：1 次 (PGDN)")
            # 滚动后等待页面加载
            time.sleep(random.uniform(2, 3))

        except Exception as e:
            print(f"页面滚动出错：{e}")
            try:
                # 备用方式：JavaScript 滚动（如果键盘滚动失败）
                self.page.evaluate("window.scrollBy(0, window.innerHeight);")
                time.sleep(random.uniform(2, 3))
            except Exception:
                pass
            except:
                pass

        # 最终等待确保所有内容加载完成
        time.sleep(random.uniform(2, 4))

    def _get_visible_pin_elements(self, media_type: str = "all") -> list:
        """获取当前视口内可见的 pin 元素

        Args:
            media_type: 媒体类型筛选 all/images/videos
        """
        try:
            # 使用 JavaScript 查找视口内的 pin 链接，并返回调试信息
            result = self.page.evaluate(
                """
                (mediaType) => {
                    const pins = [];
                    const processedIds = new Set();
                    const debugInfo = {
                        totalLinks: 0,
                        validPinLinks: 0,
                        inViewportCount: 0,
                        outViewportCount: 0,
                        viewportSize: { width: window.innerWidth, height: window.innerHeight },
                        sampleOutViewport: []  // 记录部分超出视口的元素示例
                    };

                    // 查找所有 pin 链接
                    const pinLinks = document.querySelectorAll('a[href*="/pin/"]');
                    debugInfo.totalLinks = pinLinks.length;

                    pinLinks.forEach(link => {
                        try {
                            // 提取 pin ID
                            const match = link.href.match(/\\/pin\\/([0-9]+)/);
                            if (!match) return;

                            debugInfo.validPinLinks++;
                            const pinId = match[1];
                            if (processedIds.has(pinId)) return;

                            // 检查是否在视口内
                            const rect = link.getBoundingClientRect();
                            const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                            const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                            
                            // 严格视口检测
                            const inViewport = (
                                rect.top >= 0 &&
                                rect.left >= 0 &&
                                rect.bottom <= viewportHeight &&
                                rect.right <= viewportWidth
                            );
                            
                            // 宽松检测：元素部分可见
                            const partiallyVisible = (
                                rect.top < viewportHeight &&
                                rect.bottom > 0 &&
                                rect.left < viewportWidth &&
                                rect.right > 0
                            );

                            if (inViewport) {
                                debugInfo.inViewportCount++;
                            } else if (partiallyVisible) {
                                debugInfo.outViewportCount++;
                                // 记录示例
                                if (debugInfo.sampleOutViewport.length < 3) {
                                    debugInfo.sampleOutViewport.push({
                                        id: pinId,
                                        rect: { top: Math.round(rect.top), bottom: Math.round(rect.bottom), left: Math.round(rect.left), right: Math.round(rect.right) },
                                        viewport: { width: viewportWidth, height: viewportHeight }
                                    });
                                }
                            }

                            if (inViewport) {
                                // 媒体类型检测
                                let isVideo = false;
                                const imgElement = link.querySelector('img');
                                if (imgElement) {
                                    const src = imgElement.src || '';
                                    const alt = imgElement.alt || '';
                                    // Pinterest 视频通常有特定标识
                                    isVideo = src.includes('/video/') || 
                                              src.includes('video') || 
                                              alt.includes('video') ||
                                              link.querySelector('[data-test-id="video-pin"]') !== null;
                                }
                                
                                // 根据媒体类型过滤
                                if (mediaType === 'images' && isVideo) return;
                                if (mediaType === 'video' && !isVideo) return;

                                processedIds.add(pinId);
                                pins.push({
                                    id: pinId,
                                    element: link,
                                    is_video: isVideo
                                });
                            }
                        } catch (e) {
                            // 跳过解析失败的元素
                        }
                    });

                    return { pins, debugInfo };
                }
            """,
                media_type,
            )

            # 解析结果
            visible_pins = result.get("pins", [])
            debug_info = result.get("debugInfo", {})

            # 输出调试信息
            print(f"[DEBUG] 视口检测: {debug_info.get('inViewportCount', 0)} 个完全在视口内, {debug_info.get('outViewportCount', 0)} 个部分可见但超出边界")
            print(f"[DEBUG] 视口大小: {debug_info.get('viewportSize', {})}")
            print(f"[DEBUG] 总链接数: {debug_info.get('totalLinks', 0)}, 有效pin链接: {debug_info.get('validPinLinks', 0)}")
            
            if debug_info.get("sampleOutViewport"):
                print(f"[DEBUG] 部分超出视口的示例: {debug_info.get('sampleOutViewport')}")

            if self.debug:
                print(f"发现 {len(visible_pins)} 个可见 pin (媒体类型：{media_type})")

            return visible_pins

        except Exception as e:
            print(f"[DEBUG] 获取可见 pin 失败：{e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return []

    def _close_pin_modal(self):
        """关闭 pin 详情模态框"""
        if not self._is_page_alive():
            return

        try:
            # 尝试按 Escape 键关闭
            self.page.keyboard.press("Escape")
            time.sleep(1)

            if not self._is_page_alive():
                return

            # 检查模态框是否已关闭
            modal_closed = self.page.evaluate("""
                () => {
                    const modal = document.querySelector('[data-test-id="close-button"]');
                    return !modal;
                }
            """)

            if not modal_closed:
                # 如果 Escape 键无效，尝试点击关闭按钮
                try:
                    if not self._is_page_alive():
                        return
                    close_button = self.page.query_selector(
                        '[data-test-id="close-button"]'
                    )
                    if close_button:
                        close_button.click()
                        time.sleep(1)
                except:
                    pass

        except Exception as e:
            if self.debug:
                print(f"关闭模态框时出错: {e}")

    def _find_similar_pins_in_modal(
        self, scroll_times: int = 1, exclude_ids: set = None
    ) -> list:
        """在 pin 详情模态框中查找相似推荐

        Args:
            scroll_times: 滚动次数，1表示只获取当前可见，>1会滚动加载更多
            exclude_ids: 要排除的pin ID集合（如已访问的）

        Returns:
            相似推荐列表（不包含exclude_ids中的）
        """
        if exclude_ids is None:
            exclude_ids = set()

        try:
            all_pins = []
            seen_ids = set()

            # 获取当前页面的 pin ID，避免把自身加入相似推荐列表
            current_page_pin_id = ""
            try:
                url_match = self.page.evaluate("""
                    () => {
                        const m = window.location.pathname.match(/\\/pin\\/([0-9]+)/);
                        return m ? m[1] : '';
                    }
                """)
                current_page_pin_id = url_match or ""
            except Exception:
                pass

            for scroll in range(scroll_times):
                # 查找当前可见的所有 pin（同时提取每个 pin 卡片上的 saves 数）
                similar_pins = self.page.evaluate("""
                    () => {
                        function parseSaves(str) {
                            if (!str) return 0;
                            let cleaned = str.replace(/,/g, '').trim();
                            const match = cleaned.match(/^([\\d.]+)\\s*([kKmM])?$/);
                            if (!match) return parseInt(cleaned) || 0;
                            let num = parseFloat(match[1]);
                            const unit = (match[2] || '').toLowerCase();
                            if (unit === 'k') num *= 1000;
                            if (unit === 'm') num *= 1000000;
                            return Math.round(num);
                        }
                        const pins = [];
                        const processedIds = new Set();

                        // 查找所有 pin 链接（在模态框内）
                        const pinLinks = document.querySelectorAll('a[href*="/pin/"]');

                        pinLinks.forEach(link => {
                            try {
                                const match = link.href.match(/\\/pin\\/([0-9]+)/);
                                if (!match) return;

                                const pinId = match[1];
                                if (processedIds.has(pinId)) return;

                                processedIds.add(pinId);

                                // 尝试从 pin 卡片中提取 saves
                                let saves = 0;
                                // 向上查找卡片容器
                                const card = link.closest('[data-test-id*="pin"]') 
                                    || link.closest('[data-grid-item]')
                                    || link.parentElement?.parentElement;
                                
                                if (card) {
                                    // 在卡片内查找 saves 相关元素
                                    const saveEls = card.querySelectorAll(
                                        '[data-test-id*="save"], [aria-label*="save" i], ' +
                                        'div[style*="margin"], span[style*="font"]'
                                    );
                                    for (const el of saveEls) {
                                        const text = (el.textContent || '').trim();
                                        const num = parseSaves(text);
                                        if (num > 0) { saves = num; break; }
                                    }
                                    // 如果还没找到，扫描卡片内所有文本片段
                                    if (!saves) {
                                        const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
                                        while (walker.nextNode()) {
                                            const text = walker.currentNode.textContent.trim();
                                            const num = parseSaves(text);
                                            if (num > 0) { saves = num; break; }
                                        }
                                    }
                                }

                                pins.push({
                                    id: pinId,
                                    href: link.href,
                                    card_saves: saves
                                });
                            } catch (e) {
                                // 跳过
                            }
                        });

                        return pins;
                    }
                """)

                # 记录新发现的 pins（排除已访问的、已记录的、当前页面自身）
                new_found = 0
                for pin in similar_pins:
                    pin_id = pin["id"]
                    if pin_id in seen_ids or pin_id in exclude_ids:
                        continue
                    if pin_id == current_page_pin_id:
                        continue
                    seen_ids.add(pin_id)
                    all_pins.append(pin)
                    new_found += 1

                if self.debug and scroll_times > 1:
                    print(
                        f"  滚动 {scroll + 1}/{scroll_times}: 发现 {new_found} 个新推荐，累计 {len(all_pins)} 个"
                    )

                # 如果不是最后一次滚动，尝试滚动加载更多
                if scroll < scroll_times - 1:
                    try:
                        viewport = self.page.viewport_size
                        if viewport:
                            center_x = viewport["width"] // 2
                            center_y = viewport["height"] // 2
                            self.page.mouse.move(center_x, center_y)
                            self.page.mouse.wheel(0, 800)
                        else:
                            self.page.keyboard.press("PageDown")
                    except Exception as e:
                        if self.debug:
                            print(f"    滚动失败: {e}")
                        try:
                            self.page.keyboard.press("PageDown")
                        except:
                            pass

                    time.sleep(random.uniform(2, 3))

            # 返回所有找到的相似推荐
            return all_pins

        except Exception as e:
            if self.debug:
                print(f"查找相似推荐失败: {e}")
            return []

    def _extract_pin_details_from_modal(self) -> dict:
        try:
            pin_data = self.page.evaluate("""
                () => {
                    const debugInfo = {
                        method: null,
                        pwsDataExists: false,
                        pinsCount: 0,
                        pinResourceCount: 0,
                        extractedPin: null,
                        errors: []
                    };
                    
                    function extractFromPWSData() {
                        const script = document.getElementById('__PWS_DATA__');
                        if (!script) {
                            debugInfo.errors.push('PWS_DATA script not found');
                            return null;
                        }
                        debugInfo.pwsDataExists = true;
                        try {
                            const data = JSON.parse(script.textContent);
                            const props = data.props || {};
                            const initialState = props.initialReduxState || {};
                            const pins = initialState.pins || {};
                            const resources = initialState.resources || {};
                            const pinResource = resources.PinResource || {};
                            
                            debugInfo.pinsCount = Object.keys(pins).length;
                            debugInfo.pinResourceCount = Object.keys(pinResource).length;
                            
                            for (const [id, pin] of Object.entries(pins)) {
                                const aggData = pin.aggregated_pin_data || {};
                                const stats = aggData.aggregated_stats || {};
                                let isVideo = false;
                                let videoUrl = '';
                                if (pin.videos && Object.keys(pin.videos).length > 0) {
                                    isVideo = true;
                                    const videoList = pin.videos.video_list || {};
                                    for (const quality of ['V_720P', 'V_480P', 'V_360P']) {
                                        if (videoList[quality] && videoList[quality].url) {
                                            videoUrl = videoList[quality].url;
                                            break;
                                        }
                                    }
                                }
                                
                                const result = {
                                    id: id,
                                    title: pin.grid_title || pin.title || '',
                                    description: pin.description || '',
                                    saves: parseInt(stats.saves) || 0,
                                    comments: parseInt(aggData.comment_count) || 0,
                                    pinner: (pin.pinner || {}).username || '',
                                    images: pin.images || {},
                                    is_video: isVideo,
                                    video_url: videoUrl
                                };
                                debugInfo.method = 'PWS_DATA.pins';
                                debugInfo.extractedPin = { id: result.id, saves: result.saves };
                                return result;
                            }
                            for (const [key, resource] of Object.entries(pinResource)) {
                                if (resource && resource.data) {
                                    const pin = resource.data;
                                    const aggData = pin.aggregated_pin_data || {};
                                    const stats = aggData.aggregated_stats || {};
                                    let isVideo = false;
                                    let videoUrl = '';
                                    if (pin.videos && Object.keys(pin.videos).length > 0) {
                                        isVideo = true;
                                        const videoList = pin.videos.video_list || {};
                                        for (const quality of ['V_720P', 'V_480P', 'V_360P']) {
                                            if (videoList[quality] && videoList[quality].url) {
                                                videoUrl = videoList[quality].url;
                                                break;
                                            }
                                        }
                                    }
                                    
                                    const result = {
                                        id: String(pin.id || key),
                                        title: pin.grid_title || pin.title || '',
                                        description: pin.description || '',
                                        saves: parseInt(stats.saves) || 0,
                                        comments: parseInt(aggData.comment_count) || 0,
                                        pinner: (pin.pinner || {}).username || '',
                                        images: pin.images || {},
                                        is_video: isVideo,
                                        video_url: videoUrl
                                    };
                                    debugInfo.method = 'PWS_DATA.PinResource';
                                    debugInfo.extractedPin = { id: result.id, saves: result.saves };
                                    return result;
                                }
                            }
                            debugInfo.errors.push('PWS_DATA: no pin data found');
                            return null;
                        } catch (e) {
                            debugInfo.errors.push('PWS_DATA parse error: ' + e.message);
                            return null;
                        }
                    }
                    function parseFlexibleNumber(str) {
                        if (!str) return 0;
                        let cleaned = str.replace(/,/g, '').trim();
                        const match = cleaned.match(/^([\\d.]+)\\s*([kKmM])?$/);
                        if (!match) return parseInt(cleaned) || 0;
                        let num = parseFloat(match[1]);
                        const unit = (match[2] || '').toLowerCase();
                        if (unit === 'k') num *= 1000;
                        if (unit === 'm') num *= 1000000;
                        return Math.round(num);
                    }
                    
                    function extractFromDOM() {
                        let saves = 0, comments = 0, title = '', description = '', pinId = '';
                        const urlMatch = window.location.pathname.match(/\\/pin\\/([0-9]+)/);
                        if (urlMatch) pinId = urlMatch[1];
                        const allText = document.body.innerText || '';
                        
                        // 尝试从 aria-label 等属性中获取 engagement 数据
                        function findEngagementFromAria() {
                            const elements = document.querySelectorAll('[aria-label]');
                            for (const el of elements) {
                                const label = el.getAttribute('aria-label') || '';
                                const saveMatch = label.match(/([\\d,.]+[kKmM]?)\\s*(saves?|saved|保存|收藏|likes?|reactions?|赞|反[应馈])/i);
                                if (saveMatch && !saves) {
                                    saves = parseFlexibleNumber(saveMatch[1]);
                                }
                            }
                        }
                        findEngagementFromAria();
                        
                        // 正则匹配 body 文本（支持 K/M 缩略格式）
                        // 把 saves 和 likes/reactions 都当作保存数合并
                        const flexNum = '([\\d][\\d,.]*[kKmM]?)';
                        const engagementPatterns = [
                            new RegExp(flexNum + '\\\\s*(saves?|saved|保存|收藏|likes?|reactions?|赞|反[应馈])', 'i'),
                            new RegExp('(saves?|saved|保存|收藏|likes?|reactions?|赞|反[应馈])\\\\s*' + flexNum, 'i'),
                        ];
                        for (const pat of engagementPatterns) {
                            const m = allText.match(pat);
                            if (m) { saves = saves || parseFlexibleNumber(m[1] || m[2]); break; }
                        }
                        // Pinterest 特定元素：reaction count
                        if (!saves) {
                            const reactionEls = document.querySelectorAll(
                                '[data-test-id="reactions"], [data-test-id*="reaction"], ' +
                                '[aria-label*="like" i], [aria-label*="react" i], ' +
                                '[aria-label*="save" i], ' +
                                'button[aria-label*="like" i] span, ' +
                                '[data-test-id="social-actions"] [data-test-id]'
                            );
                            for (const el of reactionEls) {
                                const text = (el.textContent || '').trim();
                                const num = parseFlexibleNumber(text);
                                if (num > 0) { saves = num; break; }
                            }
                        }
                        const commentPatterns = [
                            new RegExp(flexNum + '\\\\s*(comments?|评论)', 'i'),
                            new RegExp('(comments?|评论)\\\\s*' + flexNum, 'i'),
                        ];
                        for (const pat of commentPatterns) {
                            const m = allText.match(pat);
                            if (m) { comments = comments || parseFlexibleNumber(m[1] || m[2]); break; }
                        }
                        const titleEl = document.querySelector('[data-test-id="pin-title"]')
                            || document.querySelector('h1');
                        if (titleEl) title = titleEl.textContent.trim();
                        const imgEl = document.querySelector('img[src*="pinimg"]');
                        let imageUrl = '';
                        if (imgEl) imageUrl = imgEl.src || '';
                        let isVideo = false;
                        let videoUrl = '';
                        const videoElement = document.querySelector('[data-test-id="pinrep-video"]');
                        if (videoElement) {
                            isVideo = true;
                            const durationEl = document.querySelector('[data-test-id="PinTypeIdentifier"] span');
                            if (durationEl) {
                                isVideo = true;
                            }
                        }
                        
                        if (pinId) {
                            debugInfo.method = 'DOM';
                            debugInfo.errors = [];  // 清除 PWS_DATA 阶段的残留错误（DOM 提取已成功）
                            debugInfo.extractedPin = { id: pinId, saves: saves, title: title.substring(0, 30) };
                            return {
                                id: pinId,
                                title: title,
                                description: description,
                                saves: saves,
                                comments: comments,
                                pinner: '',
                                images: imageUrl ? { orig: { url: imageUrl } } : {},
                                is_video: isVideo,
                                video_url: videoUrl
                            };
                        }
                        debugInfo.errors.push('DOM: no data extracted');
                        return null;
                    }
                    
                    const result = extractFromPWSData() || extractFromDOM();
                    return { data: result, debugInfo: debugInfo };
                }
            """)
            
            debug_info = pin_data.get("debugInfo", {}) if pin_data else {}
            actual_data = pin_data.get("data", {}) if pin_data else {}
            
            self.logger.debug(f"[提取详情] 方法: {debug_info.get('method', 'None')}")
            self.logger.debug(f"[提取详情] PWS_DATA存在: {debug_info.get('pwsDataExists', False)}, pins数量: {debug_info.get('pinsCount', 0)}, PinResource数量: {debug_info.get('pinResourceCount', 0)}")
            if debug_info.get('extractedPin'):
                self.logger.debug(f"[提取详情] 提取到的pin: {debug_info.get('extractedPin')}")
            if debug_info.get('errors') and not actual_data:
                self.logger.warning(f"[提取详情] 错误信息: {debug_info.get('errors')}")

            if actual_data:
                images = actual_data.get("images", {})
                image_url = (
                    images.get("orig", {}).get("url", "")
                    if isinstance(images, dict)
                    else ""
                )
                image_url_736x = (
                    images.get("736x", {}).get("url", "")
                    if isinstance(images, dict)
                    else ""
                )
                actual_data["image_url"] = image_url
                actual_data["image_url_736x"] = image_url_736x

            return actual_data if actual_data else {}

        except Exception as e:
            if self.debug:
                print(f"从模态框提取详情失败: {e}")
            return {}

    def _navigate_back_to_search(self, keyword: str):
        """安全返回搜索页

        策略：
        1. 模态框关闭（保护 SPA 状态，最优）
        2. 浏览器后退（SPA history.back）
        3. URL 直接跳转（最后手段，但最可靠）
        注意：浏览器后退只回退一步，深度爬坡后回退会停在上一级 pin 而非搜索页。
        此时用保存的 _search_page_url 直接跳转是唯一正确的方式。
        """
        if not self._is_page_alive():
            self.logger.warning("[_navigate_back_to_search] 页面已失效，无法返回")
            return

        try:
            current_url = self.page.url
        except Exception:
            self.logger.warning("[_navigate_back_to_search] 无法获取当前URL")
            return

        if "/search/" in current_url:
            return

        print(f"  返回搜索结果页...")
        try:
            # 第1层：优先尝试关闭模态框（Pinterest 最常见的交互，不会破坏瀑布流）
            self._close_pin_modal()
            time.sleep(random.uniform(1.5, 2.5))

            if not self._is_page_alive():
                return

            if "/search/" in self.page.url:
                return  # 弹窗关闭成功

            # 第2层：浏览器后退
            # 注意：深度爬坡后浏览器回退一步只会到上一级 pin 页，不会到搜索页。
            # 因此后退后 URL 仍在 /pin/ 上时，直接跳到第3层 URL 跳转。
            print("  弹窗关闭无效，尝试使用浏览器后退...")
            self._safe_go_back()
            time.sleep(random.uniform(1, 2))

            if "/search/" in self.page.url:
                return  # 浏览器后退成功（浅深度时有效）

            # 第3层：用保存的搜索页 URL 直接跳转（最后手段，深度爬坡的必经之路）
            if self._search_page_url:
                print(f"  浏览器后退无效（仍在 pin 页），用 URL 跳转: {self._search_page_url[:80]}...")
                try:
                    self.page.goto(
                        self._search_page_url,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    time.sleep(random.uniform(5, 8))
                except Exception as goto_err:
                    self.logger.error(
                        f"[_navigate_back_to_search] URL 跳转也失败: {goto_err}"
                    )
            else:
                self.logger.warning("[_navigate_back_to_search] _search_page_url 为空，无法跳转")

        except Exception as e:
            print(f"  返回搜索页出错: {e}")
            time.sleep(2)

    def _interact_with_pin(
        self, pin_id: str, main_pin_count: int, collected_pins: dict, keyword: str = ""
    ):
        try:
            pin_link = self.page.query_selector(f'a[href*= "/pin/{pin_id}"]')
            if not pin_link:
                if self.debug:
                    print(f"未找到 pin {pin_id} 的元素")
                return

            print(f"  点击查看 pin {pin_id}")
            pin_link.click()
            time.sleep(random.uniform(2, 4))

            details = self._extract_pin_details_from_modal()
            if details and details.get("id"):
                if pin_id in collected_pins:
                    pin = collected_pins[pin_id]
                    pin.title = details.get("title", pin.title)
                    pin.description = details.get("description", pin.description)
                    pin.saves = details.get("saves", 0)
                    pin.comments = details.get("comments", 0)
                    pin.pinner = details.get("pinner", " ")

            # 根据主pin数量动态调整相似推荐采集数量
            if main_pin_count <= 20:
                max_similar = random.randint(3, 5)
            else:
                max_similar = random.randint(1, 2)

            similar_pins = self._find_similar_pins_in_modal()
            if similar_pins and len(similar_pins) > 0:
                selected_similar = random.sample(
                    similar_pins, min(max_similar, len(similar_pins))
                )
                print(
                    f"  发现 {len(similar_pins)} 个相似推荐，选择 {len(selected_similar)} 个"
                )

                for similar_pin_info in selected_similar:
                    similar_id = similar_pin_info["id"]
                    if similar_id in collected_pins:
                        continue

                    try:
                        similar_link = self.page.query_selector(
                            f'a[href*= "/pin/{similar_id}"]'
                        )
                        if similar_link:
                            print(f"    点击相似推荐 {similar_id}")
                            similar_link.click()
                            time.sleep(random.uniform(2, 5))

                            similar_details = self._extract_pin_details_from_modal()
                            if similar_details and similar_details.get("id"):
                                is_video = similar_details.get("is_video", False)
                                video_url = similar_details.get("video_url", " ")

                                # 媒体类型过滤
                                if self.media_type == "images" and is_video:
                                    self._safe_go_back()
                                    continue
                                if self.media_type == "video" and not is_video:
                                    self._safe_go_back()
                                    continue

                                similar_pin = Pin(
                                    id=str(similar_details.get("id", " ")),
                                    title=similar_details.get("title", " "),
                                    description=similar_details.get("description", " "),
                                    image_url=similar_details.get("image_url", " "),
                                    image_url_736x=similar_details.get(
                                        "image_url_736x", " "
                                    ),
                                    saves=similar_details.get("saves", 0),
                                    comments=similar_details.get("comments", 0),
                                    link=f"https://kr.pinterest.com/pin/{similar_id}/",
                                    pinner=similar_details.get("pinner", " "),
                                    source=f"similar_from_{pin_id}",
                                    is_video=is_video,
                                    video_url=video_url,
                                )
                                collected_pins[similar_id] = similar_pin
                                print(f"    已收集相似 pin {similar_id}")

                            self._safe_go_back()
                    except Exception as e:
                        if self.debug:
                            print(f"    点击相似推荐失败: {e}")
                        continue

            reading_time = random.uniform(3, 15)
            print(f"  模拟阅读 {reading_time:.1f} 秒...")
            time.sleep(reading_time)

            # ✅ 修复：仅关闭模态框，绝不强制返回搜索页，保持瀑布流滚动状态
            self._close_pin_modal()
            time.sleep(random.uniform(1, 3))

        except Exception as e:
            print(f"与 pin {pin_id} 交互时出错: {e}")
            try:
                self._close_pin_modal()
            except:
                pass

    def _extract_pins_from_page(self) -> List[Pin]:
        try:
            has_login_wall = self.page.evaluate("""
                () => {
                    const loginModal = document.querySelector('[data-test-id="login-modal"]');
                    const signupButton = document.querySelector('[data-test-id="signup-button"]');
                    const loginButton = document.querySelector('[data-test-id="login-button"]');
                    return !!(loginModal || signupButton || loginButton);
                }
            """)

            if has_login_wall:
                print("[DEBUG] 检测到登录墙，尝试关闭...")

            if self.debug:
                try:
                    self.page.screenshot(path="debug_screenshot.png", timeout=10000)
                    print("[DEBUG] 已保存调试截图: debug_screenshot.png")
                except Exception as screenshot_error:
                    print(f"[DEBUG] 截图失败: {screenshot_error}")
                    print(f"[DEBUG] 当前URL: {self.page.url}")
                    print(f"[DEBUG] 页面标题: {self.page.title()}")

            pins = self._extract_from_json()

            if not pins:
                if self.debug:
                    print("[DEBUG] JSON 提取失败，尝试从 DOM 提取...")
                pins = self._extract_from_dom()

            return pins

        except Exception as e:
            print(f"[DEBUG] 提取数据时出错: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _close_pin_modal(self):
        """关闭 pin 详情模态框"""
        if not self._is_page_alive():
            return

        try:
            # 尝试按 ESC 键关闭模态框
            self.page.keyboard.press("Escape")
            time.sleep(random.uniform(0.5, 1))

            if not self._is_page_alive():
                return

            # 如果 ESC 无效，尝试点击关闭按钮
            close_btn = self.page.query_selector('[data-test-id="close-button"], [data-test-id="pin-close-button"]')
            if close_btn:
                close_btn.click()
                time.sleep(random.uniform(0.5, 1))
        except Exception as e:
            if self.debug:
                print(f"关闭模态框失败: {e}")

    def _navigate_back_to_search(self, keyword: str):
        """安全返回搜索页"""
        if not self._is_page_alive():
            self.logger.warning("[_navigate_back_to_search] 页面已失效，无法返回")
            return

        try:
            current_url = self.page.url
        except Exception:
            self.logger.warning("[_navigate_back_to_search] 无法获取当前URL")
            return

        if "/search/" in current_url:
            return

        print(f"  返回搜索结果页...")
        try:
            # 优先尝试关闭模态框
            self._close_pin_modal()
            time.sleep(random.uniform(1.5, 2.5))

            # 如果关闭弹窗后 URL 还没变回 search，使用浏览器后退
            if not self._is_page_alive():
                return

            if "/search/" not in self.page.url:
                print("  弹窗关闭无效，尝试使用浏览器后退...")
                self._safe_go_back()

        except Exception as e:
            print(f"  返回搜索页出错: {e}")
            time.sleep(2)

    def _extract_from_json(self) -> List[Pin]:
        """从 __PWS_DATA__ JSON 提取 Pin 数据"""
        try:
            # 执行 JavaScript 提取 __PWS_DATA__
            pws_data = self.page.evaluate("""
                () => {
                    const script = document.getElementById('__PWS_DATA__');
                    return script ? script.textContent : null;
                }
            """)

            if not pws_data:
                return []

            data = json.loads(pws_data)

            # 调试：保存JSON
            if self.debug:
                with open("debug_data.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print("已保存调试JSON: debug_data.json")

            # 检查是否被识别为机器人
            is_bad_bot = data.get("context", {}).get("is_bad_bot", False)
            if is_bad_bot:
                print("警告: Pinterest 检测到机器人访问")

            return self._parse_pins_data(data)

        except json.JSONDecodeError as e:
            if self.debug:
                print(f"JSON 解析错误: {e}")
            return []
        except Exception as e:
            if self.debug:
                print(f"JSON 提取错误: {e}")
            return []

    def _extract_from_dom(self) -> List[Pin]:
        """从 DOM 元素直接提取 Pin 数据（基本信息）"""
        try:
            # 使用 JavaScript 从页面提取 Pin 链接
            pins_data = self.page.evaluate("""
                () => {
                    const pins = [];
                    const processedIds = new Set();

                    // 查找所有 pin 链接
                    const pinLinks = document.querySelectorAll('a[href*="/pin/"]');

                    pinLinks.forEach(link => {
                        try {
                            // 从 href 中提取 pin ID
                            const match = link.href.match(/\\/pin\\/([0-9]+)/);
                            if (!match) return;

                            const pinId = match[1];
                            if (processedIds.has(pinId)) return;
                            processedIds.add(pinId);

                            // 获取图片 URL - 从父元素中查找
                            let container = link;
                            for (let i = 0; i < 5; i++) {
                                container = container.parentElement;
                                if (!container) return;
                            }

                            const img = container.querySelector('img[src*="pinimg"]');
                            const imageUrl = img ? img.src : '';
                            const title = img?.alt || '';

                            // 获取 saves 从文本（合并 likes/reactions 到 saves）
                            let saves = 0, comments = 0;
                            if (container.textContent) {
                                const text = container.textContent;
                                const saveMatch = text.match(/(\d+(?:,\d+)*)\s*(?:saves?|saved|保存|收藏)/i);
                                if (saveMatch) saves = parseInt(saveMatch[1].replace(/,/g, '')) || 0;
                                if (!saves) {
                                    const likeMatch = text.match(/(\d+(?:,\d+)*)\s*(?:likes?|liked|reactions?|赞)/i);
                                    if (likeMatch) saves = parseInt(likeMatch[1].replace(/,/g, '')) || 0;
                                }
                                const commentMatch = text.match(/(\d+(?:,\d+)*)\s*(?:comments?|评论)/i);
                                if (commentMatch) comments = parseInt(commentMatch[1].replace(/,/g, '')) || 0;
                            }

                            if (pinId && imageUrl) {
                                pins.push({
                                    id: pinId,
                                    title: title,
                                    description: '',
                                    image_url: imageUrl.replace('/236x/', '/originals/').replace('/564x/', '/originals/'),
                                    image_url_736x: imageUrl.replace('/236x/', '/736x/').replace('/564x/', '/736x/'),
                                    saves: saves,
                                    comments: comments,
                                    link: link.href,
                                    pinner: ''
                                });
                            }
                        } catch (e) {
                            // 跳过解析失败的元素
                        }
                    });

                    return pins;
                }
            """)

            if self.debug:
                print(f"从 DOM 提取到 {len(pins_data)} 个 Pin")

            pins = []
            for pin_data in pins_data:
                try:
                    pin = Pin(
                        id=str(pin_data["id"]),
                        title=pin_data.get("title", ""),
                        description=pin_data.get("description", ""),
                        image_url=pin_data.get("image_url", ""),
                        image_url_736x=pin_data.get("image_url_736x", ""),
                        saves=pin_data.get("saves", 0),
                        comments=pin_data.get("comments", 0),
                        link=pin_data.get("link", ""),
                        pinner=pin_data.get("pinner", ""),
                        is_video=pin_data.get("is_video", False),
                        video_url=pin_data.get("video_url", ""),
                    )
                    pins.append(pin)
                except Exception as e:
                    if self.debug:
                        print(f"解析 Pin 时出错: {e}")
                    continue

            return pins

        except Exception as e:
            if self.debug:
                print(f"DOM 提取错误: {e}")
            return []

    def fetch_pin_details(self, pin_id: str) -> dict:
        """访问 pin 详情页获取完整数据（saves, comments 等）"""
        try:
            url = f"https://kr.pinterest.com/pin/{pin_id}/"
            if self.debug:
                print(f"  正在获取详情: {url}")

            # 在新标签页打开
            new_page = self.context.new_page()
            new_page.set_default_timeout(30000)

            try:
                new_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(random.uniform(3, 5))

                pin_data = new_page.evaluate("""
                    () => {
                        function fromPWS() {
                            const script = document.getElementById('__PWS_DATA__');
                            if (!script) return null;
                            try {
                                const data = JSON.parse(script.textContent);
                                const pins = (data.props || {}).initialReduxState || {};
                                const pinMap = pins.pins || {};
                                for (const [id, pin] of Object.entries(pinMap)) {
                                    const aggData = pin.aggregated_pin_data || {};
                                    const stats = aggData.aggregated_stats || {};
                                    return {
                                        title: pin.grid_title || pin.title || '',
                                        description: pin.description || '',
                                        saves: parseInt(stats.saves) || 0,
                                        comments: parseInt(aggData.comment_count) || 0,
                                        pinner: (pin.pinner || {}).username || ''
                                    };
                                }
                                return null;
                            } catch (e) { return null; }
                        }
                        function fromDOM() {
                            let saves = 0, comments = 0, title = '';
                            const allText = document.body.innerText || '';
                            let m;
                            m = allText.match(/(\\d[\\d,]*)\\s*(saves?|saved|保存|收藏|likes?|liked|reactions?|赞)/i);
                            if (m) saves = parseInt(m[1].replace(/,/g, '')) || 0;
                            if (!m) { m = allText.match(/(saves?|saved|保存|收藏|likes?|liked|reactions?|赞)\\s*(\\d[\\d,]*)/i); if (m) saves = parseInt(m[2].replace(/,/g, '')) || 0; }
                            m = allText.match(/(\\d[\\d,]*)\\s*(comments?|评论)/i);
                            if (m) comments = parseInt(m[1].replace(/,/g, '')) || 0;
                            if (!m) { m = allText.match(/(comments?|评论)\\s*(\\d[\\d,]*)/i); if (m) comments = parseInt(m[2].replace(/,/g, '')) || 0; }
                            const titleEl = document.querySelector('[data-test-id="pin-title"]') || document.querySelector('h1');
                            if (titleEl) title = titleEl.textContent.trim();
                            return (saves > 0 || comments > 0) ? { title, saves, comments, pinner: '', description: '' } : null;
                        }
                        return fromPWS() || fromDOM();
                    }
                """)

                if pin_data:
                    return pin_data

            finally:
                new_page.close()

            return {}

        except Exception as e:
            if self.debug:
                print(f"  获取详情失败: {e}")
            return {}

    def enrich_pins_with_details(
        self, pins: List[Pin], max_pins: int = 100
    ) -> List[Pin]:
        """为 pins 添加详细信息（saves, comments）"""
        enriched_pins = []
        to_fetch = pins[:max_pins]
        total = len(to_fetch)

        print(f"\n正在获取 {total} 个 Pin 的详细信息...")

        # 通知进度：开始获取详情
        if self.progress_callback:
            self.progress_callback(
                "enriching", 0, total, f"开始获取 {total} 个 Pin 的详情"
            )

        for i, pin in enumerate(to_fetch):
            if pin.link:
                details = self.fetch_pin_details(pin.id)

                if details:
                    pin.title = details.get("title", pin.title)
                    pin.description = details.get("description", pin.description)
                    pin.saves = details.get("saves", 0)
                    pin.comments = details.get("comments", 0)
                    pin.pinner = details.get("pinner", "")

                enriched_pins.append(pin)

                # 显示进度
                saves_str = f"{pin.saves:,}" if pin.saves else "0"
                comments_str = f"{pin.comments:,}" if pin.comments else "0"
                title_preview = pin.title[:30] if pin.title else "无标题"
                print(
                    f"  [{i + 1}/{total}] Saves: {saves_str} | Comments: {comments_str} | {title_preview}"
                )

                # 更新进度回调
                if self.progress_callback:
                    percentage = int((i + 1) / total * 100)
                    self.progress_callback(
                        "enriching",
                        i + 1,
                        total,
                        f"已获取 {i + 1}/{total} 个详情 - {title_preview}",
                    )

                # 随机延迟，保护账号
                wait_time = random.uniform(3, 6)
                time.sleep(wait_time)

                # 每获取 10 个，额外休息
                if (i + 1) % 10 == 0 and i < total - 1:
                    rest_time = random.uniform(15, 30)
                    print(f"  已获取 {i + 1} 个，休息 {rest_time:.1f}秒...")
                    time.sleep(rest_time)

        return enriched_pins

    def _parse_pins_data(self, data: dict) -> List[Pin]:
        """解析 JSON 数据为 Pin 对象列表"""
        pins = []

        try:
            # 检查数据结构
            props = data.get("props", {})
            if not props:
                if self.debug:
                    print("警告: 没有 props 字段")
                    # 打印顶层键
                    print(f"顶层键: {list(data.keys())}")
                return pins

            initial_state = props.get("initialReduxState", {})
            if not initial_state:
                if self.debug:
                    print("警告: 没有 initialReduxState 字段")
                    print(f"props 键: {list(props.keys())}")
                return pins

            # 方式1：从 pins 对象提取
            pins_data = initial_state.get("pins", {})

            if self.debug:
                print(f"发现 {len(pins_data)} 个 pins")
                # 打印 initialReduxState 的键
                print(f"initialReduxState 键: {list(initial_state.keys())[:10]}")

            # 方式2：从 feeds 提取（搜索结果通常在这里）
            feeds = initial_state.get("feeds", {})

            # 如果 pins 为空，尝试从 feeds 获取 pin IDs
            if not pins_data and feeds:
                for feed_key, feed_data in feeds.items():
                    if isinstance(feed_data, dict) and "items" in feed_data:
                        items = feed_data.get("items", [])
                        if self.debug:
                            print(f"Feed {feed_key}: {len(items)} items")

                        # 从 items 获取 pin 数据
                        for item in items:
                            if isinstance(item, dict):
                                pin_id = item.get("id") or item.get("pin_id")
                                if pin_id and pin_id not in pins_data:
                                    pins_data[str(pin_id)] = item

            for pin_id, pin_data in pins_data.items():
                try:
                    # 提取图片 URL
                    images = pin_data.get("images", {})
                    image_url = images.get("orig", {}).get("url", "")
                    image_url_736x = images.get("736x", {}).get("url", "")

                    # 如果没有 images，尝试其他字段
                    if not image_url and not image_url_736x:
                        # 尝试 image_spec 或其他字段
                        image_spec = pin_data.get("image_spec", {})
                        if image_spec:
                            image_url = image_spec.get("url", "")

                    # 提取 save 数和评论数
                    aggregated_data = pin_data.get("aggregated_pin_data", {})
                    aggregated_stats = aggregated_data.get("aggregated_stats", {})
                    saves = aggregated_stats.get("saves", 0)
                    comments = aggregated_data.get("comment_count", 0)

                    # 提取发布者信息
                    pinner = pin_data.get("pinner", {})
                    pinner_name = pinner.get("username", "") if pinner else ""

                    # 检测是否为视频
                    is_video = False
                    video_url = ""
                    if "videos" in pin_data and pin_data["videos"]:
                        is_video = True
                        video_data = pin_data["videos"]
                        if isinstance(video_data, dict) and "video_list" in video_data:
                            # 获取最佳质量的视频URL
                            video_list = video_data["video_list"]
                            for quality in ["V_720P", "V_480P", "V_360P"]:
                                if quality in video_list:
                                    video_url = video_list[quality].get("url", "")
                                    if video_url:
                                        break

                    pin = Pin(
                        id=str(pin_id),
                        title=pin_data.get("grid_title") or pin_data.get("title", ""),
                        description=pin_data.get("description", ""),
                        image_url=image_url,
                        image_url_736x=image_url_736x,
                        saves=saves,
                        comments=comments,
                        link=pin_data.get("link", ""),
                        pinner=pinner_name,
                        is_video=is_video,
                        video_url=video_url,
                    )
                    pins.append(pin)

                except Exception as e:
                    if self.debug:
                        print(f"解析 Pin {pin_id} 时出错: {e}")
                    continue

        except Exception as e:
            print(f"解析 pins 数据时出错: {e}")

        return pins
