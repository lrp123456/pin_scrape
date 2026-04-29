"""Pinterest Pin 数据模型"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Optional, List, Set
from pathlib import Path
import redis

_redis_logger = logging.getLogger("pinterest_scraper.redis")

PIN_ID_SET_KEY = "pinterest:collected_pin_ids"

# 内存去重集合（程序启动时从Redis加载，后续只与内存对比）
_in_memory_collected_ids: Set[str] = set()

# Redis连接单例（避免重复创建）
_redis_client: redis.Redis = None


def _get_redis_config():
    try:
        from shared.redis_config import get_redis_config
        redis_cfg = get_redis_config()
        if not redis_cfg.enabled:
            _redis_logger.warning("[Redis] 未启用，使用内存去重模式")
            return None
        return redis_cfg.get_connection_params()
    except Exception as e:
        _redis_logger.warning(f"[Redis] 加载配置失败: {e}，使用内存模式")
        return None


def get_redis_client(config_dict=None):
    """获取 Redis 客户端（单例）

    Args:
        config_dict: 可选的配置字典，包含 redis_host, redis_port, redis_db, redis_password
                    如果为 None，则从配置文件加载默认配置
    """
    global _redis_client

    # 如果提供了配置字典，创建临时客户端（不使用单例缓存）
    if config_dict is not None:
        try:
            client = redis.Redis(
                host=config_dict.get("redis_host", "localhost"),
                port=config_dict.get("redis_port", 6379),
                db=config_dict.get("redis_db", 0),
                password=config_dict.get("redis_password") or None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            client.ping()
            return client
        except Exception as e:
            _redis_logger.warning(f"[Redis] 连接失败: {e}")
            return None

    if _redis_client is not None:
        return _redis_client
    
    try:
        config = _get_redis_config()
        if config is None:
            _redis_logger.warning("[Redis] 未启用，使用内存去重模式")
            return None

        _redis_client = redis.Redis(**config)
        _redis_client.ping()
        _redis_logger.info(f"[Redis] 连接成功: {config.get('host')}:{config.get('port')}/{config.get('db')}")
        return _redis_client
    except Exception as e:
        _redis_logger.warning(f"[Redis] 连接失败: {e}，将使用内存去重模式（重启后会重置）")
        _redis_client = None
        return None


def init_collected_ids_from_redis():
    """从Redis加载已收集的ID到内存（程序启动时调用一次）"""
    global _in_memory_collected_ids
    client = get_redis_client()
    if client is not None:
        try:
            _in_memory_collected_ids = client.smembers(PIN_ID_SET_KEY)
            _redis_logger.info(
                f"[Redis] 已从Redis加载 {len(_in_memory_collected_ids)} 个已收集的Pin ID到内存"
            )
        except Exception as e:
            _redis_logger.warning(f"[Redis] 从Redis加载已收集ID失败: {e}")


@dataclass
class Pin:
    """Pinterest Pin 数据模型"""

    id: str
    title: str
    description: str
    image_url: str
    image_url_736x: str
    saves: int
    comments: int
    link: str
    pinner: str
    source: str = "main"  # "main" 或 "similar_from_{pin_id}"
    is_video: bool = False  # 是否为视频
    video_url: str = ""  # 视频 URL（如果是视频）

    def to_dict(self) -> dict:
        """转换为字典用于 JSON 序列化"""
        return asdict(self)

    @classmethod
    def is_collected(cls, pin_id: str) -> bool:
        """检查 pin_id 是否已被收集（只查内存，极快）"""
        return pin_id in _in_memory_collected_ids

    @classmethod
    def mark_as_collected(cls, pin_id: str) -> bool:
        """标记 pin_id 为已收集（更新内存+异步写Redis）"""
        if pin_id in _in_memory_collected_ids:
            return False
        _in_memory_collected_ids.add(pin_id)
        try:
            client = get_redis_client()
            if client is not None:
                result = client.sadd(PIN_ID_SET_KEY, pin_id)
                if result:
                    _redis_logger.debug(f"[Redis] 已保存 pin {pin_id[:12]}...")
            else:
                _redis_logger.debug(f"[Redis] 未启用，仅内存保存 pin {pin_id[:12]}...")
        except Exception as e:
            _redis_logger.warning(f"[Redis] 保存失败: {e}")
        return True

    @classmethod
    def get_collected_count(cls) -> int:
        """获取已收集的 pin 数量"""
        return len(_in_memory_collected_ids)

    @classmethod
    def clear_collected(cls) -> bool:
        """清除所有已收集记录"""
        _in_memory_collected_ids.clear()
        try:
            client = get_redis_client()
            if client is not None:
                client.delete(PIN_ID_SET_KEY)
        except Exception:
            pass
        return True

    def meets_criteria(
        self, min_saves: int = 0, min_comments: int = 0
    ) -> bool:
        """检查是否满足筛选条件"""
        return (
            self.saves >= min_saves
            and self.comments >= min_comments
        )
