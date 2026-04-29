"""Ollama 客户端 - AI 图片评估"""

import base64
import json
import logging
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict

from shared.ollama_config import get_ollama_config
from shared.prompt_templates import PromptGenerator

_ollama_logger = logging.getLogger("pinterest_scraper.ollama")


class OllamaClient:
    """Ollama 客户端"""

    def __init__(self, endpoint: Optional[str] = None, model: Optional[str] = None, timeout: Optional[int] = None):
        config = get_ollama_config()
        self.endpoint = endpoint or config.endpoint
        self.model = model or config.model
        self.timeout = timeout or config.timeout
        self.fallback_on_error = config.fallback_on_error
        self.prompt_generator = PromptGenerator()
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """创建带连接池和重试机制的 Session，避免端口耗尽（WinError 10048）"""
        session = requests.Session()
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=4,
            pool_maxsize=8,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @staticmethod
    def _generate_variants(image_url: str) -> list:
        """为 Pinterest 图片生成多分辨率 URL：736x → originals → 474x → 236x"""
        import re
        match = re.search(r'i\.pinimg\.com/(?:236x|474x|736x|originals)/(.+)', image_url)
        if not match:
            return [image_url]
        base = match.group(1)
        return [
            f"https://i.pinimg.com/736x/{base}",
            f"https://i.pinimg.com/originals/{base}",
            f"https://i.pinimg.com/474x/{base}",
            f"https://i.pinimg.com/236x/{base}",
        ]

    def _download_single(self, url: str) -> Optional[bytes]:
        """尝试下载单个 URL，返回图片字节或 None"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://www.pinterest.com/",
            }
            response = self._session.get(url, timeout=30, headers=headers)
            response.raise_for_status()
            return response.content
        except Exception:
            return None

    def _download_image(self, image_url: str) -> Optional[str]:
        """下载图片并转为 base64：按 736x → originals → 474x → 236x 顺序降级"""
        variants = self._generate_variants(image_url)
        for i, url in enumerate(variants):
            # 连接错误时重试一次
            for attempt in range(2):
                content = self._download_single(url)
                if content is not None:
                    return base64.b64encode(content).decode('utf-8')
                if attempt == 0:
                    time.sleep(0.5)
            _ollama_logger.debug(f"[Ollama] 变体 {i+1}/{len(variants)} 失败: {url}")
        _ollama_logger.warning(f"[Ollama] 所有变体均失败，跳过当前 pin")
        return None

    def evaluate_pin(self, image_url: str, query: str, prompt: str = None) -> Dict:
        """
        评估 Pinterest Pin 图片
        
        Args:
            image_url: Pinterest 图片 URL (i.pinimg.com)
            query: 检索词（如"原木风"）
            prompt: 自定义 prompt，不传则使用默认入口筛选 prompt
        
        Returns:
            {
                "is_interior": bool,
                "matches_query": bool,
                "is_approved": bool,
                "reasoning": str
            }
        """
        config = get_ollama_config()
        if not config.enabled:
            return self._default_pass()
        
        # 下载图片转为 base64
        image_base64 = self._download_image(image_url)
        if not image_base64:
            _ollama_logger.warning("[Ollama] 无法获取图片，跳过当前 pin")
            return self._default_fail()
        
        prompt = prompt or self.prompt_generator.generate(query)
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64]
                }
            ],
            "stream": False,
            "format": "json"
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/api/chat",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result_data = response.json()
            content = result_data.get("message", {}).get("content", "")
            
            # 解析 JSON 响应
            parsed = json.loads(content)
            
            # 确保字段完整
            return {
                "is_interior": parsed.get("is_interior", False),
                "matches_query": parsed.get("matches_query", False),
                "is_approved": parsed.get("is_approved", False),
                "reasoning": parsed.get("reasoning", "评估完成"),
            }
            
        except requests.Timeout:
            _ollama_logger.warning(f"[Ollama] 请求超时 ({self.timeout}s)")
            return self._handle_error("timeout")
        except requests.ConnectionError:
            _ollama_logger.warning(f"[Ollama] 连接失败: {self.endpoint}")
            return self._handle_error("connection")
        except json.JSONDecodeError as e:
            _ollama_logger.warning(f"[Ollama] JSON 解析失败: {e}")
            return self._handle_error("parse")
        except Exception as e:
            _ollama_logger.warning(f"[Ollama] 未知错误: {e}")
            return self._handle_error("unknown")

    def evaluate_pins_batch(
        self, image_urls: list, query: str, prompt: str, timeout: int = None
    ) -> list:
        """批量评估多张图片（一次 API 调用），替代逐个串行评估

        Args:
            image_urls: 图片 URL 列表
            query: 检索词
            prompt: 批量评估 prompt（已包含 {count} 等占位符信息）
            timeout: 超时时间（秒），默认使用 self.timeout * 1.5

        Returns:
            [
                {"index": 0, "is_interior": bool, "style_match": int, ...},
                ...
            ]
            失败时返回空列表
        """
        config = get_ollama_config()
        if not config.enabled:
            return []

        # 并发下载所有图片（线程池）
        import concurrent.futures
        base64_list = [None] * len(image_urls)

        _ollama_logger.info(f"[Ollama批量] 并发下载 {len(image_urls)} 张图片...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(self._download_image, url): idx
                for idx, url in enumerate(image_urls)
            }
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    base64_list[idx] = future.result()
                except Exception as e:
                    _ollama_logger.warning(
                        f"[Ollama批量] 图片 {idx} 下载失败: {e}"
                    )

        # 过滤下载失败的，保留有效图片
        valid_base64 = [b64 for b64 in base64_list if b64 is not None]
        if len(valid_base64) < 1:
            _ollama_logger.warning("[Ollama批量] 所有图片下载失败，跳过")
            return []

        skipped_count = len(image_urls) - len(valid_base64)
        if skipped_count > 0:
            _ollama_logger.warning(
                f"[Ollama批量] {skipped_count} 张下载失败，评估 {len(valid_base64)} 张"
            )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": valid_base64,
                }
            ],
            "stream": False,
            "format": "json",
        }

        try:
            response = requests.post(
                f"{self.endpoint}/api/chat",
                json=payload,
                timeout=timeout or int(self.timeout * 1.5),
            )
            response.raise_for_status()

            result_data = response.json()
            content = result_data.get("message", {}).get("content", "")
            parsed = json.loads(content)

            if isinstance(parsed, list):
                _ollama_logger.info(
                    f"[Ollama批量] ✅ 批量评估完成: {len(parsed)} 张"
                )
                return parsed
            elif isinstance(parsed, dict):
                # 模型可能返回了单结果格式，包装为列表
                _ollama_logger.warning("[Ollama批量] 返回了单对象而非数组，包装为列表")
                return [parsed]
            else:
                _ollama_logger.warning(f"[Ollama批量] 未知返回格式: {type(parsed)}")
                return []

        except requests.Timeout:
            _ollama_logger.warning(f"[Ollama批量] 请求超时")
            return []
        except requests.ConnectionError:
            _ollama_logger.warning(f"[Ollama批量] 连接失败: {self.endpoint}")
            return []
        except json.JSONDecodeError as e:
            _ollama_logger.warning(f"[Ollama批量] JSON 解析失败: {e}")
            return []
        except Exception as e:
            _ollama_logger.warning(f"[Ollama批量] 未知错误: {e}")
            return []
    
    def _handle_error(self, error_type: str) -> Dict:
        """处理错误，返回未通过，让调用方跳过当前 pin"""
        _ollama_logger.warning(f"[Ollama] 评估失败 ({error_type})，跳过当前 pin")
        return self._default_fail()

    def _default_pass(self) -> Dict:
        """默认通过（仅当 AI 筛选未启用时使用）"""
        return {
            "is_interior": True,
            "matches_query": True,
            "is_approved": True,
            "reasoning": "AI 筛选未启用，默认通过",
        }

    def _default_fail(self) -> Dict:
        """默认未通过（评估失败时使用，让调用方跳过）"""
        return {
            "is_interior": False,
            "matches_query": False,
            "is_approved": False,
            "reasoning": "AI 评估失败或无法获取图片，跳过",
        }
    
    def health_check(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            response = requests.get(
                f"{self.endpoint}/api/tags",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
