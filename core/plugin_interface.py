"""插件接口定义

所有爬虫插件必须实现 ScraperPlugin 接口。
引擎通过此接口与插件交互，实现解耦。

插件生命周期:
  1. 创建实例 → validate_config()
  2. 启动浏览器 → start()
  3. 执行任务 → run()
  4. 停止 → stop()

插件注册:
  每个插件包需在 __init__.py 中定义 register() 函数，
  返回插件元信息和类引用。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScrapeResult:
    items: List[Dict[str, Any]] = field(default_factory=list)
    total_found: int = 0
    total_collected: int = 0
    output_dir: str = ""
    status: TaskStatus = TaskStatus.COMPLETED
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInfo:
    name: str
    version: str
    description: str
    author: str = ""
    supported_sites: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)


class ScraperPlugin(ABC):
    """爬虫插件接口

    所有爬虫插件必须继承此类并实现所有抽象方法。
    引擎通过此接口统一调度不同网站的爬虫。
    """

    @classmethod
    @abstractmethod
    def info(cls) -> PluginInfo:
        """返回插件元信息"""
        pass

    @classmethod
    @abstractmethod
    def validate_config(cls, config: Dict[str, Any]) -> bool:
        """验证配置是否有效

        Args:
            config: 插件配置字典

        Returns:
            配置是否有效
        """
        pass

    @classmethod
    @abstractmethod
    def default_config(cls) -> Dict[str, Any]:
        """返回默认配置"""
        pass

    @abstractmethod
    def start(self) -> None:
        """启动插件（初始化浏览器等资源）"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """停止插件（释放浏览器等资源）"""
        pass

    @abstractmethod
    def run(self, task_config: Dict[str, Any],
            progress_callback: Optional[Callable] = None) -> ScrapeResult:
        """执行爬取任务

        Args:
            task_config: 任务配置（查询词、数量限制等）
            progress_callback: 进度回调函数 callback(stage, current, total, message)

        Returns:
            爬取结果
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取插件当前状态"""
        pass

    @abstractmethod
    def cancel(self) -> None:
        """取消当前任务"""
        pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


class PipelinePlugin(ScraperPlugin):
    """管道插件接口

    用于多阶段爬取流程（如天津住宅：住建委→房天下→户型图）
    在 ScraperPlugin 基础上增加阶段管理。
    """

    @abstractmethod
    def get_stages(self) -> List[str]:
        """返回管道阶段名称列表"""
        pass

    @abstractmethod
    def run_stage(self, stage_name: str, task_config: Dict[str, Any],
                  progress_callback: Optional[Callable] = None) -> ScrapeResult:
        """执行指定阶段

        Args:
            stage_name: 阶段名称
            task_config: 任务配置
            progress_callback: 进度回调

        Returns:
            阶段执行结果
        """
        pass

    def run(self, task_config: Dict[str, Any],
            progress_callback: Optional[Callable] = None) -> ScrapeResult:
        """按顺序执行所有阶段"""
        all_items = []
        stages = self.get_stages()
        for i, stage in enumerate(stages):
            if progress_callback:
                progress_callback("pipeline", i, len(stages), f"阶段 {i+1}/{len(stages)}: {stage}")
            result = self.run_stage(stage, task_config, progress_callback)
            all_items.extend(result.items)
            if result.status == TaskStatus.FAILED:
                return ScrapeResult(
                    items=all_items,
                    status=TaskStatus.FAILED,
                    error=f"阶段 {stage} 失败: {result.error}",
                )
        return ScrapeResult(
            items=all_items,
            total_collected=len(all_items),
            status=TaskStatus.COMPLETED,
        )
