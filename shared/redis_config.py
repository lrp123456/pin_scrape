"""Redis 配置管理模块"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

_redis_cfg_logger = logging.getLogger("pinterest_scraper.redis_config")


class RedisConfig:
    DEFAULT_CONFIG = {
        "enabled": False,
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "password": None,
        "decode_responses": True,
        "socket_timeout": 5,
        "socket_connect_timeout": 5,
        "retry_on_timeout": True,
        "max_connections": 10,
    }

    def __init__(self, config_file: str = "redis_config.json"):
        self.config_file = self._resolve_config_path(config_file)
        self.config = self._load_config()

    def _resolve_config_path(self, config_file: str) -> Path:
        """解析配置文件路径（支持打包环境和开发环境）"""
        if os.path.isabs(config_file):
            return Path(config_file)
        
        if getattr(sys, 'frozen', False):
            # 打包环境：优先查找 exe 所在目录
            exe_dir = Path(sys.executable).parent
            external_config = exe_dir / config_file
            
            # 如果外部存在配置文件，使用外部的（允许用户自定义）
            if external_config.exists():
                return external_config
            
            # 其次查找当前工作目录
            cwd_config = Path(os.getcwd()) / config_file
            if cwd_config.exists():
                return cwd_config
            
            # 否则使用打包内部的配置（临时解压目录）
            if hasattr(sys, '_MEIPASS'):
                internal_config = Path(sys._MEIPASS) / config_file
                if internal_config.exists():
                    return internal_config
            
            # 默认返回外部路径（会自动创建）
            return external_config
        else:
            # 开发环境：使用项目根目录
            return Path(__file__).parent.parent / config_file

    def _load_config(self) -> dict:
        _redis_cfg_logger.debug(f"[Redis配置] 尝试加载: {self.config_file.absolute()}")
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    config = {k: v for k, v in data.items() if k in self.DEFAULT_CONFIG}
                    merged = {**self.DEFAULT_CONFIG, **config}
                    _redis_cfg_logger.info(f"[Redis配置] 加载成功: enabled={merged.get('enabled')}, host={merged.get('host')}")
                    return merged
            except Exception as e:
                _redis_cfg_logger.warning(f"[Redis配置] 加载配置文件失败: {e}，使用默认配置")
                return self.DEFAULT_CONFIG.copy()
        else:
            _redis_cfg_logger.info(f"[Redis配置] 配置文件不存在: {self.config_file.absolute()}，使用默认配置")
            return self.DEFAULT_CONFIG.copy()

    def save_config(self):
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            _redis_cfg_logger.info(f"[Redis配置] 配置已保存到: {self.config_file.absolute()}")
        except Exception as e:
            _redis_cfg_logger.warning(f"[Redis配置] 保存配置失败: {e}")

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", False)

    @property
    def host(self) -> str:
        return self.config.get("host", "localhost")

    @property
    def port(self) -> int:
        return self.config.get("port", 6379)

    @property
    def db(self) -> int:
        return self.config.get("db", 0)

    @property
    def password(self) -> Optional[str]:
        return self.config.get("password")

    def get_connection_params(self) -> dict:
        params = {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "decode_responses": self.config.get("decode_responses", True),
            "socket_timeout": self.config.get("socket_timeout", 5),
            "socket_connect_timeout": self.config.get("socket_connect_timeout", 5),
            "retry_on_timeout": self.config.get("retry_on_timeout", True),
            "max_connections": self.config.get("max_connections", 10),
        }
        if self.password:
            params["password"] = self.password
        return params

    def test_connection(self) -> bool:
        if not self.enabled:
            _redis_cfg_logger.warning("[Redis配置] Redis 未启用")
            return False

        try:
            import redis
            client = redis.Redis(**self.get_connection_params())
            client.ping()
            _redis_cfg_logger.info(f"[Redis配置] 连接成功: {self.host}:{self.port}/{self.db}")
            return True
        except ImportError:
            _redis_cfg_logger.warning("[Redis配置] redis 模块未安装，请运行: pip install redis")
            return False
        except Exception as e:
            _redis_cfg_logger.warning(f"[Redis配置] 连接失败: {e}")
            return False

    def get_config_file_path(self) -> str:
        return str(self.config_file.absolute())

    def __str__(self):
        return f"RedisConfig(enabled={self.enabled}, host={self.host}, port={self.port}, db={self.db}, file={self.config_file.absolute()})"


_global_config: Optional[RedisConfig] = None


def get_redis_config(config_file: str = "redis_config.json") -> RedisConfig:
    global _global_config
    if _global_config is None:
        _global_config = RedisConfig(config_file)
    return _global_config


def reload_redis_config(config_file: str = "redis_config.json"):
    global _global_config
    _global_config = RedisConfig(config_file)
    return _global_config
