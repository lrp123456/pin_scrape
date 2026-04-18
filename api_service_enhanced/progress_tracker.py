"""进度追踪模块"""

import json
import threading
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from shared.progress_state import ProgressState


class ProgressTracker:
    """进度追踪器"""

    PROGRESS_FILE = Path(os.getenv("TEMP", ".")) / "pinterest_scraper_progress.json"

    def __init__(self):
        self.lock = threading.Lock()
        self.progress = ProgressState()
        self._load_progress(reset_running=True)

    def _load_progress(self, reset_running=False):
        """从文件加载进度

        Args:
            reset_running: 仅在初始化时为True，清除上次中断的残留状态
        """
        try:
            if self.PROGRESS_FILE.exists():
                with open(self.PROGRESS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.progress = ProgressState.from_dict(data)
                    if reset_running:
                        self.progress.running = False
                        self.progress.stage = "idle"
        except Exception:
            pass

    def _save_progress(self):
        """保存进度到文件"""
        with self.lock:
            try:
                with open(self.PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.progress.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"保存进度文件失败: {e}")

    def start_task(self, query: str, total: int):
        """开始任务"""
        with self.lock:
            self.progress = ProgressState(
                running=True,
                stage="initializing",
                percentage=0,
                current=0,
                total=total,
                query=query,
                message="初始化中...",
                start_time=datetime.now().isoformat(),
                error=None,
            )
        self._save_progress()

    def update(self, stage: str, current: int, total: int, message: str = ""):
        """更新进度"""
        with self.lock:
            self.progress.stage = stage
            self.progress.current = current
            self.progress.total = total
            self.progress.percentage = int((current / total * 100) if total > 0 else 0)
            self.progress.message = message
        self._save_progress()

    def complete(self):
        """完成任务"""
        with self.lock:
            self.progress.running = False
            self.progress.stage = "completed"
            self.progress.percentage = 100
            self.progress.message = "任务完成"
        self._save_progress()

    def error(self, error_msg: str):
        """记录错误"""
        with self.lock:
            self.progress.running = False
            self.progress.stage = "error"
            self.progress.error = error_msg
            self.progress.message = f"错误: {error_msg}"
        self._save_progress()

    def cancel(self):
        """取消任务"""
        with self.lock:
            self.progress.running = False
            self.progress.stage = "cancelled"
            self.progress.message = "任务已取消"
            self.progress.error = None
        self._save_progress()

    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度"""
        with self.lock:
            self._load_progress()
            return self.progress.to_dict()
