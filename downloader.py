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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.images_dir = self.output_dir / f"{query}_{timestamp}"
        else:
            self.images_dir = self.output_dir / "images"

        self.images_dir.mkdir(parents=True, exist_ok=True)

        # 加载代理配置（同时检查两个配置文件路径）
        self.proxy_url = None

        # 尝试从 shared/config_manager 加载
        try:
            from shared.config_manager import load_config as load_shared_config

            config = load_shared_config()
            if config.get("proxy_enabled", False):
                proxy_host = config.get("proxy_host", "127.0.0.1")
                proxy_port = config.get("proxy_port", 7897)
                self.proxy_url = f"http://{proxy_host}:{proxy_port}"
                print(f"下载器启用代理(shared): {self.proxy_url}")
        except Exception:
            pass

        # 如果没有找到，尝试从 tray_app/config_manager 加载
        if not self.proxy_url:
            try:
                from tray_app.config_manager import ConfigManager

                tray_config = ConfigManager()
                if tray_config.get("proxy_enabled", False):
                    proxy_host = tray_config.get("proxy_host", "127.0.0.1")
                    proxy_port = tray_config.get("proxy_port", 7897)
                    self.proxy_url = f"http://{proxy_host}:{proxy_port}"
                    print(f"下载器启用代理(tray): {self.proxy_url}")
            except Exception:
                pass

    def filter_and_download(
        self,
        pins: List[Pin],
        min_saves: int = 0,
        min_comments: int = 0,
    ) -> List[Pin]:
        filtered_pins = [
            pin
            for pin in pins
            if pin.meets_criteria(min_saves, min_comments)
        ]

        print(f"筛选结果: {len(filtered_pins)}/{len(pins)} 个 Pin 符合条件")

        if not filtered_pins:
            print("没有符合条件的 Pin，跳过下载")
            return []

        downloaded_pins = asyncio.run(self._download_all_images(filtered_pins))

        print(f"下载完成: {len(downloaded_pins)}/{len(filtered_pins)} 张图片")
        return downloaded_pins

    async def _download_all_images(self, pins: List[Pin]) -> List[Pin]:
        """串行下载所有图片（添加延迟保护）"""
        downloaded_pins = []

        connector = None
        if self.proxy_url:
            connector = aiohttp.TCPConnector(local_addr=None)

        async with aiohttp.ClientSession(connector=connector) as session:
            for i, pin in enumerate(pins):
                if pin.image_url or pin.image_url_736x:
                    success = await self._download_image(session, pin)
                    if success:
                        downloaded_pins.append(pin)

                    if i < len(pins) - 1:
                        wait_time = random.uniform(2, 5)
                        print(f"等待 {wait_time:.1f}秒 后继续下载...")
                        await asyncio.sleep(wait_time)

                    if (i + 1) % 10 == 0 and i < len(pins) - 1:
                        rest_time = random.uniform(10, 20)
                        print(f"已下载 {i + 1} 张，休息 {rest_time:.1f}秒...")
                        await asyncio.sleep(rest_time)

        return downloaded_pins

    @staticmethod
    def _generate_url_variants(url: str) -> list:
        """生成 Pinterest 图片多分辨率 URL：736x → originals → 474x → 236x"""
        import re
        match = re.search(r'i\.pinimg\.com/(?:236x|474x|736x|originals)/(.+)', url)
        if not match:
            return [url]
        base = match.group(1)
        return [
            f"https://i.pinimg.com/736x/{base}",
            f"https://i.pinimg.com/originals/{base}",
            f"https://i.pinimg.com/474x/{base}",
            f"https://i.pinimg.com/236x/{base}",
        ]

    async def _download_image(self, session: aiohttp.ClientSession, pin: Pin) -> bool:
        url = pin.image_url or pin.image_url_736x
        if not url:
            return False

        if pin.is_video:
            ext = ".mp4"
        else:
            ext = ".jpg"
            if ".png" in url.lower():
                ext = ".png"
            elif ".gif" in url.lower():
                ext = ".gif"

        filename = f"{pin.saves}_{pin.comments}_{pin.id}{ext}"
        filepath = self.images_dir / filename

        if filepath.exists():
            print(f"图片已存在: {filename}")
            return True

        variants = self._generate_url_variants(url)

        for i, variant_url in enumerate(variants):
            try:
                kwargs = {
                    "timeout": aiohttp.ClientTimeout(total=60),
                    "ssl": False,
                }
                if self.proxy_url:
                    kwargs["proxy"] = self.proxy_url

                async with session.get(variant_url, **kwargs) as response:
                    if response.status == 200:
                        content = await response.read()
                        filepath.write_bytes(content)
                        if i == 0:
                            print(f"下载成功: {filename}")
                        else:
                            print(f"下载成功（降级变体 {i + 1}/{len(variants)}）: {filename}")
                        return True
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass

        print(f"下载失败（所有变体均失败）: {filename}")
        return False
