# -*- coding: utf-8 -*-
"""异步 AI 筛选工作池 - 浏览与 AI 筛选并行解耦

核心设计：
- 主线程只负责浏览/点击/提取数据，不等待 AI 结果
- AI 任务提交到线程池后台处理（并发 2~3 个）
- AI 结果通过回调异步通知，决定是否收集/爬坡
- 筛选结果写入协调器缓存，其他 Worker 可直接复用

使用方式:
    worker = AsyncAIWorker(ai_manager, coordinator)
    worker.register_callback("collection", on_collection_result)

    # 主线程快速浏览
    for pin in pins:
        worker.submit_collection_filter(pin.id, pin.image_url, query)
        # 不等待，继续下一个
"""

import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Optional, Dict, Callable, List, Any, Tuple
from dataclasses import dataclass, field

_logger = logging.getLogger("pinterest_scraper.async_ai")


@dataclass(order=True)
class AITask:
    """AI 筛选任务"""

    priority: int  # 0=高优(入口预筛), 1=普通(收集筛选)
    pin_id: str
    image_url: str
    query: str
    task_type: str  # "entry"(入口预筛) | "collection"(收集筛选) | "batch"(批量收集)
    metadata: dict = field(compare=False, default_factory=dict)
    submit_time: float = field(default_factory=time.time, compare=False)


