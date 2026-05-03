"""Pinterest 数据提取

职责:
  - 从搜索页 DOM 提取 Pin 列表
  - 从模态框提取 Pin 详情
  - 从 JSON API 响应提取数据
  - 相似 Pin 发现
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from shared.models import Pin

logger = logging.getLogger(__name__)


class PinterestExtractor:
    """Pinterest 数据提取器"""

    def __init__(self, page: Page, debug: bool = False):
        self.page = page
        self.debug = debug

    def extract_pins_from_dom(self) -> List[Pin]:
        """从搜索页 DOM 提取 Pin 列表"""
        pins = []
        try:
            pin_elements = self.page.query_selector_all('div[data-test-id="pin"]')
            for elem in pin_elements:
                try:
                    pin = self._extract_single_pin_from_element(elem)
                    if pin and pin.id:
                        pins.append(pin)
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"DOM 提取失败: {e}")
        return pins

    def _extract_single_pin_from_element(self, elem) -> Optional[Pin]:
        """从单个 Pin DOM 元素提取数据"""
        try:
            link = elem.query_selector("a")
            if not link:
                return None

            href = link.get_attribute("href") or ""
            pin_id = ""
            if "/pin/" in href:
                parts = href.split("/pin/")
                if len(parts) > 1:
                    pin_id = parts[1].split("/")[0].split("?")[0]

            if not pin_id or not pin_id.isdigit():
                return None

            img = elem.query_selector("img")
            image_url = ""
            title = ""
            if img:
                image_url = img.get_attribute("src") or ""
                title = img.get_attribute("alt") or ""

            return Pin(
                id=pin_id,
                title=title[:200] if title else "",
                image_url=image_url,
                saves=0,
                is_video="/videos/" in href,
            )
        except Exception:
            return None

    def extract_pin_details_from_modal(self) -> Dict[str, Any]:
        """从模态框提取 Pin 详情"""
        details = {}
        try:
            details["id"] = self._get_pin_id_from_modal()
            details["title"] = self._get_title_from_modal()
            details["description"] = self._get_description_from_modal()
            details["image_url"] = self._get_image_from_modal()
            details["saves"] = self._get_saves_from_modal()
            details["is_video"] = self._check_is_video_modal()
            details["pinner"] = self._get_pinner_from_modal()
        except Exception as e:
            logger.error(f"模态框提取失败: {e}")
        return details

    def _get_pin_id_from_modal(self) -> str:
        try:
            url = self.page.url
            if "/pin/" in url:
                parts = url.split("/pin/")
                if len(parts) > 1:
                    return parts[1].split("/")[0].split("?")[0]
        except Exception:
            pass
        return ""

    def _get_title_from_modal(self) -> str:
        try:
            title_el = self.page.query_selector('h1, [data-test-id="pin-title"]')
            if title_el:
                return title_el.inner_text().strip()[:200]
        except Exception:
            pass
        return ""

    def _get_description_from_modal(self) -> str:
        try:
            desc_el = self.page.query_selector('[data-test-id="pin-description"], .pin-description')
            if desc_el:
                return desc_el.inner_text().strip()[:500]
        except Exception:
            pass
        return ""

    def _get_image_from_modal(self) -> str:
        try:
            img = self.page.query_selector('div[data-test-id="pin-image"] img, .pin-image img')
            if img:
                src = img.get_attribute("src") or ""
                if src.startswith("http"):
                    return src
        except Exception:
            pass
        return ""

    def _get_saves_from_modal(self) -> int:
        try:
            save_el = self.page.query_selector('[data-test-id="pin-save-button"], .save-count')
            if save_el:
                text = save_el.inner_text().strip()
                match = re.search(r'[\d,]+', text)
                if match:
                    return int(match.group().replace(",", ""))
        except Exception:
            pass
        return 0

    def _check_is_video_modal(self) -> bool:
        try:
            video = self.page.query_selector('video, [data-test-id="video-player"]')
            return video is not None
        except Exception:
            return False

    def _get_pinner_from_modal(self) -> str:
        try:
            pinner_el = self.page.query_selector('[data-test-id="pinner-name"], .pinner-name a')
            if pinner_el:
                return pinner_el.inner_text().strip()
        except Exception:
            pass
        return ""

    def find_similar_pins_in_modal(self) -> List[Dict[str, str]]:
        """从模态框中查找相似 Pin"""
        similar = []
        try:
            more_like = self.page.query_selector_all(
                '[data-test-id="more-ideas"] a, [data-test-id="related-pins"] a'
            )
            for link in more_like[:20]:
                href = link.get_attribute("href") or ""
                if "/pin/" in href:
                    parts = href.split("/pin/")
                    if len(parts) > 1:
                        pin_id = parts[1].split("/")[0].split("?")[0]
                        if pin_id.isdigit():
                            similar.append({"id": pin_id, "href": href})
        except Exception as e:
            logger.error(f"查找相似Pin失败: {e}")
        return similar

    def extract_from_json_response(self, data: Dict) -> List[Pin]:
        """从 Pinterest API JSON 响应提取 Pin"""
        pins = []
        try:
            pin_data_list = self._parse_pins_data(data)
            for pd in pin_data_list:
                pin = Pin(
                    id=str(pd.get("id", "")),
                    title=pd.get("title", "")[:200],
                    description=pd.get("description", "")[:500],
                    image_url=pd.get("images", {}).get("orig", {}).get("url", ""),
                    saves=pd.get("saves", 0),
                    is_video=pd.get("is_video", False),
                    pinner=pd.get("pinner", {}).get("username", ""),
                )
                if pin.id:
                    pins.append(pin)
        except Exception as e:
            logger.error(f"JSON 提取失败: {e}")
        return pins

    def _parse_pins_data(self, data: Dict) -> List[Dict]:
        """解析 Pinterest API 返回的 Pin 数据"""
        results = []
        try:
            if "resource_response" in data:
                data = data["resource_response"]
            if "data" in data:
                items = data["data"]
                if isinstance(items, list):
                    results = items
                elif isinstance(items, dict) and "results" in items:
                    results = items["results"]
        except Exception:
            pass
        return results
