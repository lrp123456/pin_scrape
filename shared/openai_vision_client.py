# -*- coding: utf-8 -*-
"""通用 OpenAI 兼容视觉模型客户端

支持所有 OpenAI 协议兼容的 API 提供商（智谱、Gitee、硅基流动等）。
统一接口，方便热插拔和降级。

429 限流时不重试，返回 _error="429" 标记让管理器即时降级。
"""

import json
import logging
import re
from typing import Optional, Dict

from openai import OpenAI

_vision_logger = logging.getLogger("pinterest_scraper.openai_vision")


class OpenAIVisionClient:
    """通用 OpenAI 兼容视觉模型客户端

    适用于智谱 GLM、Gitee AI、硅基流动等所有 OpenAI 协议兼容的 API。
    使用 chat.completions.create() 接口，支持图片 URL 和 base64 输入。
    """

    # 标记常量
    RATE_LIMITED = "429_rate_limited"

    def __init__(
        self,
        provider_name: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 60,
    ):
        """初始化客户端

        Args:
            provider_name: 提供商名称（用于日志，如 "Zhipu"、"Gitee"、"SiliconFlow"）
            api_key: API 密钥
            base_url: API 基础 URL（openai 库会自动拼接 /chat/completions）
            model: 模型名称
            timeout: 请求超时时间（秒）
        """
        self.provider_name = provider_name
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

        # 处理 base_url：如果以 /chat/completions 结尾则去掉（openai 库会自动拼接）
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]
        # 确保以 / 结尾（openai 库要求）
        if not base_url.endswith("/"):
            base_url += "/"

        self.base_url = base_url

        # 使用 openai 库创建客户端
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,  # 不重试，429 即时返回标记让管理器降级
        )

    def health_check(self) -> bool:
        """检查 API 是否可用（API Key 已配置）"""
        return bool(self.api_key) and self._client is not None

    def evaluate_pin_with_url(
        self, image_url: str, query: str, prompt: str
    ) -> Optional[Dict]:
        """使用图片 URL 评估 Pin

        Args:
            image_url: 图片的公开 URL
            query: 检索词
            prompt: 评估提示词

        Returns:
            成功 → {is_interior, matches_query, is_approved, reasoning}
            429  → {"_error": "429_rate_limited"}
            失败 → None
        """
        if not self.api_key:
            _vision_logger.warning(f"[{self.provider_name}] API key 未配置")
            return None

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=500,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            if not content:
                _vision_logger.warning(f"[{self.provider_name}] URL 模式空响应")
                return None

            return self._parse_response(content)

        except Exception as e:
            return self._handle_error(e, "URL")

    def evaluate_pin_with_base64(
        self, base64_data: str, query: str, prompt: str
    ) -> Optional[Dict]:
        """使用 base64 图片数据评估 Pin

        Args:
            base64_data: 图片的 base64 编码（不含 data:image 前缀）
            query: 检索词
            prompt: 评估提示词

        Returns:
            评估结果字典，429 时返回 {"_error": "429_rate_limited"} 标记
        """
        if not self.api_key:
            _vision_logger.warning(f"[{self.provider_name}] API key 未配置")
            return None

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_data}"
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=500,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            if not content:
                _vision_logger.warning(f"[{self.provider_name}] base64 模式空响应")
                return None

            return self._parse_response(content)

        except Exception as e:
            return self._handle_error(e, "base64")

    def _parse_response(self, content: str) -> Optional[Dict]:
        """解析 AI 响应 JSON"""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # 尝试提取 JSON 子串
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                except json.JSONDecodeError:
                    _vision_logger.warning(
                        f"[{self.provider_name}] JSON 解析失败: {content[:200]}"
                    )
                    return None
            else:
                _vision_logger.warning(
                    f"[{self.provider_name}] JSON 解析失败: {content[:200]}"
                )
                return None

        return {
            "is_interior": parsed.get("is_interior", False),
            "matches_query": parsed.get("matches_query", False),
            "is_approved": parsed.get("is_approved", False),
            "reasoning": parsed.get("reasoning", "评估完成"),
        }

    def _handle_error(self, error: Exception, mode: str) -> Optional[Dict]:
        """处理 API 错误"""
        error_str = str(error)
        # 429 限流 → 返回标记让管理器降级
        if "429" in error_str or "rate" in error_str.lower():
            _vision_logger.warning(
                f"[{self.provider_name}] {mode} 429 限流 → 返回标记"
            )
            return {"_error": self.RATE_LIMITED}
        _vision_logger.warning(
            f"[{self.provider_name}] {mode} API 错误: {error_str[:200]}"
        )
        return None
