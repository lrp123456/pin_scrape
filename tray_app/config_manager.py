"""配置文件管理"""

import json
from pathlib import Path
from typing import Any, Dict
import sys
import winreg


class ConfigManager:
    """配置文件管理器"""

    DEFAULT_CONFIG = {
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
        'custom_icon_path': '',
    }

    def __init__(self, config_path: Path = None):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径，默认为%APPDATA%/PinterestScraper/config.json
        """
        if config_path is None:
            app_data = Path.home() / 'AppData' / 'Roaming'
            config_path = app_data / 'PinterestScraper' / 'config.json'

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """加载配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 合并默认配置
                    return {**self.DEFAULT_CONFIG, **config}
            except Exception as e:
                print(f"加载配置失败: {e}")
                return self.DEFAULT_CONFIG.copy()

        return self.DEFAULT_CONFIG.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """设置配置项"""
        self.config[key] = value
        self._save_config()

    def _save_config(self):
        """保存配置"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def set_autostart(self, enable: bool):
        """设置开机自启

        Args:
            enable: 是否启用
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Run',
                0,
                winreg.KEY_SET_VALUE
            )

            app_name = 'PinterestScraper'
            exe_path = sys.executable  # 当前exe路径

            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass

            winreg.CloseKey(key)

            # 更新配置
            self.set('auto_start', enable)

        except Exception as e:
            print(f"设置开机自启失败: {e}")

    def is_autostart(self) -> bool:
        """检查是否已设置开机自启

        Returns:
            是否已设置
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Run',
                0,
                winreg.KEY_READ
            )

            try:
                value, _ = winreg.QueryValueEx(key, 'PinterestScraper')
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)

        except Exception as e:
            print(f"检查开机自启失败: {e}")
            return False
