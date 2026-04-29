"""配置管理 - 支持控制台修改Redis配置"""

import os
import json
from pathlib import Path
from typing import Optional
import redis

CONFIG_FILE = Path.home() / ".pinterest_scraper_config.json"
DEFAULT_CONFIG = {
    "redis_host": "localhost",
    "redis_port": 6379,
    "redis_db": 0,
    "redis_password": "",
    "output_dir": str(Path.home() / "PinterestScraper" / "output"),
    "chrome_port": 9222,
    "chrome_headless": False,
    "chrome_profile": "",
    "proxy_host": "127.0.0.1",
    "proxy_port": 7897,
    "proxy_enabled": False,
    # 以下字段用于托盘应用兼容性
    "api_port": 8000,
    "default_query": "",
    "default_max_pins": 100,
    "default_min_saves": 0,
    "default_min_likes": 0,
    "default_min_comments": 0,
    "auto_start": False,
}


def load_config():
    """加载配置文件"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """保存配置文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_redis_client(config: dict):
    """获取Redis客户端"""
    try:
        return redis.Redis(
            host=config["redis_host"],
            port=config["redis_port"],
            db=config["redis_db"],
            password=config["redis_password"] or None,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    except Exception as e:
        print(f"Redis连接失败: {e}")
        return None


def test_redis_connection(config: dict) -> bool:
    """测试Redis连接"""
    client = get_redis_client(config)
    if client is None:
        return False
    try:
        return client.ping()
    except Exception as e:
        print(f"Redis测试失败: {e}")
        return False


def get_config():
    """获取当前配置"""
    return load_config()
