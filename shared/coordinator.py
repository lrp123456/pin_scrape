# -*- coding: utf-8 -*-
"""Redis 协调器 - 多 Worker 共享状态管理

Key 命名规范: ps:{query}:{purpose}

提供多 Worker 之间的：
- 收集去重（collected Set）
- AI 筛选缓存（filter Hash→String，结果复用）
- 入口队列（entry_q List，原子分配）
- 分配锁（assigned Set，防并发处理）
- 待爬坡队列（pending_climb List）
- Saves 排行榜（saves Sorted Set）
- Worker 心跳（workers Hash）
"""

import json
import logging
import threading
import time
from typing import Optional, Dict, List, Set, Tuple

from shared.models import get_redis_client

_logger = logging.getLogger("pinterest_scraper.coordinator")

# ── 全局单例缓存 ──
_coordinator_cache: Dict[str, "ScrapeCoordinator"] = {}
_cache_lock = threading.Lock()


def get_coordinator(query: str, worker_id: str = "worker-0") -> "ScrapeCoordinator":
    """获取或创建协调器实例（按 query+worker_id 缓存单例）"""
    cache_key = f"{query}:{worker_id}"
    with _cache_lock:
        if cache_key not in _coordinator_cache:
            _coordinator_cache[cache_key] = ScrapeCoordinator(query, worker_id)
        return _coordinator_cache[cache_key]


