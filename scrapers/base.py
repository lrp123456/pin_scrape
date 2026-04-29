"""通用爬虫基类

所有网站爬虫必须继承此基类，并实现其中的抽象方法。
"""

import sys
import time
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class BaseScraper(ABC):
    """爬虫基类

    所有网站爬虫必须继承此类并实现抽象方法。
    子类需要实现的方法：
    - _get_search_url(): 生成搜索页URL
    - _extract_pin_ids_from_search(): 从搜索页提取内容ID
    - _extract_details(): 从详情页提取数据
    - _get_similar_ids(): 获取相似内容ID
    - _get_media_type(): 判断媒体类型
    """

    # 类级别的媒体类型常量
    MEDIA_TYPE_ALL = "all"
    MEDIA_TYPE_IMAGES = "images"
    MEDIA_TYPE_VIDEO = "video"

    def __init__(
        self,
        headless: bool = True,
        debug: bool = False,
        cdp_endpoint: Optional[str] = None,
        log_file: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ):
        """初始化爬虫

        Args:
            headless: 是否无头模式
            debug: 是否调试模式
            cdp_endpoint: Chrome DevTools Protocol 端点
            log_file: 日志文件路径
            progress_callback: 进度回调函数
        """
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.log_file = log_file
        self.progress_callback = progress_callback

        # 浏览器实例（由子类初始化）
        self.browser = None
        self.context = None
        self.page = None
        self._playwright = None
        self._own_browser = False

        # 当前状态
        self._current_keyword = ""
        self.media_type = self.MEDIA_TYPE_ALL

        # 初始化日志
        self.logger = self._init_logger()

    @abstractmethod
    def _get_search_url(self, keyword: str) -> str:
        """生成搜索页URL

        Args:
            keyword: 搜索关键词

        Returns:
            搜索页完整URL
        """
        pass

    @abstractmethod
    def _extract_pin_ids_from_search(self) -> List[str]:
        """从搜索页提取内容ID列表

        Returns:
            内容ID列表
        """
        pass

    @abstractmethod
    def _extract_details(self, content_id: str) -> Optional[Dict[str, Any]]:
        """从详情页提取内容数据

        Args:
            content_id: 内容ID

        Returns:
            包含以下键的字典：
            - id: 内容ID
            - title: 标题
            - description: 描述
            - image_url: 原图URL
            - image_url_xxx: 其他尺寸图片URL
            - saves/favorites: 收藏数
            - comments: 评论数
            - pinner/author: 发布者
            - is_video: 是否视频
            - video_url: 视频URL
            - source: 来源标识
        """
        pass

    @abstractmethod
    def _get_similar_ids(self) -> List[Dict[str, str]]:
        """获取相似内容推荐列表

        Returns:
            相似内容列表，每项包含 id 和其他信息
        """
        pass

    @abstractmethod
    def _get_media_type(self, content_id: str) -> bool:
        """判断内容是否为视频

        Args:
            content_id: 内容ID

        Returns:
            True-视频，False-图片
        """
        pass

    @abstractmethod
    def _close_modal(self) -> bool:
        """关闭详情弹窗/模态框

        Returns:
            True-成功，False-失败
        """
        pass

    @abstractmethod
    def _go_back(self) -> None:
        """返回上一页（浏览器后退）"""
        pass

    @abstractmethod
    def _scroll_page(self) -> bool:
        """滚动页面加载更多内容

        Returns:
            True-成功滚动，False-无法滚动
        """
        pass

    def _init_logger(self):
        """初始化日志记录器"""
        import logging

        logger = logging.getLogger(f"{self.__class__.__name__}")
        logger.setLevel(logging.DEBUG if self.debug else logging.INFO)

        if self.log_file:
            fh = logging.FileHandler(self.log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)

        return logger

    def search(
        self,
        keyword: str,
        max_count: int = 100,
        min_saves: int = 0,
        climb_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """搜索并收集内容

        Args:
            keyword: 搜索关键词
            max_count: 最大收集数量
            min_saves: 最小收藏数筛选
            climb_mode: 爬坡模式（不检查min_saves）

        Returns:
            收集到的内容列表
        """
        self._current_keyword = keyword
        self._apply_stealth_mode()

        # 访问搜索页
        search_url = self._get_search_url(keyword)
        self.logger.info(f"访问搜索页: {search_url}")
        self.page.goto(search_url)
        time.sleep(random.uniform(5, 8))

        # 初始滚动
        for _ in range(random.randint(0, 5)):
            self._scroll_page()
            time.sleep(random.uniform(0.5, 1))

        # 主搜索循环
        collected = []
        visited_ids = set()
        search_page_ids = self._extract_pin_ids_from_search()

        for content_id in search_page_ids:
            if len(collected) >= max_count:
                break
            if content_id in visited_ids:
                continue

            visited_ids.add(content_id)
            details = self._extract_details(content_id)

            if not details:
                continue

            saves = details.get("saves", 0) or 0

            # 检查是否满足筛选条件
            if not climb_mode and saves < min_saves:
                continue

            collected.append(details)

            if self.progress_callback:
                self.progress_callback(
                    "collecting",
                    len(collected),
                    max_count,
                    f"已收集 {len(collected)}/{max_count}",
                )

        return collected

    def _apply_stealth_mode(self):
        """应用反检测模式（子类可重写）"""
        pass

    def start(self):
        """启动浏览器（子类需要重写或调用基类实现）"""
        raise NotImplementedError("子类必须实现 start() 方法")

    def close(self):
        """关闭浏览器"""
        if self._own_browser and self.browser:
            self.browser.close()
        if self._playwright:
            self._playwright.stop()

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False


class BaseOutput:
    """输出处理基类"""

    @staticmethod
    def save_json(data: List[Dict], filepath: str, query: str):
        """保存数据到JSON文件"""
        import json
        from datetime import datetime

        output = {
            "query": query,
            "total": len(data),
            "timestamp": datetime.now().isoformat(),
            "items": data,
        }

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    @staticmethod
    def save_csv(data: List[Dict], filepath: str):
        """保存数据到CSV文件"""
        import csv

        if not data:
            return

        keys = data[0].keys()
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
