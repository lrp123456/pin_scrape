"""Pinterest Pin 收集与批量处理

职责:
  - 滚动收集 Pin
  - 爬坡探索（从高质量 Pin 发现更多）
  - 批量收集池与 AI 筛选
  - 结果输出
"""

import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from playwright.sync_api import Page

from shared.models import Pin
from plugins.pinterest.navigator import PinterestNavigator
from plugins.pinterest.extractor import PinterestExtractor

logger = logging.getLogger(__name__)

BATCH_COLLECT_SIZE = 5


class PinterestCollector:
    """Pinterest Pin 收集器"""

    def __init__(self, page: Page, navigator: PinterestNavigator,
                 extractor: PinterestExtractor, debug: bool = False,
                 worker_id: str = "worker-0"):
        self.page = page
        self.nav = navigator
        self.ext = extractor
        self.debug = debug
        self.worker_id = worker_id
        self._ai_filter = None
        self._coordinator = None
        self._async_ai = None
        self._init_ai()

    def _init_ai(self) -> None:
        try:
            from shared.ai_filter_manager import AIFilterManager
            from shared.ollama_config import get_ollama_config
            self._ai_filter = AIFilterManager()
        except ImportError:
            pass

        try:
            from shared.coordinator import ScrapeCoordinator
            from shared.async_ai_worker import AsyncAIWorker
            self._coordinator = ScrapeCoordinator()
            self._async_ai = AsyncAIWorker()
        except ImportError:
            pass

    def scroll_and_collect(self, max_pins: int, keyword: str,
                           progress_callback: Optional[Callable] = None) -> List[Pin]:
        """滚动搜索页收集 Pin

        Args:
            max_pins: 最大收集数量
            keyword: 搜索关键词
            progress_callback: 进度回调

        Returns:
            收集到的 Pin 列表
        """
        collected: List[Pin] = []
        seen_ids: Set[str] = set()
        no_new_count = 0
        max_no_new = 5

        while len(collected) < max_pins and no_new_count < max_no_new:
            new_pins = self.ext.extract_pins_from_dom()
            added = 0
            for pin in new_pins:
                if pin.id and pin.id not in seen_ids:
                    seen_ids.add(pin.id)
                    collected.append(pin)
                    added += 1

            if added == 0:
                no_new_count += 1
            else:
                no_new_count = 0

            if progress_callback:
                progress_callback("collecting", len(collected), max_pins,
                                  f"[{self.worker_id}] 已发现 {len(collected)} 个Pin")

            self.nav.scroll_page()
            time.sleep(random.uniform(0.5, 1.5))

        logger.info(f"[{self.worker_id}] 搜索页收集完成: {len(collected)} 个Pin")
        return collected

    def explore_similar_pins(self, qualified_pins: List[Pin],
                             max_explore: int = 5,
                             progress_callback: Optional[Callable] = None) -> List[Pin]:
        """从高质量 Pin 探索相似内容（爬坡模式）

        Args:
            qualified_pins: 已确认的高质量 Pin 列表
            max_explore: 最大探索数量
            progress_callback: 进度回调

        Returns:
            新发现的高质量 Pin 列表
        """
        discovered: List[Pin] = []
        explored_ids: Set[str] = {p.id for p in qualified_pins}

        for i, pin in enumerate(qualified_pins[:max_explore]):
            if progress_callback:
                progress_callback("exploring", i, min(len(qualified_pins), max_explore),
                                  f"[{self.worker_id}] 探索相似 #{i+1}")

            similar = self._explore_one_pin(pin, explored_ids)
            discovered.extend(similar)
            explored_ids.update(s.id for s in similar)

        logger.info(f"[{self.worker_id}] 爬坡探索完成: 发现 {len(discovered)} 个新Pin")
        return discovered

    def _explore_one_pin(self, pin: Pin, explored_ids: Set[str]) -> List[Pin]:
        """探索单个 Pin 的相似内容"""
        discovered = []
        try:
            self.nav.navigate_to_search(pin.title or f"pin {pin.id}")
            time.sleep(random.uniform(2, 4))

            new_pins = self.ext.extract_pins_from_dom()
            for p in new_pins:
                if p.id and p.id not in explored_ids:
                    discovered.append(p)
                    explored_ids.add(p.id)
                    if len(discovered) >= 10:
                        break
        except Exception as e:
            logger.error(f"探索Pin {pin.id} 失败: {e}")
        return discovered

    def apply_ai_filter(self, pin: Pin, keyword: str) -> bool:
        """对 Pin 应用 AI 质量筛选

        Args:
            pin: 待筛选的 Pin
            keyword: 搜索关键词

        Returns:
            True 表示通过筛选
        """
        if not self._ai_filter:
            return True

        try:
            if self._coordinator:
                cached = self._coordinator.check_cache(pin.id)
                if cached is not None:
                    return cached

            result = self._ai_filter.evaluate(
                image_url=pin.image_url,
                keyword=keyword,
                pin_id=pin.id,
            )

            if self._coordinator:
                self._coordinator.save_cache(pin.id, result)

            return result
        except Exception as e:
            logger.error(f"AI筛选失败 [{pin.id}]: {e}")
            return True

    def batch_filter(self, pins: List[Pin], keyword: str,
                     progress_callback: Optional[Callable] = None) -> List[Pin]:
        """批量 AI 筛选

        Args:
            pins: 待筛选的 Pin 列表
            keyword: 搜索关键词
            progress_callback: 进度回调

        Returns:
            通过筛选的 Pin 列表
        """
        qualified = []
        for i, pin in enumerate(pins):
            if progress_callback:
                progress_callback("filtering", i, len(pins),
                                  f"[{self.worker_id}] AI筛选 {i+1}/{len(pins)}")

            if self.apply_ai_filter(pin, keyword):
                qualified.append(pin)

        logger.info(f"[{self.worker_id}] AI筛选: {len(qualified)}/{len(pins)} 通过")
        return qualified
