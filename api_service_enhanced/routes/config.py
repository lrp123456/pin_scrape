"""配置管理路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
from pathlib import Path
import redis

router = APIRouter()

# 配置文件路径
CONFIG_FILE = Path.home() / 'AppData' / 'Roaming' / 'PinterestScraper' / 'config.json'


class ConfigUpdate(BaseModel):
    """配置更新请求"""
    api_port: Optional[int] = None
    output_dir: Optional[str] = None
    chrome_port: Optional[int] = None
    chrome_headless: Optional[bool] = None
    chrome_profile: Optional[str] = None
    default_query: Optional[str] = None
    default_max_pins: Optional[int] = None
    default_min_saves: Optional[int] = None
    default_min_likes: Optional[int] = None
    default_min_comments: Optional[int] = None
    auto_start: Optional[bool] = None
    redis_host: Optional[str] = None
    redis_port: Optional[int] = None
    redis_db: Optional[int] = None
    redis_password: Optional[str] = "u8QMIvCwvFZ7rtCOfWvmKI7uXCxFiwf5"


def load_config() -> dict:
    """加载配置"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    """保存配置"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


@router.get("/config")
async def get_config():
    """获取当前配置

    Returns:
        配置信息
    """
    config = load_config()
    return config


@router.post("/config")
async def update_config(req: ConfigUpdate):
    """更新配置

    Args:
        req: 配置更新请求

    Returns:
        更新后的配置
    """
    # 加载现有配置
    config = load_config()

    # 更新非None的字段
    update_data = req.model_dump(exclude_none=True)
    config.update(update_data)

    # 保存配置
    save_config(config)

    return config


@router.post("/config/reset")
async def reset_config():
    """重置配置为默认值

    Returns:
        默认配置
    """
    default_config = {
        'api_port': 8000,
        'output_dir': str(Path.home() / 'PinterestScraper' / 'output'),
        'chrome_port': 9222,
        'chrome_headless': False,
        'chrome_profile': '',
        'default_query': '',
        'default_max_pins': 100,
        'default_min_saves': 0,
        'default_min_likes': 0,
        'default_min_comments': 0,
        'auto_start': False,
        'redis_host': 'localhost',
        'redis_port': 6379,
        'redis_db': 0,
        'redis_password': 'u8QMIvCwvFZ7rtCOfWvmKI7uXCxFiwf5'
    }

    save_config(default_config)

    return default_config

@router.post("/config/test-redis")
async def test_redis_connection():
    """测试 Redis 连接

    Returns:
        测试结果
    """
    config = load_config()
    
    redis_host = config.get('redis_host', 'localhost')
    redis_port = config.get('redis_port', 6379)
    redis_db = config.get('redis_db', 0)
    redis_password = config.get('redis_password', '') or None
    
    try:
        # 尝试连接 Redis
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            socket_timeout=5,
            decode_responses=True
        )
        
        # 执行 PING 测试
        result = r.ping()
        
        # 获取一些基本信息
        info = r.info('server')
        
        return {
            "success": True,
            "message": "Redis 连接成功",
            "details": {
                "host": redis_host,
                "port": redis_port,
                "db": redis_db,
                "redis_version": info.get('redis_version', 'unknown'),
                "connected_clients": info.get('connected_clients', 'unknown')
            }
        }
        
    except redis.ConnectionError as e:
        return {
            "success": False,
            "message": f"Redis 连接失败：无法连接到 {redis_host}:{redis_port}",
            "error": str(e)
        }
    except redis.AuthenticationError as e:
        return {
            "success": False,
            "message": "Redis 认证失败：密码错误",
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Redis 测试出错：{str(e)}",
            "error": str(e)
        }
