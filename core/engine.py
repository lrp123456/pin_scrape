"""爬虫引擎 - 插件调度与任务管理

核心职责:
  1. 插件注册与发现
  2. 任务调度与执行
  3. 进度追踪
  4. Cookie 分配
"""

import importlib
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from core.plugin_interface import ScraperPlugin, PipelinePlugin, ScrapeResult, TaskStatus
from core.browser_manager import BrowserManager
from core.config import ConfigManager

logger = logging.getLogger(__name__)

PLUGIN_REGISTRY: Dict[str, Type[ScraperPlugin]] = {}


def register_plugin(name: str, plugin_cls: Type[ScraperPlugin]) -> None:
    """注册插件类"""
    PLUGIN_REGISTRY[name] = plugin_cls
    logger.info(f"已注册插件: {name} ({plugin_cls.info().description})")


def discover_plugins() -> None:
    """自动发现并注册 plugins/ 目录下的插件"""
    plugins_dir = Path(__file__).parent.parent / "plugins"
    if not plugins_dir.exists():
        return

    for plugin_dir in plugins_dir.iterdir():
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("_"):
            continue
        init_file = plugin_dir / "__init__.py"
        if not init_file.exists():
            continue
        try:
            module = importlib.import_module(f"plugins.{plugin_dir.name}")
            if hasattr(module, "register"):
                module.register()
        except Exception as e:
            logger.warning(f"加载插件 {plugin_dir.name} 失败: {e}")


def get_plugin(name: str) -> Optional[Type[ScraperPlugin]]:
    """获取已注册的插件类"""
    return PLUGIN_REGISTRY.get(name)


def list_plugins() -> List[str]:
    """列出所有已注册的插件名"""
    return list(PLUGIN_REGISTRY.keys())


class ScraperEngine:
    """爬虫引擎

    统一管理插件实例、浏览器和任务执行。
    """

    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or ConfigManager()
        self._instances: Dict[str, ScraperPlugin] = {}
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_plugin(self, name: str, **kwargs) -> ScraperPlugin:
        """创建插件实例"""
        plugin_cls = get_plugin(name)
        if not plugin_cls:
            raise ValueError(f"未注册的插件: {name}，可用插件: {list_plugins()}")

        section_config = self.config.get_section(name)
        section_config.update(kwargs)

        if not plugin_cls.validate_config(section_config):
            raise ValueError(f"插件 {name} 配置无效")

        instance = plugin_cls(**section_config)
        self._instances[name] = instance
        return instance

    def run_task(self, plugin_name: str, task_config: Dict[str, Any],
                 progress_callback: Optional[Callable] = None) -> ScrapeResult:
        """执行爬取任务

        Args:
            plugin_name: 插件名称
            task_config: 任务配置
            progress_callback: 进度回调

        Returns:
            爬取结果
        """
        instance = self._instances.get(plugin_name)
        if not instance:
            instance = self.create_plugin(plugin_name)

        task_id = f"{plugin_name}_{id(task_config)}"
        with self._lock:
            self._tasks[task_id] = {
                "plugin": plugin_name,
                "config": task_config,
                "status": TaskStatus.RUNNING,
            }

        try:
            instance.start()
            result = instance.run(task_config, progress_callback)
            with self._lock:
                self._tasks[task_id]["status"] = result.status
            return result
        except Exception as e:
            logger.error(f"任务执行失败 [{plugin_name}]: {e}")
            with self._lock:
                self._tasks[task_id]["status"] = TaskStatus.FAILED
            return ScrapeResult(status=TaskStatus.FAILED, error=str(e))
        finally:
            instance.stop()

    def cancel_task(self, plugin_name: str) -> None:
        """取消任务"""
        instance = self._instances.get(plugin_name)
        if instance:
            instance.cancel()

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    def shutdown(self) -> None:
        """关闭引擎，释放所有资源"""
        for name, instance in self._instances.items():
            try:
                instance.stop()
            except Exception:
                pass
        self._instances.clear()
        logger.info("引擎已关闭")
