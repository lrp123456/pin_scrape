"""AI 筛选管理器 - 多 provider 动态降级 + 动态提示词

降级顺序（由 ollama_config.json 的 ai_provider_priority 配置）：
  1. 智谱 GLM URL（免费模型 glm-4.6v-flash）
  2. Gitee AI URL（GLM-4.6V-Flash）
  3. 硅基流动 URL（Qwen3.5-4B）
  4. 豆包 base64（doubao-seed-2-0-lite-260215）
  5. Ollama 本地模型 base64（兜底）

核心设计：
  429 限流 → 不重试，即时降级到下一个 provider
  动态提示词 → 首次评估时自动用 LLM 将查询词转为详细视觉筛选清单
  全部使用 OpenAI 协议统一接口，方便热插拔
"""

import logging
import time
from typing import Optional, Dict

from shared.ollama_config import get_ollama_config
from shared.openai_vision_client import OpenAIVisionClient
from shared.ollama_client import OllamaClient

# 豆包客户端延迟导入（openai 库可能未安装）
_doubao_imported = False
DoubaoClient = None

_filter_logger = logging.getLogger("pinterest_scraper.ai_filter")


class AIFilterManager:
    """AI 筛选管理器：按配置优先级自动降级，支持动态提示词"""

    def __init__(self, timeout: int = 180):
        config = get_ollama_config()
        self.priority = config.ai_provider_priority
        self.timeout = timeout

        self._doubao_available = False  # 默认不可用，init 中尝试加载

        # 使用通用 OpenAI 兼容客户端初始化各 provider
        self.zhipu = OpenAIVisionClient(
            provider_name="Zhipu",
            api_key=config.zhipu_api_key,
            base_url=config.zhipu_api_url,
            model=config.zhipu_model,
            timeout=config.zhipu_timeout,
        )
        self.gitee = OpenAIVisionClient(
            provider_name="Gitee",
            api_key=config.gitee_api_key,
            base_url=config.gitee_api_url,
            model=config.gitee_model,
            timeout=config.gitee_timeout,
        )
        self.siliconflow = OpenAIVisionClient(
            provider_name="SiliconFlow",
            api_key=config.siliconflow_api_key,
            base_url=config.siliconflow_api_url,
            model=config.siliconflow_model,
            timeout=config.siliconflow_timeout,
        )
        self.ollama = OllamaClient(timeout=timeout)

        # 延迟加载豆包客户端（使用 Responses API，与 Chat Completions 不同）
        global _doubao_imported, DoubaoClient
        if not _doubao_imported:
            try:
                from shared.doubao_client import DoubaoClient as _DC
                DoubaoClient = _DC
                _doubao_imported = True
            except ImportError:
                _doubao_imported = True  # 标记已尝试，避免重复警告
                _filter_logger.warning("[AI筛选] openai 库未安装，豆包客户端不可用。安装: pip install openai")

        if DoubaoClient:
            self.doubao = DoubaoClient()
            self._doubao_available = self.doubao.health_check()
        else:
            self.doubao = None
        self._zhipu_available = self.zhipu.health_check()
        self._gitee_available = self.gitee.health_check()
        self._siliconflow_available = self.siliconflow.health_check()
        self._ollama_available = self.ollama.health_check()
        self._last_call_time = 0
        self._min_interval = 2.0  # 连续调用最小间隔（秒）

        # 动态提示词：懒加载，首次使用某个查询词时才生成
        self._dynamic_enabled = True

        _filter_logger.info(
            f"[AI筛选] Provider 状态: Zhipu={self._zhipu_available}, "
            f"Gitee={self._gitee_available}, SiliconFlow={self._siliconflow_available}, "
            f"Doubao={self._doubao_available}, Ollama={self._ollama_available}, "
            f"优先级={self.priority}"
        )

    def _wait_interval(self):
        """确保连续调用之间至少间隔 _min_interval 秒"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    def generate_dynamic_criteria(self, query: str) -> bool:
        """生成动态视觉筛选标准（应在爬虫初始化后首次调用）

        调用 LLM 将查询词转化为详细的视觉筛选清单，
        缓存以供后续所有 evaluate_pin 调用使用。

        Args:
            query: 用户的搜索查询词（如"现代简约"）

        Returns:
            True 表示动态生成成功，False 表示回退到静态模板
        """
        if not self._dynamic_enabled:
            return False

        from shared.prompt_templates import PromptGenerator

        # 已有缓存则跳过
        if PromptGenerator.has_dynamic_criteria(query):
            _filter_logger.info(f"[动态提示词] 已有缓存，跳过生成: {query}")
            return True

        _filter_logger.info(f"[动态提示词] 开始为查询词生成视觉筛选标准: {query}")

        try:
            from shared.dynamic_prompt import generate_dynamic_criteria

            config = get_ollama_config()
            llm_endpoint = config.endpoint
            llm_model = config.model

            result = generate_dynamic_criteria(
                query=query,
                ollama_endpoint=llm_endpoint,
                ollama_model=llm_model,
                timeout=120,
            )

            if result:
                PromptGenerator.set_dynamic_criteria(query, result)
                _filter_logger.info(
                    f"[动态提示词] ✅ 已缓存视觉筛选标准: "
                    f"{len(result.get('criteria', ''))} 字符, "
                    f"{len(result.get('style_keywords', []))} 个关键词"
                )
                return True
            else:
                _filter_logger.warning("[动态提示词] 生成失败，本会话使用静态模板")
                self._dynamic_enabled = False
                return False

        except Exception as e:
            _filter_logger.warning(f"[动态提示词] 异常，回退静态模板: {e}")
            self._dynamic_enabled = False
            return False

    def _resolve_dynamic_template(self, query: str) -> Optional[dict]:
        """解析动态模板：从 PromptGenerator 缓存获取"""
        from shared.prompt_templates import PromptGenerator

        if PromptGenerator.has_dynamic_criteria(query):
            return PromptGenerator._resolve_template(query)
        return None

    def evaluate_pin(self, image_url: str, query: str) -> Dict:
        """入口筛选：评估 Pin 图片是否为室内场景且符合检索词

        优先使用动态生成的视觉筛选标准，回退到静态模板。
        """
        from shared.prompt_templates import PromptGenerator

        dynamic_template = self._resolve_dynamic_template(query)
        prompt = PromptGenerator.generate(query, dynamic_template)
        return self._evaluate_with_prompt(image_url, query, prompt)

    def evaluate_pin_for_collection(self, image_url: str, query: str) -> Dict:
        """收集阶段深度筛选：评估风格匹配度、人物排除、场景完整性

        优先使用动态生成的视觉筛选标准，回退到静态模板。
        """
        from shared.prompt_templates import PromptGenerator

        dynamic_template = self._resolve_dynamic_template(query)
        prompt = PromptGenerator.generate_collection_prompt(query, dynamic_template)
        result = self._evaluate_with_prompt(image_url, query, prompt)

        # 统一返回格式
        if result:
            return self._normalize_collection_result(result)
        return self._default_collection_item_fail()

    def evaluate_pins_batch(
        self, image_urls: list, query: str, batch_size: int = 5
    ) -> list:
        """批量收集阶段深度筛选：一次 API 调用评估多张图片

        按 batch_size 分批调用 Ollama（目前仅 Ollama 支持 batch 多图），
        大幅减少串行 API 调用次数。

        Args:
            image_urls: 图片 URL 列表
            query: 检索词
            batch_size: 每批图片数量（默认 5）

        Returns:
            [{"index": 0, "is_interior": bool, "style_match": int, ...}, ...]
            按 image_urls 的原始索引返回
        """
        from shared.prompt_templates import PromptGenerator

        dynamic_template = self._resolve_dynamic_template(query)
        total = len(image_urls)
        all_results = []

        for batch_start in range(0, total, batch_size):
            batch_urls = image_urls[batch_start : batch_start + batch_size]
            actual_count = len(batch_urls)

            _filter_logger.info(
                f"[AI批量筛选] 第 {batch_start // batch_size + 1} 批: "
                f"评估 {actual_count} 张 (总进度 {batch_start}/{total})"
            )

            prompt = PromptGenerator.generate_batch_collection_prompt(
                actual_count, query, dynamic_template
            )

            batch_results = self._evaluate_batch_with_providers(
                batch_urls, query, prompt
            )

            if batch_results:
                # 偏移索引以匹配原始 image_urls 的位置
                for item in batch_results:
                    item["index"] = item.get("index", 0) + batch_start
                all_results.extend(batch_results)
            else:
                # 该批次失败，为每张图创建默认失败结果
                _filter_logger.warning(
                    f"[AI批量筛选] 第 {batch_start // batch_size + 1} 批全部失败，"
                    f" {actual_count} 张默认不通过"
                )
                for i in range(batch_start, batch_start + actual_count):
                    all_results.append(
                        {**self._default_collection_item_fail(), "index": i}
                    )

        _filter_logger.info(
            f"[AI批量筛选] ✅ 全部批次完成: {total} 张 → {len(all_results)} 个结果"
        )
        return all_results

    def _normalize_collection_result(self, result: Dict) -> Dict:
        """统一收集结果格式（单张评估用）"""
        return {
            "is_interior": result.get("is_interior", False),
            "style_match": result.get("style_match", 0),
            "has_human": result.get("has_human", True),
            "scene_completeness": result.get("scene_completeness", 0),
            "is_approved": result.get("is_approved", False),
            "reasoning": result.get("reasoning", "评估完成"),
        }

    @staticmethod
    def _default_collection_item_fail() -> Dict:
        """单张收集评估失败时的默认结果"""
        return {
            "is_interior": False,
            "style_match": 0,
            "has_human": True,
            "scene_completeness": 0,
            "is_approved": False,
            "reasoning": "AI 评估失败，默认不通过",
        }

    def _evaluate_batch_with_providers(
        self, image_urls: list, query: str, prompt: str
    ) -> list:
        """批量评估：按配置优先级尝试 provider

        优先尝试豆包批量（单次 API），其次 Ollama 批量，最后逐个降级。
        429 限流 → 即时跳转到下一个 provider（不重试）。
        """
        # 1. 豆包批量（优先）
        if "doubao_batch" in self.priority and self._doubao_available:
            _filter_logger.info(f"[AI批量筛选] Doubao 批量评估 {len(image_urls)} 张")
            results = self.doubao.evaluate_batch(image_urls, prompt)
            if results:
                if isinstance(results, list) and len(results) > 0 and isinstance(results[0], dict) and results[0].get("_error"):
                    _filter_logger.warning("[AI批量筛选] Doubao 429 → 降级")
                else:
                    _filter_logger.info(f"[AI批量筛选] Doubao 批量 ✅: {len(results)} 个结果")
                    return results

        # 2. Ollama 批量
        if "ollama" in self.priority and self._ollama_available:
            _filter_logger.info(f"[AI批量筛选] Ollama 批量评估 {len(image_urls)} 张")
            results = self.ollama.evaluate_pins_batch(image_urls, query, prompt)
            if results:
                _filter_logger.info(f"[AI批量筛选] Ollama 批量 ✅: {len(results)} 个结果")
                return results
            _filter_logger.warning("[AI批量筛选] Ollama 批量失败，降级")

        # 3. 降级：逐个评估（所有 provider）
        _filter_logger.info(
            f"[AI批量筛选] 逐个评估 {len(image_urls)} 张（降级模式）"
        )
        results = []
        for idx, url in enumerate(image_urls):
            self._wait_interval()
            result = self._evaluate_with_prompt(url, query, prompt)
            if result:
                result["index"] = idx
                results.append(result)
            else:
                results.append(
                    {**self._default_collection_item_fail(), "index": idx}
                )
        return results

    def _evaluate_with_prompt(self, image_url: str, query: str, prompt: str) -> Optional[Dict]:
        """使用指定 prompt 评估图片，按配置优先级自动降级

        如果 provider 返回 429 限流标记 → 即时跳转到下一个 provider（不重试）。
        """
        result = None

        for provider in self.priority:
            if result is not None:
                break

            self._wait_interval()

            # ── 智谱 URL ──
            if provider == "zhipu_url" and self._zhipu_available:
                _filter_logger.info("[AI筛选] 使用 Zhipu URL 评估")
                result = self.zhipu.evaluate_pin_with_url(image_url, query, prompt)
                if result:
                    if isinstance(result, dict) and result.get("_error"):
                        _filter_logger.warning("[AI筛选] Zhipu 429 → 降级")
                        result = None
                    else:
                        _filter_logger.info("[AI筛选] Zhipu ✅")

            # ── 智谱 base64 ──
            elif provider == "zhipu_base64" and self._zhipu_available:
                _filter_logger.info("[AI筛选] 使用 Zhipu base64 评估")
                base64_data = self.ollama._download_image(image_url)
                if base64_data:
                    result = self.zhipu.evaluate_pin_with_base64(base64_data, query, prompt)
                    if result:
                        if isinstance(result, dict) and result.get("_error"):
                            _filter_logger.warning("[AI筛选] Zhipu 429 → 降级")
                            result = None
                        else:
                            _filter_logger.info("[AI筛选] Zhipu ✅")

            # ── Gitee URL ──
            elif provider == "gitee_url" and self._gitee_available:
                _filter_logger.info("[AI筛选] 使用 Gitee URL 评估")
                result = self.gitee.evaluate_pin_with_url(image_url, query, prompt)
                if result:
                    if isinstance(result, dict) and result.get("_error"):
                        _filter_logger.warning("[AI筛选] Gitee 429 → 降级")
                        result = None
                    else:
                        _filter_logger.info("[AI筛选] Gitee ✅")

            # ── Gitee base64 ──
            elif provider == "gitee_base64" and self._gitee_available:
                _filter_logger.info("[AI筛选] 使用 Gitee base64 评估")
                base64_data = self.ollama._download_image(image_url)
                if base64_data:
                    result = self.gitee.evaluate_pin_with_base64(base64_data, query, prompt)
                    if result:
                        if isinstance(result, dict) and result.get("_error"):
                            _filter_logger.warning("[AI筛选] Gitee 429 → 降级")
                            result = None
                        else:
                            _filter_logger.info("[AI筛选] Gitee ✅")

            # ── SiliconFlow URL ──
            elif provider == "siliconflow_url" and self._siliconflow_available:
                _filter_logger.info("[AI筛选] 使用 SiliconFlow URL 评估")
                result = self.siliconflow.evaluate_pin_with_url(image_url, query, prompt)
                if result:
                    if isinstance(result, dict) and result.get("_error"):
                        _filter_logger.warning("[AI筛选] SiliconFlow 429 → 降级")
                        result = None
                    else:
                        _filter_logger.info("[AI筛选] SiliconFlow ✅")

            # ── SiliconFlow base64 ──
            elif provider == "siliconflow_base64" and self._siliconflow_available:
                _filter_logger.info("[AI筛选] 使用 SiliconFlow base64 评估")
                base64_data = self.ollama._download_image(image_url)
                if base64_data:
                    result = self.siliconflow.evaluate_pin_with_base64(base64_data, query, prompt)
                    if result:
                        if isinstance(result, dict) and result.get("_error"):
                            _filter_logger.warning("[AI筛选] SiliconFlow 429 → 降级")
                            result = None
                        else:
                            _filter_logger.info("[AI筛选] SiliconFlow ✅")

            # ── 豆包 base64（单张） ──
            elif provider == "doubao_base64" and self._doubao_available:
                _filter_logger.info("[AI筛选] 使用 Doubao base64 评估")
                base64_data = self.ollama._download_image(image_url)
                if base64_data:
                    result = self.doubao.evaluate_single(base64_data, prompt)
                    if result:
                        if isinstance(result, dict) and result.get("_error"):
                            _filter_logger.warning("[AI筛选] Doubao 429 → 降级")
                            result = None  # 清空，继续到下一个 provider
                        else:
                            _filter_logger.info("[AI筛选] Doubao ✅")

            # ── Ollama 本地 ──
            elif provider == "ollama" and self._ollama_available:
                _filter_logger.info("[AI筛选] 使用 Ollama 评估")
                result = self.ollama.evaluate_pin(image_url, query, prompt)
                if result and result.get("is_approved") is not None:
                    _filter_logger.info("[AI筛选] Ollama ✅")

        if result is None:
            _filter_logger.warning("[AI筛选] 所有 provider 均失败，默认未通过")
            return None

        return result

    @staticmethod
    def _default_fail() -> Dict:
        return {
            "is_interior": False,
            "matches_query": False,
            "is_approved": False,
            "reasoning": "AI 评估失败，跳过",
        }

    @staticmethod
    def _default_collection_fail() -> Dict:
        return {
            "is_interior": False,
            "style_match": 0,
            "has_human": True,
            "scene_completeness": 0,
            "is_approved": False,
            "reasoning": "AI 评估失败，跳过",
        }