class AsyncAIWorker:
    """异步 AI 筛选工作池

    支持三种任务类型：
    - entry: 入口预筛选（单图，快速判断风格/室内）
    - collection: 收集深度筛选（单图，详细评估 5 维度）
    - batch: 批量收集筛选（多图，一次 API 调用评估多张）
    """

    def __init__(
        self,
        ai_manager,
        coordinator,
        max_workers: int = 2,
    ):
        """
        Args:
            ai_manager: AIFilterManager 实例（支持 evaluate_pin / evaluate_pin_for_collection / evaluate_pins_batch）
            coordinator: ScrapeCoordinator 实例（缓存命中时直接回调，不占用线程）
            max_workers: AI 处理线程池大小（建议 2~3，太大浪费资源）
        """
        self._ai_manager = ai_manager
        self._coordinator = coordinator
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ai_worker")
        self._lock = threading.Lock()
        self._futures: Dict[str, Future] = {}  # pin_id → Future

        # 回调注册：每种任务类型可注册多个回调
        # 回调签名: callback(pin_id: str, result: dict | None)
        self._callbacks: Dict[str, List[Callable]] = {
            "entry": [],
            "collection": [],
            "batch": [],
        }

        # 批量累积器（凑够 batch_size 后一次性提交）
        self._batch_buffer: List[Tuple[str, str]] = []  # [(pin_id, image_url), ...]
        self._batch_size = 5
        self._batch_query = ""
        self._batch_lock = threading.Lock()

        # 统计
        self._submitted = 0
        self._completed = 0
        self._cache_hits = 0
        self._total_api_calls = 0

        _logger.info(f"[异步AI] 初始化完成，线程池={max_workers}，批量={self._batch_size}")

    # ═══════════════════════════════════════════════════════════════
    # 提交任务
    # ═══════════════════════════════════════════════════════════════

    def submit_entry_filter(self, pin_id: str, image_url: str, query: str) -> bool:
        """提交入口预筛选任务

        Args:
            pin_id: Pin ID
            image_url: 图片 URL（搜索页缩略图）
            query: 搜索关键词

        Returns:
            True: 已提交
            False: 缓存命中，直接回调过了
        """
        return self._submit(pin_id, image_url, query, "entry", priority=0)

    def submit_collection_filter(self, pin_id: str, image_url: str, query: str) -> bool:
        """提交收集深度筛选任务

        Returns:
            True: 已提交
            False: 缓存命中
        """
        return self._submit(pin_id, image_url, query, "collection", priority=1)

    def add_to_batch(self, pin_id: str, image_url: str, query: str) -> int:
        """添加到批量累积器，满 batch_size 自动提交

        Returns:
            当前缓冲区大小（提交后归零）
        """
        with self._batch_lock:
            self._batch_buffer.append((pin_id, image_url))
            self._batch_query = query

            if len(self._batch_buffer) >= self._batch_size:
                return self._flush_batch()
            return len(self._batch_buffer)

    def _flush_batch(self) -> int:
        """冲刷批量缓冲区并提交"""
        if not self._batch_buffer:
            return 0

        pin_ids = [item[0] for item in self._batch_buffer]
        image_urls = [item[1] for item in self._batch_buffer]
        query = self._batch_query
        self._batch_buffer.clear()

        # 过滤掉已有缓存的
        filtered_pins = []
        filtered_urls = []
        for pid, url in zip(pin_ids, image_urls):
            cached = self._coordinator.get_filter_result(pid)
            if cached is not None:
                self._cache_hits += 1
                self._notify_callbacks("collection", pid, cached)
            else:
                filtered_pins.append(pid)
                filtered_urls.append(url)

        if not filtered_pins:
            return 0

        task = AITask(
            priority=1,
            pin_id=",".join(filtered_pins),
            image_url="",
            query=query,
            task_type="batch",
            metadata={"pin_ids": filtered_pins, "image_urls": filtered_urls},
        )
        batch_id = f"batch_{int(time.time() * 1000)}"

        with self._lock:
            self._submitted += 1
            self._total_api_calls += 1
            future = self._executor.submit(self._process_batch, task)
            self._futures[batch_id] = future

        _logger.debug(f"[异步AI] 提交批量任务: {len(filtered_pins)} 张, id={batch_id}")
        return 0

    def flush_batch(self):
        """手动冲刷批量缓冲区（处理完一批后调用）"""
        with self._batch_lock:
            self._flush_batch()

    def _submit(self, pin_id: str, image_url: str, query: str, task_type: str, priority: int) -> bool:
        """提交单图任务（内部方法）"""
        # 先查缓存
        cached = self._coordinator.get_filter_result(pin_id)
        if cached is not None:
            self._cache_hits += 1
            _logger.debug(f"[异步AI] 缓存命中: {pin_id[:12]}...")
            self._notify_callbacks(task_type, pin_id, cached)
            return False

        task = AITask(priority=priority, pin_id=pin_id, image_url=image_url, query=query, task_type=task_type)

        with self._lock:
            self._submitted += 1
            self._total_api_calls += 1
            future = self._executor.submit(self._process_single, task)
            self._futures[pin_id] = future

        _logger.debug(f"[异步AI] 提交: {pin_id[:12]}... type={task_type}")
        return True

    # ═══════════════════════════════════════════════════════════════
    # 处理任务（在线程池中运行）
    # ═══════════════════════════════════════════════════════════════

    def _process_single(self, task: AITask):
        """处理单图 AI 筛选（在子线程中运行）"""
        try:
            _logger.debug(f"[异步AI] 开始: {task.pin_id[:12]}... type={task.task_type}")

            if task.task_type == "entry":
                result = self._ai_manager.evaluate_pin(task.image_url, task.query)
            else:
                result = self._ai_manager.evaluate_pin_for_collection(task.image_url, task.query)

            # 缓存结果供其他 Worker 复用
            if result:
                self._coordinator.set_filter_result(task.pin_id, result)

            self._notify_callbacks(task.task_type, task.pin_id, result)

            with self._lock:
                self._completed += 1

            approved = result.get("is_approved", False) if result else "None"
            _logger.debug(f"[异步AI] 完成: {task.pin_id[:12]}... approved={approved}")

        except Exception as e:
            _logger.warning(f"[异步AI] 单图处理异常: {task.pin_id[:12]}... error={e}")
            self._notify_callbacks(task.task_type, task.pin_id, None)

    def _process_batch(self, task: AITask):
        """处理批量 AI 筛选（在子线程中运行）"""
        try:
            pin_ids = task.metadata["pin_ids"]
            image_urls = task.metadata["image_urls"]
            _logger.debug(f"[异步AI] 批量开始: {len(pin_ids)} 张")

            results = self._ai_manager.evaluate_pins_batch(image_urls, task.query, batch_size=len(image_urls))

            # 缓存每个结果
            if results:
                for i, result in enumerate(results):
                    if i < len(pin_ids):
                        self._coordinator.set_filter_result(pin_ids[i], result)
                        self._notify_callbacks("collection", pin_ids[i], result)
            else:
                # 全部失败，通知空结果
                for pid in pin_ids:
                    self._notify_callbacks("collection", pid, None)

            with self._lock:
                self._completed += 1

            _logger.debug(f"[异步AI] 批量完成: {len(pin_ids)} 张")

        except Exception as e:
            _logger.warning(f"[异步AI] 批量处理异常: {e}")
            for pid in task.metadata["pin_ids"]:
                self._notify_callbacks("collection", pid, None)

    # ═══════════════════════════════════════════════════════════════
    # 回调机制
    # ═══════════════════════════════════════════════════════════════

    def register_callback(self, task_type: str, callback: Callable[[str, Optional[dict]], None]):
        """注册结果回调

        Args:
            task_type: "entry" | "collection" | "batch"
            callback: 回调函数，接收 (pin_id: str, result: dict | None)
        """
        if task_type in self._callbacks:
            self._callbacks[task_type].append(callback)
            _logger.debug(f"[异步AI] 注册回调: type={task_type}")

    def _notify_callbacks(self, task_type: str, pin_id: str, result: Optional[dict]):
        """通知所有注册的回调（线程安全）"""
        for cb in self._callbacks.get(task_type, []):
            try:
                cb(pin_id, result)
            except Exception as e:
                _logger.warning(f"[异步AI] 回调异常: type={task_type}, error={e}")

    # ═══════════════════════════════════════════════════════════════
    # 状态查询
    # ═══════════════════════════════════════════════════════════════

    def is_done(self, pin_id: str) -> bool:
        """检查指定任务是否已完成"""
        with self._lock:
            future = self._futures.get(pin_id)
            return future is not None and future.done()

    def wait_for(self, pin_id: str, timeout: Optional[float] = None) -> Optional[dict]:
        """阻塞等待任务完成并获取结果（从缓存读取）"""
        with self._lock:
            future = self._futures.get(pin_id)
        if future is None:
            return self._coordinator.get_filter_result(pin_id)
        try:
            future.result(timeout=timeout)
        except Exception:
            pass
        return self._coordinator.get_filter_result(pin_id)

    def pending_count(self) -> int:
        """待处理的 AI 任务数"""
        with self._lock:
            return sum(1 for f in self._futures.values() if not f.done())

    @property
    def stats(self) -> dict:
        """工作池统计"""
        return {
            "submitted": self._submitted,
            "completed": self._completed,
            "pending": self.pending_count(),
            "cache_hits": self._cache_hits,
            "api_calls": self._total_api_calls,
            "batch_buffer": len(self._batch_buffer),
        }

    # ═══════════════════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════════════════

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None):
        """关闭工作池

        Args:
            wait: True=等待所有任务完成，False=取消待处理任务
            timeout: 等待超时（秒）
        """
        # 先冲刷批量缓冲区
        self.flush_batch()
        _logger.info(f"[异步AI] 关闭工作池, stats={self.stats}")
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=False)
        return False
