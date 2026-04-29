"""Ollama 配置管理模块"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

_ollama_cfg_logger = logging.getLogger("pinterest_scraper.ollama_config")


class OllamaConfig:
    """Ollama 配置管理"""
    
    DEFAULT_CONFIG = {
        "enabled": True,
        "endpoint": "http://localhost:11434",
        "model": "gemma4:e4b",
        "timeout": 180,
        "fallback_on_error": True,
        "max_retries": 1,
        "zhipu_api_key": "",
        "zhipu_api_url": "https://open.bigmodel.cn/api/paas/v4/",
        "zhipu_model": "glm-4.6v-flash",
        "zhipu_timeout": 30,
        "gitee_api_key": "",
        "gitee_api_url": "https://ai.gitee.com/v1/chat/completions",
        "gitee_model": "GLM-4.6V-Flash",
        "gitee_timeout": 30,
        "siliconflow_api_key": "",
        "siliconflow_api_url": "https://api.siliconflow.cn/v1/chat/completions",
        "siliconflow_model": "Qwen/Qwen3-VL-8B-Instruct",
        "siliconflow_timeout": 60,
        "doubao_api_key": "",
        "doubao_api_url": "https://ark.cn-beijing.volces.com/api/v3",
        "doubao_model": "doubao-seed-2-0-lite-260215",
        "doubao_timeout": 60,
        "ai_provider_priority": ["zhipu_url", "gitee_url", "siliconflow_base64", "doubao_base64", "ollama"],
    }
    
    CONFIG_FILE = "ollama_config.json"
    
    def __init__(self):
        self.config_file = self._resolve_config_path()
        self.config = self._load_config()
    
    def _resolve_config_path(self) -> Path:
        """解析配置文件路径（支持打包环境和开发环境）"""
        if getattr(sys, 'frozen', False):
            # 打包环境：优先查找 exe 所在目录
            exe_dir = Path(sys.executable).parent
            config_path = exe_dir / self.CONFIG_FILE
            if config_path.exists():
                return config_path
            
            # 其次查找当前工作目录
            cwd_config = Path(os.getcwd()) / self.CONFIG_FILE
            if cwd_config.exists():
                return cwd_config
            
            # 默认返回 exe 目录（会自动创建）
            return config_path
        else:
            # 开发环境：使用项目根目录
            return Path(__file__).parent.parent / self.CONFIG_FILE
    
    def _load_config(self) -> dict:
        """加载配置"""
        _ollama_cfg_logger.debug(f"[Ollama配置] 尝试加载: {self.config_file.absolute()}")
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    config = {k: v for k, v in data.items() if k in self.DEFAULT_CONFIG}
                    merged = {**self.DEFAULT_CONFIG, **config}
                    _ollama_cfg_logger.info(f"[Ollama配置] 加载成功: enabled={merged.get('enabled')}, model={merged.get('model')}")
                    return merged
            except Exception as e:
                _ollama_cfg_logger.warning(f"[Ollama配置] 加载失败: {e}，使用默认配置")
                return self.DEFAULT_CONFIG.copy()
        else:
            _ollama_cfg_logger.info(f"[Ollama配置] 配置文件不存在，使用默认配置: enabled=True, model=gemma4:e4b")
            return self.DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """保存配置"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _ollama_cfg_logger.warning(f"[Ollama配置] 保存失败: {e}")
    
    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)
    
    @property
    def endpoint(self) -> str:
        return self.config.get("endpoint", "http://localhost:11434")
    
    @property
    def model(self) -> str:
        return self.config.get("model", "gemma4:e4b")
    
    @property
    def timeout(self) -> int:
        return self.config.get("timeout", 180)
    
    @property
    def fallback_on_error(self) -> bool:
        return self.config.get("fallback_on_error", True)

    @property
    def zhipu_api_key(self) -> str:
        return os.environ.get("ZHIPU_API_KEY") or self.config.get("zhipu_api_key", "")

    @property
    def zhipu_api_url(self) -> str:
        return self.config.get("zhipu_api_url", "https://ai.gitee.com/v1/chat/completions")

    @property
    def zhipu_model(self) -> str:
        return self.config.get("zhipu_model", "glm-4.6v-flash")

    @property
    def zhipu_timeout(self) -> int:
        return self.config.get("zhipu_timeout", 30)

    @property
    def gitee_api_key(self) -> str:
        return os.environ.get("GITEE_API_KEY") or self.config.get("gitee_api_key", "")

    @property
    def gitee_api_url(self) -> str:
        return self.config.get("gitee_api_url", "https://ai.gitee.com/v1/chat/completions")

    @property
    def gitee_model(self) -> str:
        return self.config.get("gitee_model", "GLM-4.6V-Flash")

    @property
    def gitee_timeout(self) -> int:
        return self.config.get("gitee_timeout", 30)

    @property
    def siliconflow_api_key(self) -> str:
        return os.environ.get("SILICONFLOW_API_KEY") or self.config.get("siliconflow_api_key", "")

    @property
    def siliconflow_api_url(self) -> str:
        return self.config.get("siliconflow_api_url", "https://api.siliconflow.cn/v1/chat/completions")

    @property
    def siliconflow_model(self) -> str:
        return self.config.get("siliconflow_model", "Qwen/Qwen3.5-4B")

    @property
    def siliconflow_timeout(self) -> int:
        return self.config.get("siliconflow_timeout", 60)

    @property
    def doubao_api_key(self) -> str:
        """豆包 API Key：优先环境变量 ARK_API_KEY"""
        return os.environ.get("ARK_API_KEY") or self.config.get("doubao_api_key", "")

    @property
    def doubao_api_url(self) -> str:
        return self.config.get("doubao_api_url", "https://ark.cn-beijing.volces.com/api/v3")

    @property
    def doubao_model(self) -> str:
        return self.config.get("doubao_model", "")

    @property
    def doubao_timeout(self) -> int:
        return self.config.get("doubao_timeout", 60)

    @property
    def ai_provider_priority(self) -> list:
        return self.config.get("ai_provider_priority", ["zhipu_url", "gitee_url", "siliconflow_base64", "doubao_base64", "ollama"])


_global_config: Optional[OllamaConfig] = None


def get_ollama_config() -> OllamaConfig:
    global _global_config
    if _global_config is None:
        _global_config = OllamaConfig()
    return _global_config
