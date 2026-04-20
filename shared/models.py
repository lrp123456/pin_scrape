"""Pinterest Pin 数据模型"""

import json
import os
from dataclasses import dataclass, asdict
from typing import Optional, List, Set
import redis

# Redis 连接配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
PIN_ID_SET_KEY = "pinterest:collected_pin_ids"

# 内存去重集合（Redis 不可用时的备用方案）
_in_memory_collected_ids: Set[str] = set()


def get_redis_client():
    """获取 Redis 客户端"""
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # 测试连接是否成功
        client.ping()
        return client
    except Exception as e:
        print(f"⚠️  Redis 连接失败：{e}")
        print(f"   将使用内存去重模式（重启后会重置）")
        return None


@dataclass
class Pin:
    """Pinterest Pin 数据模型"""

    id: str
    title: str
    description: str
    image_url: str
    image_url_736x: str
    saves: int
    likes: int  # 点赞数
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
        """检查 pin_id 是否已被收集"""
        redis_client = get_redis_client()
        if redis_client is None:
            # Redis 不可用，使用内存去重
            return pin_id in _in_memory_collected_ids
        return redis_client.sismember(PIN_ID_SET_KEY, pin_id)

    @classmethod
    def mark_as_collected(cls, pin_id: str) -> bool:
        """标记 pin_id 为已收集"""
        redis_client = get_redis_client()
        if redis_client is None:
            # Redis 不可用，使用内存去重
            if pin_id in _in_memory_collected_ids:
                return False
            _in_memory_collected_ids.add(pin_id)
            return True
        return redis_client.sadd(PIN_ID_SET_KEY, pin_id) > 0

    @classmethod
    def get_collected_count(cls) -> int:
        """获取已收集的 pin 数量"""
        redis_client = get_redis_client()
        if redis_client is None:
            return len(_in_memory_collected_ids)
        return redis_client.scard(PIN_ID_SET_KEY)

    @classmethod
    def clear_collected(cls) -> bool:
        """清除所有已收集记录"""
        redis_client = get_redis_client()
        if redis_client is None:
            _in_memory_collected_ids.clear()
            return True
        redis_client.delete(PIN_ID_SET_KEY)
        return True

    def meets_criteria(
        self, min_saves: int = 0, min_likes: int = 0, min_comments: int = 0
    ) -> bool:
        """检查是否满足筛选条件"""
        return (
            self.saves >= min_saves
            and self.likes >= min_likes
            and self.comments >= min_comments
        )
