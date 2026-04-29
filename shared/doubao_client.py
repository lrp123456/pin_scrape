"""豆包/火山引擎 视觉模型客户端 - AI 图片评估
使用 openai 库 + Responses API (https://ark.cn-beijing.volces.com/api/v3)

429 限流时不重试，返回 _error="429" 标记让管理器即时降级。
统一使用 openai 库，未来任何 OpenAI 兼容 API 都可用同一方式接入。
"""

import json
import logging
import os
from typing import Optional, Dict, List

from openai import OpenAI

from shared.ollama_config import get_ollama_config
from shared.prompt_templates import PromptGenerator

_doubao_logger = logging.getLogger("pinterest_scraper.doubao")


class DoubaoClient:
    """豆包/火山引擎视觉模型客户端（OpenAI 兼容协议）

    使用 openai 库的 client.responses.create() 调用火山引擎 Responses API。
    智谱等其他 OpenAI 协议提供商也可通过同样的 openai 库接入。
    429 时不重试，标记让管理器即时降级到下个提供商。
    """

    # ── 标记常量 ──
    RATE_LIMITED = "429_rate_limited"  # 429 限流标记

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        config = get_ollama_config()
        # 优先环境变量 ARK_API_KEY（豆包官方推荐方式）
        self.api_key = (
            api_key
            or os.environ.get("ARK_API_KEY")
            or config.doubao_api_key
        )
        self.api_url = api_url or config.doubao_api_url
        self.model = model or config.doubao_model
        self.timeout = timeout or config.doubao_timeout
        self.prompt_generator = PromptGenerator()

        # 使用 openai 库创建客户端
        if self.api_key:
            self._client = OpenAI(
                base_url=self.api_url,
                api_key=self.api_key,
                timeout=self.timeout,
            )
        else:
            self._client = None

    def health_check(self) -> bool:
        """检查是否可用（API Key 已配置）"""
        return bool(self.api_key) and self._client is not None

    # ── 单张评估 ──

    def evaluate_single(
        self,
        image_input: str,  # 图片 URL（https://...）或 base64 字符串
        prompt: str,
    ) -> Optional[Dict]:
        """单张图片评估（入口筛选 / 收集筛选）

        使用 openai 库调用 Responses API：
        client.responses.create(
            model="...",
            input=[{"role": "user", "content": [
                {"type": "input_image", "image_url": "..."},
                {"type": "input_text", "text": "prompt"}
            ]}]
        )

        Args:
            image_input: 图片 URL 或 base64 字符串
            prompt: 评估提示词

        Returns:
            成功 → {is_interior, matches_query, is_approved, reasoning}
            429  → {"_error": "429_rate_limited"}
            其它错误 → None
        """
        if not self._client:
            return None

        # 构建图片内容
        if image_input.startswith(("http://", "https://")):
            image_url = image_input
        else:
            image_url = f"data:image/jpeg;base64,{image_input}"

        try:
            response = self._client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_image", "image_url": image_url},
                            {"type": "input_text", "text": prompt},
                        ],
                    }
                ],
            )

            # 提取文本内容
            text_content = ""
            if response.output:
                for item in response.output[0].content:
                    if hasattr(item, "text"):
                        text_content = item.text
                        break

            if not text_content:
                _doubao_logger.warning("[Doubao] 空响应")
                return None

            # 解析 JSON
            parsed = json.loads(text_content) if isinstance(text_content, str) else text_content

            return {
                "is_interior": parsed.get("is_interior", False),
                "matches_query": parsed.get("matches_query", False),
                "is_approved": parsed.get("is_approved", False),
                "reasoning": parsed.get("reasoning", "评估完成"),
            }

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                _doubao_logger.warning("[Doubao] 429 限流，标记降级")
                return {"_error": self.RATE_LIMITED}
            if "401" in error_str or "unauthorized" in error_str:
                _doubao_logger.error("[Doubao] API Key 无效")
                return None
            _doubao_logger.warning(f"[Doubao] 请求失败: {e}")
            return None

    # ── 批量评估 ──

    def evaluate_batch(
        self,
        image_inputs: List[str],  # 图片 URL 或 base64 列表
        prompt: str,
    ) -> Optional[List[Dict]]:
        """批量评估多张图片（单次 API 调用）

        Args:
            image_inputs: 图片列表
            prompt: 批量评估提示词

        Returns:
            成功 → [{index, is_interior, style_match, ...}, ...]
            429  → [{"_error": "429_rate_limited"}]
            失败 → None
        """
        if not self._client or not image_inputs:
            return None

        # 构建多图 input
        content_list = []
        for img in image_inputs:
            if img.startswith(("http://", "https://")):
                image_url = img
            else:
                image_url = f"data:image/jpeg;base64,{img}"
            content_list.append({"type": "input_image", "image_url": image_url})
        content_list.append({"type": "input_text", "text": prompt})

        try:
            response = self._client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": content_list}],
            )

            # 提取文本
            text_content = ""
            if response.output:
                for item in response.output[0].content:
                    if hasattr(item, "text"):
                        text_content = item.text
                        break

            if not text_content:
                _doubao_logger.warning("[Doubao] 批量空响应")
                return None

            # 解析 JSON 数组
            parsed = json.loads(text_content) if isinstance(text_content, str) else text_content
            if isinstance(parsed, dict):
                parsed = [parsed]

            results = []
            for i, item in enumerate(parsed):
                item["index"] = i
                results.append(item)

            # 补齐
            while len(results) < len(image_inputs):
                results.append({
                    "index": len(results),
                    "is_interior": False, "style_match": 0,
                    "has_human": True, "scene_completeness": 0,
                    "is_approved": False, "reasoning": "结果缺失",
                })
            return results

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                _doubao_logger.warning("[Doubao] 批量 429 限流，标记降级")
                return [{"_error": self.RATE_LIMITED}]
            _doubao_logger.warning(f"[Doubao] 批量失败: {e}")
            return None

    @staticmethod
    def _default_fail() -> Dict:
        return {
            "is_interior": False,
            "matches_query": False,
            "is_approved": False,
            "reasoning": "Doubao AI 评估失败，跳过",
        }
