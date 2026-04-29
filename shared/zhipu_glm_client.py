"""智谱 GLM-4V 客户端 - OpenAI 协议统一接口

使用 openai 库调用智谱 API，与其他 provider 统一协议，方便热插拔。
"""

import json
import logging
from typing import Optional, Dict

from openai import OpenAI

from shared.ollama_config import get_ollama_config

_zhipu_logger = logging.getLogger("pinterest_scraper.zhipu")


class ZhipuGLMClient:
    """智谱 GLM-4V 视觉模型客户端（OpenAI 协议）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        config = get_ollama_config()
        self.api_key = api_key or config.zhipu_api_key
        # 智谱 OpenAI 兼容 Base URL（注意：必须以 /v1 结尾以确保 openai 库正确拼接路径）
        self.base_url = base_url or config.zhipu_api_url
        self.model = model or config.zhipu_model
        self.timeout = timeout or config.zhipu_timeout

        # 使用 openai 库创建客户端
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=0,  # 不重试，429 即时返回标记让管理器降级
        )

    def health_check(self) -> bool:
        """检查智谱 API 是否可用"""
        try:
            # 列出模型（轻量级检查），某些 OpenAI 兼容端点不支持 models.list
            self._client.models.list()
            return True
        except Exception as e:
            _zhipu_logger.debug(f"[Zhipu] health_check 失败: {e}")
            # 即使 models.list 失败（部分端点不支持），只要有 API key 就尝试使用
            return bool(self.api_key)

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
            _zhipu_logger.warning("[Zhipu] API key 未配置")
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
                response_format={"type": "json_object"},  # 请求 JSON 输出
            )

            content = response.choices[0].message.content
            if not content:
                _zhipu_logger.warning("[Zhipu] 空响应")
                return None

            # 解析 JSON 响应
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                # 尝试提取 JSON 子串
                import re

                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        _zhipu_logger.warning(
                            f"[Zhipu] JSON 解析失败: {content[:200]}"
                        )
                        return None
                else:
                    _zhipu_logger.warning(
                        f"[Zhipu] JSON 解析失败: {content[:200]}"
                    )
                    return None

            return {
                "is_interior": parsed.get("is_interior", False),
                "matches_query": parsed.get("matches_query", False),
                "is_approved": parsed.get("is_approved", False),
                "reasoning": parsed.get("reasoning", "评估完成"),
            }

        except Exception as e:
            error_str = str(e)
            # 429 限流 → 返回标记让管理器降级
            if "429" in error_str or "rate" in error_str.lower():
                _zhipu_logger.warning(f"[Zhipu] 429 限流 → 返回标记")
                return {"_error": "429_rate_limited"}
            _zhipu_logger.warning(f"[Zhipu] API 错误: {error_str[:200]}")
            return None

    def evaluate_pin_with_url(
        self, image_url: str, query: str, prompt: str
    ) -> Optional[Dict]:
        """使用图片 URL 评估 Pin（智谱支持直接传 URL）

        Args:
            image_url: 图片的公开 URL
            query: 检索词
            prompt: 评估提示词

        Returns:
            评估结果字典
        """
        if not self.api_key:
            _zhipu_logger.warning("[Zhipu] API key 未配置")
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
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                _zhipu_logger.warning("[Zhipu] URL 模式空响应")
                return None

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                import re

                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        _zhipu_logger.warning(f"[Zhipu] URL JSON 解析失败")
                        return None
                else:
                    return None

            return {
                "is_interior": parsed.get("is_interior", False),
                "matches_query": parsed.get("matches_query", False),
                "is_approved": parsed.get("is_approved", False),
                "reasoning": parsed.get("reasoning", "评估完成"),
            }

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate" in error_str.lower():
                _zhipu_logger.warning(f"[Zhipu] URL 429 限流")
                return {"_error": "429_rate_limited"}
            _zhipu_logger.warning(f"[Zhipu] URL API 错误: {error_str[:200]}")
            return None