class ScrapeCoordinator:
    """爬虫协调器 - 管理多 Worker 共享状态"""

    def __init__(self, query: str, worker_id: str = "worker-0"):
        """
        Args:
            query: 搜索关键词，用于区分不同任务
            worker_id: Worker 标识，用于心跳和日志
        """
        self.query = query
        self.worker_id = worker_id
        self._client = None
        self._redis_available = False

        # ── 内存 fallback 存储（Redis 不可用时使用）──
        self._memory_collected: Set[str] = set()
        self._memory_filter_cache: Dict[str, dict] = {}
        self._memory_assigned: Set[str] = set()
        self._memory_entry_queue: List[str] = []
        self._memory_pending_climb: List[dict] = []
        self._memory_saves: Dict[str, int] = {}
        self._lock = threading.Lock()

        # 尝试连接 Redis
        client = get_redis_client()
        if client is not None:
            try:
                client.ping()
                self._client = client
                self._redis_available = True
                _logger.info(f"[协调器] Worker={worker_id} 查询={query} Redis 连接成功")
            except Exception as e:
                _logger.warning(f"[协调器] Redis 连接失败，使用内存模式: {e}")
        else:
            _logger.warning("[协调器] Redis 未配置，使用内存模式（仅单 Worker）")

    # ═══════════════════════════════════════════════════════════════
    # Key 生成
    # ═══════════════════════════════════════════════════════════════

    def _k(self, purpose: str) -> str:
        """生成 query 命名空间下的 Redis key"""
        return f"ps:{self.query}:{purpose}"

    # ═══════════════════════════════════════════════════════════════
    # 收集状态
    # ═══════════════════════════════════════════════════════════════

    def is_collected(self, pin_id: str) -> bool:
        """检查 pin 是否已被任何 Worker 收集"""
        if self._redis_available:
            try:
                return bool(self._client.sismember(self._k("collected"), pin_id))
            except Exception as e:
                _logger.debug(f"[协调器] is_collected 异常: {e}")
        with self._lock:
            return pin_id in self._memory_collected

    def mark_collected(self, pin_id: str, saves: int = 0, title: str = "") -> bool:
        """标记 pin 为已收集，返回是否为新收集（False=已存在）。

        Args:
            pin_id: Pin ID
            saves: saves 数量（用于全局排行榜）
            title: pin 标题（可选记录）
        """
        result = False
        if self._redis_available:
            try:
                result = bool(self._client.sadd(self._k("collected"), pin_id))
                if result and saves > 0:
                    self._client.zadd(self._k("saves"), {pin_id: saves})
            except Exception as e:
                _logger.debug(f"[协调器] mark_collected 异常: {e}")
        with self._lock:
            if pin_id not in self._memory_collected:
                self._memory_collected.add(pin_id)
                if saves > 0:
                    self._memory_saves[pin_id] = saves
                result = True
        return result

    def collected_count(self) -> int:
        """已收集 pin 总数"""
        if self._redis_available:
            try:
                return self._client.scard(self._k("collected"))
            except Exception:
                pass
        return len(self._memory_collected)

    # ═══════════════════════════════════════════════════════════════
    # AI 筛选缓存（结果复用，避免重复 AI 调用）
    # ═══════════════════════════════════════════════════════════════

    def get_filter_result(self, pin_id: str) -> Optional[dict]:
        """获取已缓存的 AI 筛选结果"""
        if self._redis_available:
            try:
                data = self._client.get(self._k(f"filter:{pin_id}"))
                if data:
                    return json.loads(data)
            except Exception:
                pass
        with self._lock:
            return self._memory_filter_cache.get(pin_id)

    def set_filter_result(self, pin_id: str, result: dict):
        """缓存 AI 筛选结果（24 小时过期）"""
        if self._redis_available:
            try:
                self._client.set(
                    self._k(f"filter:{pin_id}"),
                    json.dumps(result, ensure_ascii=False),
                    ex=86400,  # 24 小时后自动清理
                )
            except Exception:
                pass
        with self._lock:
            self._memory_filter_cache[pin_id] = result

    # ═══════════════════════════════════════════════════════════════
    # 入口队列（原子分配，防并发）
    # ═══════════════════════════════════════════════════════════════

    def push_entry_pin(self, pin_id: str):
        """推入单个入口 pin"""
        self.push_entry_pins([pin_id])

    def push_entry_pins(self, pin_ids: List[str]):
        """推入搜索页发现的入口 pin 到队列"""
        if not pin_ids:
            return
        if self._redis_available:
            try:
                self._client.rpush(self._k("entry_q"), *pin_ids)
                _logger.debug(f"[协调器] 推入 {len(pin_ids)} 个入口 pin")
            except Exception as e:
                _logger.warning(f"[协调器] push_entry_pins 异常: {e}")
                with self._lock:
                    self._memory_entry_queue.extend(pin_ids)
        else:
            with self._lock:
                self._memory_entry_queue.extend(pin_ids)

    def pop_entry_pin(self) -> Optional[str]:
        """原子取出一个入口 pin（LPOP，多 Worker 竞争安全）"""
        if self._redis_available:
            try:
                result = self._client.lpop(self._k("entry_q"))
                if result:
                    return result
            except Exception as e:
                _logger.warning(f"[协调器] pop_entry_pin 异常: {e}")
        with self._lock:
            if self._memory_entry_queue:
                return self._memory_entry_queue.pop(0)
        return None

    def entry_queue_size(self) -> int:
        """入口队列剩余数量"""
        if self._redis_available:
            try:
                return self._client.llen(self._k("entry_q"))
            except Exception:
                pass
        return len(self._memory_entry_queue)

    # ═══════════════════════════════════════════════════════════════
    # 分配锁（防止两个 Worker 同时处理同一 pin）
    # ═══════════════════════════════════════════════════════════════

    def try_assign(self, pin_id: str) -> bool:
        """尝试独占分配 pin（SADD 原子操作）"""
        if self._redis_available:
            try:
                acquired = bool(self._client.sadd(self._k("assigned"), pin_id))
                if acquired:
                    _logger.debug(f"[协调器] 获得分配: {pin_id[:12]}... → {self.worker_id}")
                return acquired
            except Exception as e:
                _logger.warning(f"[协调器] try_assign 异常: {e}")
        with self._lock:
            if pin_id in self._memory_assigned:
                return False
            self._memory_assigned.add(pin_id)
            return True

    def release_assign(self, pin_id: str):
        """释放分配锁"""
        if self._redis_available:
            try:
                self._client.srem(self._k("assigned"), pin_id)
            except Exception:
                pass
        with self._lock:
            self._memory_assigned.discard(pin_id)

    def clear_assigned(self):
        """清除所有分配锁（任务结束/异常恢复）"""
        if self._redis_available:
            try:
                self._client.delete(self._k("assigned"))
            except Exception:
                pass
        with self._lock:
            self._memory_assigned.clear()

    # ═══════════════════════════════════════════════════════════════
    # 待爬坡队列
    # ═══════════════════════════════════════════════════════════════

    def push_pending_climb(self, pin_data: dict):
        """推入待爬坡 pin（AI 通过 + saves 达标的入口）"""
        if self._redis_available:
            try:
                self._client.rpush(self._k("pending_climb"), json.dumps(pin_data, ensure_ascii=False))
            except Exception:
                pass
        with self._lock:
            self._memory_pending_climb.append(pin_data)

    def pop_pending_climb(self) -> Optional[dict]:
        """取出待爬坡 pin"""
        if self._redis_available:
            try:
                data = self._client.lpop(self._k("pending_climb"))
                if data:
                    return json.loads(data)
            except Exception:
                pass
        with self._lock:
            if self._memory_pending_climb:
                return self._memory_pending_climb.pop(0)
        return None

    # ═══════════════════════════════════════════════════════════════
    # Saves 排行榜
    # ═══════════════════════════════════════════════════════════════

    def update_saves(self, pin_id: str, saves: int):
        """更新 pin 的 saves 数"""
        if self._redis_available:
            try:
                self._client.zadd(self._k("saves"), {pin_id: saves})
            except Exception:
                pass
        with self._lock:
            self._memory_saves[pin_id] = saves

    def get_top_saves(self, count: int = 10) -> List[Tuple[str, int]]:
        """获取 saves 最高的 N 个 pin 及其分数"""
        if self._redis_available:
            try:
                return self._client.zrevrange(self._k("saves"), 0, count - 1, withscores=True)
            except Exception:
                pass
        with self._lock:
            sorted_pins = sorted(self._memory_saves.items(), key=lambda x: x[1], reverse=True)
            return [(pid, s) for pid, s in sorted_pins[:count]]

    def total_saves(self) -> int:
        """排行榜中的 pin 总数"""
        if self._redis_available:
            try:
                return self._client.zcard(self._k("saves"))
            except Exception:
                pass
        return len(self._memory_saves)

    # ═══════════════════════════════════════════════════════════════
    # Worker 心跳
    # ═══════════════════════════════════════════════════════════════

    def heartbeat(self):
        """更新 Worker 心跳"""
        if self._redis_available:
            try:
                self._client.hset(
                    self._k("workers"),
                    self.worker_id,
                    time.time(),
                )
            except Exception:
                pass

    def get_active_workers(self) -> List[str]:
        """获取近期有活动的 Worker 列表"""
        now = time.time()
        active = []
        if self._redis_available:
            try:
                all_workers = self._client.hgetall(self._k("workers"))
                for wid, ts in all_workers.items():
                    if now - float(ts) < 60:  # 60 秒内有心跳
                        active.append(wid)
            except Exception:
                pass
        return active

    # ═══════════════════════════════════════════════════════════════
    # 任务终止广播（一个 Worker 达标后通知所有 Worker 停止）
    # ═══════════════════════════════════════════════════════════════

    def set_task_complete(self, target_count: int = 0):
        """标记任务已完成（由第一个达标的 Worker 调用）。
        所有 Worker 定期检查此标记，发现后应立即停止。

        Args:
            target_count: 已收集的达标数量
        """
        data = json.dumps({"time": time.time(), "completed_by": self.worker_id, "count": target_count})
        if self._redis_available:
            try:
                self._client.set(self._k("task_complete"), data, ex=1800)  # 30分钟过期，防止跨次残留
                _logger.info(f"[协调器] 任务完成标记已设置: Worker={self.worker_id}, 收集={target_count}")
            except Exception as e:
                _logger.warning(f"[协调器] set_task_complete 异常: {e}")
        with self._lock:
            self._memory_filter_cache["__task_complete__"] = {"complete": True, "data": data}

    def is_task_complete(self) -> bool:
        """检查是否有 Worker 已标记任务完成。
        每个 Worker 应定期调用此方法，返回 True 时立即停止。
        """
        if self._redis_available:
            try:
                return bool(self._client.exists(self._k("task_complete")))
            except Exception:
                pass
        with self._lock:
            return "__task_complete__" in self._memory_filter_cache

    def get_task_complete_info(self) -> Optional[dict]:
        """获取任务完成信息（哪个 Worker 完成的，何时完成等）"""
        if self._redis_available:
            try:
                data = self._client.get(self._k("task_complete"))
                if data:
                    return json.loads(data)
            except Exception:
                pass
        with self._lock:
            cached = self._memory_filter_cache.get("__task_complete__", {})
            return cached.get("data") if cached else None

    def clear_task_complete(self):
        """清除任务完成标记（新搜索开始时调用）"""
        try:
            key = self._k("task_complete")
            if self._client:
                self._client.delete(key)
            self._memory_filter_cache.pop("__task_complete__", None)
            _logger.info(f"[协调器] 已清除任务终止标记 for {self.query}")
        except Exception as e:
            _logger.warning(f"[协调器] clear_task_complete 异常: {e}")

    # ═══════════════════════════════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        """获取完整统计"""
        return {
            "query": self.query,
            "worker_id": self.worker_id,
            "redis_available": self._redis_available,
            "collected_count": self.collected_count(),
            "entry_queue_size": self.entry_queue_size(),
            "saves_tracked": self.total_saves(),
            "active_workers": self.get_active_workers(),
            "top_saves": [{"pin_id": pid[:16], "saves": s} for pid, s in self.get_top_saves(5)],
        }

    def cleanup_query(self):
        """清理当前查询的所有 Redis key（谨慎使用）"""
        if self._redis_available:
            try:
                keys_to_delete = [
                    self._k("collected"),
                    self._k("assigned"),
                    self._k("entry_q"),
                    self._k("pending_climb"),
                    self._k("saves"),
                    self._k("workers"),
                    self._k("task_complete"),
                ]
                # 清理 filter 缓存 keys
                pattern = self._k("filter:*")
                filter_keys = self._client.keys(pattern)
                keys_to_delete.extend(filter_keys)

                if keys_to_delete:
                    self._client.delete(*keys_to_delete)
                _logger.info(f"[协调器] 已清理查询 '{self.query}' 的所有数据")
            except Exception as e:
                _logger.warning(f"[协调器] 清理失败: {e}")
