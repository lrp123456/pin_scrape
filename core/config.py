"""统一配置管理器

集中管理所有插件的配置，支持:
  - 默认配置
  - 配置文件覆盖
  - 环境变量覆盖
  - 运行时动态修改
"""

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "conf"


class ConfigManager:
    """统一配置管理器"""

    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config = self._load_defaults()
        self._load_config_files()
        self._load_env_overrides()

    def _load_defaults(self) -> Dict[str, Any]:
        return {
            "pinterest": {
                "max_pins": 100,
                "min_saves": 0,
                "climb_mode": False,
                "batch_size": 10,
                "ai_filter": True,
                "ai_provider": "ollama",
                "download_images": True,
                "headless": True,
                "debug": False,
                "workers": 1,
            },
            "tianjin": {
                "days_limit": 30,
                "max_gov_pages": 5,
                "max_projects": 0,
                "sources": ["3vjia", "kujiale"],
                "headless": True,
                "debug": False,
            },
            "browser": {
                "cdp_port": 9222,
                "chrome_profile": "",
                "auto_launch": False,
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
            "api": {
                "host": "0.0.0.0",
                "port": 8000,
            },
        }

    def _load_config_files(self) -> None:
        config_file = CONFIG_DIR / "config.json"
        if config_file.exists():
            try:
                user_config = json.loads(config_file.read_text(encoding="utf-8"))
                self._deep_merge(self._config, user_config)
                logger.info(f"已加载配置文件: {config_file}")
            except Exception as e:
                logger.warning(f"加载配置文件失败: {e}")

    def _load_env_overrides(self) -> None:
        env_map = {
            "PINTEREST_MAX_PINS": ("pinterest", "max_pins", int),
            "PINTEREST_MIN_SAVES": ("pinterest", "min_saves", int),
            "PINTEREST_WORKERS": ("pinterest", "workers", int),
            "PINTEREST_AI_PROVIDER": ("pinterest", "ai_provider", str),
            "BROWSER_CDP_PORT": ("browser", "cdp_port", int),
            "BROWSER_HEADLESS": ("browser", "headless", lambda x: x.lower() == "true"),
            "API_PORT": ("api", "port", int),
        }
        for env_key, (section, key, converter) in env_map.items():
            value = os.getenv(env_key)
            if value is not None:
                try:
                    self._config[section][key] = converter(value)
                except Exception:
                    pass

    @staticmethod
    def _deep_merge(base: Dict, override: Dict) -> Dict:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self._config.get(section, {}).get(key, default)

    def get_section(self, section: str) -> Dict[str, Any]:
        return deepcopy(self._config.get(section, {}))

    def set(self, section: str, key: str, value: Any) -> None:
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value

    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        if section not in self._config:
            self._config[section] = {}
        self._config[section].update(values)

    @property
    def all_config(self) -> Dict[str, Any]:
        return deepcopy(self._config)

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config_file = CONFIG_DIR / "config.json"
        config_file.write_text(
            json.dumps(self._config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"配置已保存到: {config_file}")
