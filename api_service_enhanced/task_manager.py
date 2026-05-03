"""任务执行管理"""

import subprocess
import threading
import sys
import os
from pathlib import Path
from typing import Dict, Optional, List
import json

from api_service_enhanced.progress_tracker import ProgressTracker
from api_service_enhanced.chrome_manager import ChromeManager


def load_pins_from_json(filepath: Path) -> List[Dict]:
    """从JSON文件加载pin数据"""
    try:
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("pins", [])
    except Exception as e:
        print(f"[TaskManager] 加载JSON失败: {e}")
        return []


def get_base_path():
    """获取基础路径（兼容开发环境和打包环境）"""
    if getattr(sys, "frozen", False):
        # PyInstaller打包后环境
        return Path(sys._MEIPASS)
    else:
        # 开发环境
        return Path(__file__).parent.parent


class TaskManager:
    """任务执行管理器（支持多Worker并行）"""

    def __init__(
        self, chrome_manager: ChromeManager, progress_tracker: ProgressTracker
    ):
        self.chrome_manager = chrome_manager
        self.progress_tracker = progress_tracker
        self._tasks: Dict[str, subprocess.Popen] = {}
        self._output_dirs: Dict[str, str] = {}
        self.lock = threading.Lock()

    def run_scrape(self, params: Dict) -> Dict:
        """执行爬虫任务

        Args:
            params: 任务参数

        Returns:
            执行结果
        """
        worker_id = params.get("worker_id", "worker-0")

        with self.lock:
            if worker_id in self._tasks and self._tasks[worker_id].poll() is None:
                return {"success": False, "error": f"Worker {worker_id} is already running"}

        chrome_port = params.get("chrome_port", 9222)
        if worker_id and not params.get("chrome_port"):
            try:
                w_idx = int(worker_id.rsplit("-", 1)[-1])
                chrome_port = 9222 + w_idx
            except (ValueError, IndexError):
                pass

        endpoint = self.chrome_manager.get_endpoint(worker_id=worker_id)
        if not endpoint:
            try:
                print(f"[TaskManager][{worker_id}] Chrome未启动，正在启动...")
                endpoint = self.chrome_manager.start_chrome(
                    port=chrome_port,
                    profile=params.get("chrome_profile", ""),
                    headless=params.get("chrome_headless", False),
                    proxy_server=params.get("proxy_server"),
                    worker_id=worker_id,
                )
                print(f"[TaskManager][{worker_id}] Chrome已启动: {endpoint}")
            except Exception as e:
                error_msg = f"Chrome启动失败: {str(e)}"
                print(f"[TaskManager][{worker_id}] {error_msg}")
                return {"success": False, "error": error_msg}

        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(
            c for c in params["query"] if c.isalnum() or c in (" ", "_", "-")
        ).strip()
        safe_query = safe_query.replace(" ", "_")
        task_subdir = f"{safe_query}_{timestamp}"
        base_output = params.get("output_dir", "./output")
        full_output_dir = str(Path(base_output) / task_subdir)

        with self.lock:
            self._output_dirs[worker_id] = full_output_dir

        self.progress_tracker.start_task(
            params["query"], params.get("max_pins", 100), full_output_dir,
            worker_id=worker_id,
        )
        print(
            f"[TaskManager][{worker_id}] 开始任务: {params['query']}, output_dir: {full_output_dir}"
        )

        progress_file = self.progress_tracker._get_progress_file(worker_id)

        env = os.environ.copy()
        env["PROGRESS_FILE"] = str(progress_file)

        cmd = self._build_command(params, endpoint, worker_id)
        print(f"[TaskManager][{worker_id}] 执行命令: {' '.join(cmd)}")

        try:
            with self.lock:
                self._tasks[worker_id] = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
        except Exception as e:
            error_msg = f"启动任务失败: {str(e)}"
            print(f"[TaskManager][{worker_id}] {error_msg}")
            self.progress_tracker.error(error_msg, worker_id=worker_id)
            return {"success": False, "error": error_msg}

        print(f"[TaskManager][{worker_id}] 等待爬虫进程完成...")
        try:
            stdout, stderr = self._tasks[worker_id].communicate(timeout=600)
            return_code = self._tasks[worker_id].returncode

            print(f"[TaskManager][{worker_id}] 进程结束，返回码: {return_code}")
            print(f"[TaskManager][{worker_id}] ===== STDOUT =====")
            print(stdout)
            print(f"[TaskManager][{worker_id}] ===== STDERR =====")
            print(stderr)
            print(f"[TaskManager][{worker_id}] ==================")

            if return_code == 0:
                downloaded_count = 0
                downloaded = None
                pins = []
                if params.get("download_images", True):
                    try:
                        with self.lock:
                            output_dir = Path(
                                self._output_dirs.get(worker_id, params.get("output_dir", "./output"))
                            )
                        qualified_file = output_dir / "qualified_pins.json"
                        data_file = output_dir / "data.json"

                        if qualified_file.exists():
                            pins = load_pins_from_json(qualified_file)
                            print(f"[TaskManager][{worker_id}] 使用达标数据: {len(pins)} 个pins")
                        else:
                            pins = load_pins_from_json(data_file)
                            print(f"[TaskManager][{worker_id}] 使用全部数据: {len(pins)} 个pins")

                        if pins:
                            print(f"[TaskManager][{worker_id}] 开始下载 {len(pins)} 张图片...")
                            self.progress_tracker.update_collected(len(pins), worker_id=worker_id)
                            sys.path.insert(0, str(get_base_path()))
                            from downloader import ImageDownloader
                            from shared.models import Pin

                            query = params.get("query", "")
                            use_folder = params.get("use_folder_structure", False)

                            downloader = ImageDownloader(
                                str(output_dir),
                                query=query,
                                use_folder_structure=use_folder,
                            )
                            pin_objects = [Pin(**p) for p in pins]

                            if params.get("climb_mode"):
                                downloaded = downloader.filter_and_download(
                                    pin_objects,
                                    min_saves=0,
                                    min_comments=0,
                                )
                            else:
                                downloaded = downloader.filter_and_download(
                                    pin_objects,
                                    min_saves=params.get("min_saves", 0),
                                    min_comments=params.get("min_comments", 0),
                                )
                            downloaded_count = len(downloaded)
                            print(
                                f"[TaskManager][{worker_id}] ✓ 图片下载完成: {downloaded_count}/{len(pins)} 张"
                            )
                    except Exception as e:
                        print(f"[TaskManager][{worker_id}] 图片下载失败: {e}")

                self.progress_tracker.complete(worker_id=worker_id)
                print(f"[TaskManager][{worker_id}] ✓ 任务成功完成")
                total_pins = len(pins) if pins else 0
                return {
                    "success": True,
                    "output": stdout,
                    "message": "任务完成",
                    "downloaded_images": downloaded_count,
                    "collected_count": total_pins,
                    "filtered_count": len(downloaded) if downloaded else 0,
                    "worker_id": worker_id,
                }
            else:
                error_msg = stderr[:2000] if stderr else "未知错误"
                print(f"[TaskManager][{worker_id}] ✗ 任务失败: {error_msg}")
                self.progress_tracker.error(error_msg, worker_id=worker_id)
                return {
                    "success": False,
                    "error": error_msg,
                    "return_code": return_code,
                    "worker_id": worker_id,
                }

        except subprocess.TimeoutExpired:
            print(f"[TaskManager][{worker_id}] ✗ 任务超时")
            self._tasks[worker_id].kill()
            self._tasks[worker_id].wait()
            self.progress_tracker.error("任务超时", worker_id=worker_id)
            return {"success": False, "error": "Task timeout after 600s", "worker_id": worker_id}

        except Exception as e:
            error_msg = str(e)
            print(f"[TaskManager][{worker_id}] ✗ 任务异常: {error_msg}")
            self.progress_tracker.error(error_msg, worker_id=worker_id)
            return {"success": False, "error": error_msg, "worker_id": worker_id}

        finally:
            with self.lock:
                self._tasks.pop(worker_id, None)
                self._output_dirs.pop(worker_id, None)
            print(f"[TaskManager][{worker_id}] 任务清理完成")

    def cancel_current(self, worker_id: str = None):
        """取消任务并清理相关进程

        Args:
            worker_id: 指定Worker ID取消，None则取消所有
        """
        import psutil

        with self.lock:
            target_ids = [worker_id] if worker_id else list(self._tasks.keys())
            for wid in target_ids:
                task = self._tasks.get(wid)
                if task and task.poll() is None:
                    pid = task.pid
                    print(f"[TaskManager][{wid}] 正在终止任务进程 (PID: {pid})...")

                    try:
                        parent = psutil.Process(pid)
                        children = parent.children(recursive=True)

                        for child in children:
                            try:
                                child.terminate()
                            except:
                                pass

                        gone, alive = psutil.wait_procs(children, timeout=3)
                        for child in alive:
                            try:
                                child.kill()
                            except:
                                pass

                        parent.terminate()
                        parent.wait(timeout=3)

                    except psutil.NoSuchProcess:
                        pass
                    except Exception as e:
                        print(f"[TaskManager][{wid}] 终止进程树失败: {e}")
                        try:
                            task.kill()
                            task.wait()
                        except:
                            pass

                    self._tasks.pop(wid, None)
                    print(f"[TaskManager][{wid}] 任务进程已终止")

            self.progress_tracker.cancel(worker_id=worker_id)

        if not worker_id and self.chrome_manager:
            try:
                print("[TaskManager] 正在停止所有Chrome...")
                self.chrome_manager.stop_all()
                print("[TaskManager] 所有Chrome已停止")
            except Exception as e:
                print(f"[TaskManager] Chrome停止失败: {e}")

    def _build_command(self, params: Dict, endpoint: str, worker_id: str = "worker-0") -> list:
        """构建命令行

        Args:
            params: 任务参数
            endpoint: CDP端点

        Returns:
            命令行列表
        """
        # 获取工作进程路径（兼容开发和打包环境）
        base_path = get_base_path()

        # 判断是否在打包环境
        if getattr(sys, "frozen", False):
            # 打包环境：查找scraper_worker.exe
            worker_exe = base_path / "scraper_worker.exe"
            if not worker_exe.exists():
                # 尝试在exe同目录查找
                worker_exe = Path(sys.executable).parent / "scraper_worker.exe"

            cmd = [
                str(worker_exe),
                "--site", params.get("site", "pinterest"),
                "--query", params["query"],
                "--max-pins", str(params.get("max_pins", 100)),
                "--min-saves", str(params.get("min_saves", 0)),
                "--min-comments", str(params.get("min_comments", 0)),
                "--output",
                self._output_dirs.get(worker_id) or params.get("output_dir", "./output"),
                "--connect",
                "--cdp-endpoint", endpoint,
            ]

            if params.get("climb_mode"):
                cmd.append("--climb-mode")

            cmd.append("--media-type")
            cmd.append(params.get("media_type", "all"))

            # AI 筛选默认启用，仅在显式禁用时传递 --no-ai-filter
            if not params.get("enable_ai_filter", True):
                cmd.append("--no-ai-filter")
            cmd.append("--ai-filter-timeout")
            cmd.append(str(params.get("ai_filter_timeout", 180)))

            if params.get("site") == "tianjin":
                cmd.append("--max-gov-pages")
                cmd.append(str(params.get("max_gov_pages", 100)))

            # 多 Worker 标识
            if params.get("worker_id"):
                cmd.append("--worker-id")
                cmd.append(params["worker_id"])
            # 代理服务器
            if params.get("proxy_server"):
                cmd.append("--proxy-server")
                cmd.append(params["proxy_server"])

        else:
            main_py = base_path / "main.py"
            cmd = [
                sys.executable, str(main_py),
                "--site", params.get("site", "pinterest"),
                "--query", params["query"],
                "--max-pins", str(params.get("max_pins", 100)),
                "--min-saves", str(params.get("min_saves", 0)),
                "--min-comments", str(params.get("min_comments", 0)),
                "--output",
                self._output_dirs.get(worker_id) or params.get("output_dir", "./output"),
                "--connect", "--cdp-endpoint", endpoint,
            ]

            if params.get("climb_mode"):
                cmd.append("--climb-mode")

            cmd.append("--media-type")
            cmd.append(params.get("media_type", "all"))

            # AI 筛选默认启用，仅在显式禁用时传递 --no-ai-filter
            if not params.get("enable_ai_filter", True):
                cmd.append("--no-ai-filter")
            cmd.append("--ai-filter-timeout")
            cmd.append(str(params.get("ai_filter_timeout", 180)))

            if params.get("site") == "tianjin":
                cmd.append("--max-gov-pages")
                cmd.append(str(params.get("max_gov_pages", 100)))

            # 多 Worker 标识
            if params.get("worker_id"):
                cmd.append("--worker-id")
                cmd.append(params["worker_id"])
            # 代理服务器
            if params.get("proxy_server"):
                cmd.append("--proxy-server")
                cmd.append(params["proxy_server"])

        if params.get("debug"):
            cmd.append("--debug")

        return cmd
