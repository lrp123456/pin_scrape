"""进度状态定义"""

from enum import Enum
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, asdict


class Stage(str, Enum):
    """进度阶段枚举"""

    IDLE = "idle"
    INITIALIZING = "initializing"
    STARTING_CHROME = "starting_chrome"
    SEARCHING = "searching"
    COLLECTING = "collecting"
    ENRICHING = "enriching"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ProgressState:
    """进度状态数据类"""

    running: bool = False
    stage: str = Stage.IDLE.value
    percentage: int = 0
    current: int = 0
    total: int = 0
    query: str = ""
    message: str = ""
    start_time: Optional[str] = None
    error: Optional[str] = None
    output_dir: str = ""
    collected_count: int = 0

    def to_dict(self):
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建"""
        return cls(**data)
