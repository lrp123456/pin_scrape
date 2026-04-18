"""图片下载器"""

import asyncio
import aiohttp
from pathlib import Path
from typing import List
import time
import random
from datetime import datetime

from shared.models import Pin


class ImageDownloader:
    """图片下载器"""

    def __init__(
        self, output_dir: str, query: str = "", use_folder_structure: bool = False
    ):
        self.output_dir = Path(output_dir)
        self.query = query
        self.use_folder_structure = use_folder_structure

        if use_folder_structure and query:
            # 使用文件夹结构: 查询词_时间/save数_comments数_id.mp4
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.images_dir = self.output_dir / f"{query}_{timestamp}"
        else:
            # 默认结构: output/images/
            self.images_dir = self.output_dir / "images"

        self.images_dir.mkdir(parents=True, exist_ok=True)

    def filter_and_download(
        self,
        pins: List[Pin],
        min_saves: int = 0,
        min_likes: int = 0,
        min_comments: int = 0,
    ) -> List[Pin]:
        """
        筛选并下载符合条件的图片

        Args:
            pins: Pin 列表
            min_saves: save 数最小值
            min_likes: 点赞数最小值
            min_comments: 评论数最小值

        Returns:
            符合条件并下载成功的 Pin 列表
        """
        # 筛选符合条件的 Pin
        filtered_pins = [
            pin
            for pin in pins
            if pin.meets_criteria(min_saves, min_likes, min_comments)
        ]

        print(f"筛选结果: {len(filtered_pins)}/{len(pins)} 个 Pin 符合条件")

        if not filtered_pins:
            print("没有符合条件的 Pin，跳过下载")
            return []

        # 下载图片（串行下载，添加延迟保护账号）
        downloaded_pins = asyncio.run(self._download_all_images(filtered_pins))

        print(f"下载完成: {len(downloaded_pins)}/{len(filtered_pins)} 张图片")
        return downloaded_pins

    async def _download_all_images(self, pins: List[Pin]) -> List[Pin]:
        """串行下载所有图片（添加延迟保护）"""
        downloaded_pins = []

        async with aiohttp.ClientSession() as session:
            for i, pin in enumerate(pins):
                if pin.image_url or pin.image_url_736x:
                    success = await self._download_image(session, pin)
                    if success:
                        downloaded_pins.append(pin)

                    # 每下载一张图片，随机等待 2-5 秒
                    if i < len(pins) - 1:  # 最后一张不需要等待
                        wait_time = random.uniform(2, 5)
                        print(f"等待 {wait_time:.1f}秒 后继续下载...")
                        await asyncio.sleep(wait_time)

                    # 每下载 10 张图片，额外休息
                    if (i + 1) % 10 == 0 and i < len(pins) - 1:
                        rest_time = random.uniform(10, 20)
                        print(f"已下载 {i + 1} 张，休息 {rest_time:.1f}秒...")
                        await asyncio.sleep(rest_time)

        return downloaded_pins

    async def _download_image(self, session: aiohttp.ClientSession, pin: Pin) -> bool:
        """
        下载单个图片

        Args:
            session: aiohttp 会话
            pin: Pin 对象

        Returns:
            是否下载成功
        """
        # 优先使用原图，如果没有则使用中等尺寸
        url = pin.image_url or pin.image_url_736x
        if not url:
            return False

        # 确定文件扩展名
        if pin.is_video:
            ext = ".mp4"
        else:
            ext = ".jpg"
            if ".png" in url.lower():
                ext = ".png"
            elif ".gif" in url.lower():
                ext = ".gif"

        # 文件名格式
        if self.use_folder_structure and self.query:
            # 文件夹结构内使用: save数_comments数_id.mp4
            filename = f"{pin.saves}_{pin.comments}_{pin.id}{ext}"
        else:
            # 查询词_save数_comments数_视频id.mp4
            query_prefix = f"{self.query}_" if self.query else ""
            filename = f"{query_prefix}{pin.saves}_{pin.comments}_{pin.id}{ext}"

        filepath = self.images_dir / filename

        # 如果文件已存在，跳过下载
        if filepath.exists():
            print(f"图片已存在: {filename}")
            return True

        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    content = await response.read()
                    filepath.write_bytes(content)
                    print(f"下载成功: {filename}")
                    return True
                else:
                    print(f"下载失败 (HTTP {response.status}): {filename}")
                    return False
        except asyncio.TimeoutError:
            print(f"下载超时: {filename}")
            return False
        except Exception as e:
            print(f"下载出错 {filename}: {e}")
            return False
