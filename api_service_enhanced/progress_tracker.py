"""进度追踪模块"""

import json
import threading
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from shared.progress_state import ProgressState


class ProgressTracker:
    """进度追踪器（支持多Worker）"""

    PROGRESS_DIR = Path(os.getenv("TEMP", ".")) / "pinterest_scraper_progress"

    def __init__(self):
        self.lock = threading.Lock()
        self._workers: Dict[str, ProgressState] = {}
        self.PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_all_progress(reset_running=True)

    def _get_progress_file(self, worker_id: str) -> Path:
        return self.PROGRESS_DIR / f"progress_{worker_id}.json"

    def _load_all_progress(self, reset_running=False):
        for f in self.PROGRESS_DIR.glob("progress_worker-*.json"):
            worker_id = f.stem.replace("progress_", "")
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if "output_dir" not in data:
                        data["output_dir"] = ""
                    state = ProgressState.from_dict(data)
                    if reset_running:
                        state.running = False
                        state.stage = "idle"
                    self._workers[worker_id] = state
            except Exception:
                pass

    def _load_progress(self, reset_running=False):
        self._load_all_progress(reset_running)

    def _save_progress(self, worker_id: str = "worker-0"):
        with self.lock:
            state = self._workers.get(worker_id)
            if not state:
                return
            try:
                with open(self._get_progress_file(worker_id), "w", encoding="utf-8") as f:
                    json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"保存进度文件失败: {e}")

    def start_task(self, query: str, total: int, output_dir: str = "", worker_id: str = "worker-0"):
        with self.lock:
            self._workers[worker_id] = ProgressState(
                running=True,
                stage="initializing",
                percentage=0,
                current=0,
                total=total,
                query=query,
                message="初始化中...",
                start_time=datetime.now().isoformat(),
                error=None,
                output_dir=output_dir,
                collected_count=0,
            )
        self._save_progress(worker_id)

    def update(self, stage: str, current: int, total: int, message: str = "", worker_id: str = "worker-0"):
        with self.lock:
            state = self._workers.get(worker_id)
            if not state:
                state = ProgressState()
                self._workers[worker_id] = state
            state.stage = stage
            state.current = current
            state.total = total
            state.percentage = int((current / total * 100) if total > 0 else 0)
            state.message = message
        self._save_progress(worker_id)

    def update_collected(self, count: int, worker_id: str = "worker-0"):
        with self.lock:
            state = self._workers.get(worker_id)
            if state:
                state.collected_count = count
        self._save_progress(worker_id)

    def complete(self, worker_id: str = "worker-0"):
        with self.lock:
            state = self._workers.get(worker_id)
            if state:
                state.running = False
                state.stage = "completed"
                state.percentage = 100
                state.message = "任务完成"
        self._save_progress(worker_id)

    def error(self, error_msg: str, worker_id: str = "worker-0"):
        with self.lock:
            state = self._workers.get(worker_id)
            if state:
                state.running = False
                state.stage = "error"
                state.error = error_msg
                state.message = f"错误: {error_msg}"
        self._save_progress(worker_id)

    def cancel(self, worker_id: str = None):
        with self.lock:
            if worker_id:
                state = self._workers.get(worker_id)
                if state:
                    state.running = False
                    state.stage = "cancelled"
                    state.message = "任务已取消"
                    state.error = None
                self._save_progress(worker_id)
            else:
                for wid, state in self._workers.items():
                    state.running = False
                    state.stage = "cancelled"
                    state.message = "任务已取消"
                    state.error = None
                    self._save_progress(wid)

    def get_progress(self, worker_id: str = None) -> Dict[str, Any]:
        with self.lock:
            if worker_id:
                state = self._workers.get(worker_id)
                if state:
                    return state.to_dict()
                return ProgressState().to_dict()
            all_progress = {}
            for wid, state in self._workers.items():
                all_progress[wid] = state.to_dict()
            return all_progress
