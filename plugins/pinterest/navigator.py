"""Pinterest 页面导航与交互

职责:
  - 页面滚动（普通滚动、PgDn滚动）
  - 模态框关闭
  - 页面导航（前进/后退/搜索页）
  - Pin 点击
  - 可见元素获取
"""

import logging
import random
import time
from typing import List, Optional, Tuple

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


class PinterestNavigator:
    """Pinterest 页面导航器"""

    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug

    def scroll_page(self) -> bool:
        """向下滚动一屏"""
        try:
            self.page.mouse.wheel(0, random.randint(600, 1000))
            time.sleep(random.uniform(0.3, 0.8))
            return True
        except Exception:
            return False

    def scroll_with_pgdn(self) -> bool:
        """使用 PgDn 键滚动"""
        try:
            self.page.keyboard.press("PageDown")
            time.sleep(random.uniform(0.5, 1.0))
            return True
        except Exception:
            return False

    def close_pin_modal(self) -> bool:
        """关闭 Pin 详情模态框"""
        try:
            close_btn = self.page.query_selector('[data-test-id="close-button"]')
            if close_btn:
                close_btn.click()
                time.sleep(0.5)
                return True

            self.page.keyboard.press("Escape")
            time.sleep(0.5)
            return True
        except Exception:
            try:
                self.page.keyboard.press("Escape")
                time.sleep(0.3)
                return True
            except Exception:
                return False

    def navigate_to_search(self, keyword: str, base_url: str = "https://kr.pinterest.com/search/pins/") -> bool:
        """导航到搜索页

        Args:
            keyword: 搜索关键词
            base_url: 搜索基础URL

        Returns:
            是否成功导航
        """
        try:
            encoded = keyword.replace(" ", "+")
            url = f"{base_url}?q={encoded}"
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(2, 4))
            return True
        except Exception as e:
            logger.error(f"导航到搜索页失败: {e}")
            return False

    def go_back(self, fallback_url: Optional[str] = None) -> bool:
        """返回上一页

        Args:
            fallback_url: 后退失败时的回退URL

        Returns:
            是否成功后退
        """
        try:
            self.page.go_back(wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(1, 2))
            return True
        except Exception:
            if fallback_url:
                try:
                    self.page.goto(fallback_url, wait_until="domcontentloaded", timeout=15000)
                    return True
                except Exception:
                    return False
            return False

    def ensure_on_search_page(self, keyword: str, base_url: str = "https://kr.pinterest.com/search/pins/") -> bool:
        """确保当前在搜索页

        如果不在搜索页，则导航到搜索页。
        """
        current_url = self.page.url
        if "/search/pins/" in current_url and f"q={keyword.replace(' ', '+')}" in current_url:
            return True
        return self.navigate_to_search(keyword, base_url)

    def click_pin(self, pin_element) -> bool:
        """点击 Pin 元素

        Args:
            pin_element: Playwright ElementHandle

        Returns:
            是否成功点击
        """
        try:
            pin_element.click()
            time.sleep(random.uniform(1, 2))
            return True
        except Exception:
            return False

    def get_visible_pin_elements(self, media_type: str = "all") -> List:
        """获取当前可见的 Pin 元素

        Args:
            media_type: 媒体类型过滤 ("all", "images", "video")

        Returns:
            Pin 元素列表
        """
        try:
            if media_type == "images":
                selector = 'div[data-test-id="pin"] a:not([href*="/pin/"][href*="/videos/"])'
            elif media_type == "video":
                selector = 'div[data-test-id="pin"] a[href*="/videos/"]'
            else:
                selector = 'div[data-test-id="pin"] a'

            elements = self.page.query_selector_all(selector)
            return elements
        except Exception:
            return []

    def is_page_alive(self) -> bool:
        """检查页面是否可用"""
        try:
            _ = self.page.url
            return not self.page.is_closed()
        except Exception:
            return False

    def wait_for_content(self, timeout: int = 10000) -> bool:
        """等待页面内容加载"""
        try:
            self.page.wait_for_selector('[data-test-id="pin"]', timeout=timeout)
            return True
        except Exception:
            return False

    def get_current_pin_id_from_url(self) -> Optional[str]:
        """从当前URL提取 Pin ID"""
        try:
            url = self.page.url
            if "/pin/" in url:
                parts = url.split("/pin/")
                if len(parts) > 1:
                    pin_id = parts[1].split("/")[0].split("?")[0]
                    if pin_id.isdigit():
                        return pin_id
        except Exception:
            pass
        return None
