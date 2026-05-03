"""Pinterest 认证与 Cookie 管理

职责:
  - 检测登录状态
  - 启动登录流程
  - Cookie 注入与保存
  - Cookie 数据库交互
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.sync_api import BrowserContext, Page

logger = logging.getLogger(__name__)

COOKIES_DIR = Path(__file__).parent.parent.parent / "cookiesFile"


class PinterestAuth:
    """Pinterest 认证管理器"""

    def __init__(self, page: Page, context: BrowserContext,
                 worker_id: str = "worker-0", debug: bool = False):
        self.page = page
        self.context = context
        self.worker_id = worker_id
        self.debug = debug
        self._cookie_manager = None
        self._cookie_account_id = None
        self._init_cookie_manager()

    def _init_cookie_manager(self) -> None:
        try:
            from shared.cookie_manager import CookieManager
            db_path = Path(__file__).parent.parent.parent / "db" / "cookies.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._cookie_manager = CookieManager(str(db_path))
        except ImportError:
            logger.warning("CookieManager 不可用")

    def check_login_required(self) -> bool:
        """检查是否需要登录

        Returns:
            True 表示需要登录
        """
        try:
            current_url = self.page.url
            if "/login" in current_url:
                return True

            has_session = False
            cookies = self.context.cookies()
            for c in cookies:
                if c.get("name") == "_pinterest_sess" and c.get("value"):
                    has_session = True
                    break

            if not has_session:
                return True

            self.page.goto("https://kr.pinterest.com/", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)

            if "/login" in self.page.url:
                return True

            return False
        except Exception as e:
            logger.warning(f"登录检测异常: {e}")
            return True

    def inject_cookies(self, storage_state: Dict) -> None:
        """注入 Cookie 到浏览器上下文

        Args:
            storage_state: Playwright storage_state 格式的 Cookie 数据
        """
        if not storage_state:
            return

        cookies = storage_state.get("cookies", [])
        if not cookies:
            return

        try:
            formatted = []
            for c in cookies:
                fc = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".pinterest.com"),
                    "path": c.get("path", "/"),
                }
                if c.get("expires") and c["expires"] > 0:
                    fc["expires"] = c["expires"]
                if c.get("httpOnly"):
                    fc["httpOnly"] = True
                if c.get("secure"):
                    fc["secure"] = True
                if c.get("sameSite"):
                    fc["sameSite"] = c["sameSite"]
                formatted.append(fc)

            self.context.add_cookies(formatted)
            logger.info(f"[{self.worker_id}] 已注入 {len(formatted)} 个Cookie")
        except Exception as e:
            logger.error(f"Cookie注入失败: {e}")

    def save_cookie_state(self) -> Optional[Dict]:
        """保存当前浏览器 Cookie 状态

        Returns:
            storage_state 字典，失败返回 None
        """
        try:
            state = self.context.storage_state()
            cookies = state.get("cookies", [])
            has_session = any(c.get("name") == "_pinterest_sess" for c in cookies)

            if not has_session:
                logger.warning(f"[{self.worker_id}] 无 _pinterest_sess Cookie，可能未登录")
                return None

            if self._cookie_manager and self._cookie_account_id:
                self._cookie_manager.update_cookies(self._cookie_account_id, state)
                logger.info(f"[{self.worker_id}] Cookie 已保存到数据库 (账号 #{self._cookie_account_id})")

            return state
        except Exception as e:
            logger.error(f"保存Cookie失败: {e}")
            return None

    def load_cookie_from_db(self, account_id: Optional[int] = None) -> Optional[Dict]:
        """从数据库加载 Cookie

        Args:
            account_id: 指定账号ID，None 则自动分配

        Returns:
            storage_state 字典，失败返回 None
        """
        if not self._cookie_manager:
            return None

        try:
            if account_id:
                account = self._cookie_manager.get_account(account_id)
            else:
                account = self._cookie_manager.allocate_account(self.worker_id)

            if not account:
                logger.info(f"[{self.worker_id}] 无可用Cookie账号")
                return None

            self._cookie_account_id = account["id"]
            storage_state = account.get("storage_state")
            if storage_state and isinstance(storage_state, str):
                storage_state = json.loads(storage_state)

            logger.info(f"[{self.worker_id}] 已加载账号 #{account['id']} Cookie")
            return storage_state
        except Exception as e:
            logger.error(f"加载Cookie失败: {e}")
            return None

    def release_cookie(self) -> None:
        """释放当前分配的 Cookie 账号"""
        if self._cookie_manager and self._cookie_account_id:
            self._cookie_manager.release_account(self._cookie_account_id, self.worker_id)
            self._cookie_account_id = None

    def launch_login_browser(self) -> None:
        """启动可见浏览器等待用户手动登录"""
        from playwright.sync_api import sync_playwright

        logger.info(f"[{self.worker_id}] 启动登录浏览器，等待手动登录...")

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--lang=zh-CN"],
                slow_mo=200,
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )

            existing_state = self.load_cookie_from_db()
            if existing_state:
                cookies = existing_state.get("cookies", [])
                if cookies:
                    formatted = []
                    for c in cookies:
                        fc = {"name": c["name"], "value": c["value"],
                              "domain": c.get("domain", ".pinterest.com"),
                              "path": c.get("path", "/")}
                        if c.get("expires", 0) > 0:
                            fc["expires"] = c["expires"]
                        if c.get("httpOnly"):
                            fc["httpOnly"] = True
                        if c.get("secure"):
                            fc["secure"] = True
                        formatted.append(fc)
                    context.add_cookies(formatted)

            page = context.new_page()
            page.goto("https://kr.pinterest.com/login/", wait_until="domcontentloaded")

            input(f"\n[{self.worker_id}] 请在浏览器中登录 Pinterest，完成后按 Enter 确认...")

            state = context.storage_state()
            has_session = any(c.get("name") == "_pinterest_sess" for c in state.get("cookies", []))

            if has_session:
                if self._cookie_manager and self._cookie_account_id:
                    self._cookie_manager.update_cookies(self._cookie_account_id, state)
                    logger.info(f"[{self.worker_id}] 登录Cookie已保存到数据库")
                self.inject_cookies(state)
                logger.info(f"[{self.worker_id}] Cookie已注入到主浏览器")
            else:
                logger.warning(f"[{self.worker_id}] 未检测到登录Cookie")

            browser.close()
        finally:
            pw.stop()
