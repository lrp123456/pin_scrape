"""配置结构定义"""

import os
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, validator
from shared.config_manager import load_config as load_user_config


class ConfigSchema(BaseModel):
    """配置文件结构"""

    # Redis配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # 主配置
    api_port: int = 8000
    output_dir: str = str(Path.home() / "PinterestScraper" / "output")
    chrome_port: int = 9222
    chrome_headless: bool = False
    chrome_profile: str = ""
    default_query: str = ""
    default_max_pins: int = 100
    default_min_saves: int = 0
    default_min_likes: int = 0
    default_min_comments: int = 0
    auto_start: bool = False
    custom_icon_path: str = ""

    @validator("redis_host", "redis_password", pre=True)
    def load_from_user_config(cls, v, field):
        """从用户配置文件中加载值"""
        if v is None or v == "":
            user_config = load_user_config()
            return user_config.get(field.alias, v)
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "redis_host": "localhost",
                "redis_port": 6379,
                "redis_db": 0,
                "redis_password": None,
                "api_port": 8000,
                "output_dir": "C:\\Users\\王\\PinterestScraper\\output",
                "chrome_port": 9222,
                "chrome_headless": False,
                "chrome_profile": "",
                "default_query": "",
                "default_max_pins": 100,
                "default_min_saves": 0,
                "default_min_likes": 0,
                "default_min_comments": 0,
                "auto_start": False,
                "custom_icon_path": "",
            }
        }
