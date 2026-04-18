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
    """任务执行管理器"""

    def __init__(
        self, chrome_manager: ChromeManager, progress_tracker: ProgressTracker
    ):
        self.chrome_manager = chrome_manager
        self.progress_tracker = progress_tracker
        self.current_task: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()

    def run_scrape(self, params: Dict) -> Dict:
        """执行爬虫任务

        Args:
            params: 任务参数
                - query: 搜索关键词
                - max_pins: 最大数量
                - min_saves: 最小保存数
                - min_likes: 最小点赞数
                - min_comments: 最小评论数
                - output_dir: 输出目录
                - chrome_port: Chrome端口
                - chrome_profile: Chrome配置目录
                - chrome_headless: 是否无头模式
                - debug: 是否调试模式

        Returns:
            执行结果
        """
        with self.lock:
            if self.current_task and self.current_task.poll() is None:
                return {"success": False, "error": "Another task is already running"}

        # 启动Chrome（如果未启动）
        endpoint = self.chrome_manager.get_endpoint()
        if not endpoint:
            try:
                print("[TaskManager] Chrome未启动，正在启动...")
                endpoint = self.chrome_manager.start_chrome(
                    port=params.get("chrome_port", 9222),
                    profile=params.get("chrome_profile", ""),
                    headless=params.get("chrome_headless", False),
                )
                print(f"[TaskManager] Chrome已启动: {endpoint}")
            except Exception as e:
                error_msg = f"Chrome启动失败: {str(e)}"
                print(f"[TaskManager] {error_msg}")
                return {"success": False, "error": error_msg}

        # 更新进度
        self.progress_tracker.start_task(params["query"], params.get("max_pins", 100))
        print(f"[TaskManager] 开始任务: {params['query']}")

        # 创建进度文件路径（与ProgressTracker使用相同路径）
        progress_file = Path(os.getenv("TEMP", ".")) / "pinterest_scraper_progress.json"

        # 构建环境变量
        env = os.environ.copy()
        env["PROGRESS_FILE"] = str(progress_file)

        # 执行爬虫
        cmd = self._build_command(params, endpoint)
        print(f"[TaskManager] 执行命令: {' '.join(cmd)}")

        try:
            with self.lock:
                self.current_task = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
        except Exception as e:
            error_msg = f"启动任务失败: {str(e)}"
            print(f"[TaskManager] {error_msg}")
            self.progress_tracker.error(error_msg)
            return {"success": False, "error": error_msg}

        # 等待完成
        print("[TaskManager] 等待爬虫进程完成...")
        try:
            stdout, stderr = self.current_task.communicate(timeout=600)
            return_code = self.current_task.returncode

            print(f"[TaskManager] 进程结束，返回码: {return_code}")
            print(f"[TaskManager] ===== STDOUT =====")
            print(stdout)
            print(f"[TaskManager] ===== STDERR =====")
            print(stderr)
            print(f"[TaskManager] ==================")

            if return_code == 0:
                # 图片下载（如果启用）
                downloaded_count = 0
                if params.get("download_images", True):
                    try:
                        output_dir = Path(params.get("output_dir", "./output"))
                        # 优先使用达标数据文件
                        qualified_file = output_dir / "qualified_pins.json"
                        data_file = output_dir / "data.json"

                        if qualified_file.exists():
                            pins = load_pins_from_json(qualified_file)
                            print(f"[TaskManager] 使用达标数据: {len(pins)} 个pins")
                        else:
                            pins = load_pins_from_json(data_file)
                            print(f"[TaskManager] 使用全部数据: {len(pins)} 个pins")

                        if pins:
                            print(f"[TaskManager] 开始下载 {len(pins)} 张图片...")
                            # 动态导入 downloader 避免循环依赖
                            sys.path.insert(0, str(get_base_path()))
                            from downloader import ImageDownloader
                            from shared.models import Pin

                            # 获取查询词用于文件命名
                            query = params.get("query", "")
                            use_folder = params.get("use_folder_structure", False)

                            downloader = ImageDownloader(
                                str(output_dir),
                                query=query,
                                use_folder_structure=use_folder,
                            )
                            pin_objects = [Pin(**p) for p in pins]

                            # 纯爬坡模式不过滤，下载所有
                            if params.get("climb_mode"):
                                downloaded = downloader.filter_and_download(
                                    pin_objects,
                                    min_saves=0,
                                    min_likes=0,
                                    min_comments=0,
                                )
                            else:
                                downloaded = downloader.filter_and_download(
                                    pin_objects,
                                    min_saves=params.get("min_saves", 0),
                                    min_likes=params.get("min_likes", 0),
                                    min_comments=params.get("min_comments", 0),
                                )
                            downloaded_count = len(downloaded)
                            print(
                                f"[TaskManager] ✓ 图片下载完成: {downloaded_count}/{len(pins)} 张"
                            )
                    except Exception as e:
                        print(f"[TaskManager] 图片下载失败: {e}")

                self.progress_tracker.complete()
                print("[TaskManager] ✓ 任务成功完成")
                return {
                    "success": True,
                    "output": stdout,
                    "message": "任务完成",
                    "downloaded_images": downloaded_count,
                }
            else:
                error_msg = stderr[:500] if stderr else "未知错误"
                print(f"[TaskManager] ✗ 任务失败: {error_msg}")
                self.progress_tracker.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "return_code": return_code,
                }

        except subprocess.TimeoutExpired:
            print("[TaskManager] ✗ 任务超时")
            self.current_task.kill()
            self.current_task.wait()
            self.progress_tracker.error("任务超时")
            return {"success": False, "error": "Task timeout after 600s"}

        except Exception as e:
            error_msg = str(e)
            print(f"[TaskManager] ✗ 任务异常: {error_msg}")
            self.progress_tracker.error(error_msg)
            return {"success": False, "error": error_msg}

        finally:
            with self.lock:
                self.current_task = None
            print("[TaskManager] 任务清理完成")

    def cancel_current(self):
        """取消当前任务并清理相关进程"""
        import psutil

        with self.lock:
            if self.current_task and self.current_task.poll() is None:
                # 获取进程ID
                pid = self.current_task.pid
                print(f"[TaskManager] 正在终止任务进程 (PID: {pid})...")

                try:
                    # 使用psutil终止整个进程树
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)

                    # 先终止子进程
                    for child in children:
                        try:
                            child.terminate()
                        except:
                            pass

                    # 等待子进程结束
                    gone, alive = psutil.wait_procs(children, timeout=3)
                    for child in alive:
                        try:
                            child.kill()
                        except:
                            pass

                    # 终止主进程
                    parent.terminate()
                    parent.wait(timeout=3)

                except psutil.NoSuchProcess:
                    pass
                except Exception as e:
                    print(f"[TaskManager] 终止进程树失败: {e}")
                    # 备用方案：强制kill
                    try:
                        self.current_task.kill()
                        self.current_task.wait()
                    except:
                        pass

                self.current_task = None
                print("[TaskManager] 任务进程已终止")

            self.progress_tracker.cancel()

        # 停止Chrome
        if self.chrome_manager:
            try:
                print("[TaskManager] 正在停止Chrome...")
                self.chrome_manager.stop_chrome()
                print("[TaskManager] Chrome已停止")
            except Exception as e:
                print(f"[TaskManager] Chrome停止失败: {e}")

    def _build_command(self, params: Dict, endpoint: str) -> list:
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
                "--query",
                params["query"],
                "--max-pins",
                str(params.get("max_pins", 100)),
                "--min-saves",
                str(params.get("min_saves", 0)),
                "--min-likes",
                str(params.get("min_likes", 0)),
                "--min-comments",
                str(params.get("min_comments", 0)),
                "--output",
                params.get("output_dir", "./output"),
                "--connect",
                "--cdp-endpoint",
                endpoint,
            ]

            # 添加爬坡模式参数
            if params.get("climb_mode"):
                cmd.append("--climb-mode")

            # 添加媒体类型参数
            cmd.append("--media-type")
            cmd.append(params.get("media_type", "all"))

        else:
            # 开发环境：使用Python执行main.py
            main_py = base_path / "main.py"
            cmd = [
                sys.executable,
                str(main_py),
                "--query",
                params["query"],
                "--max-pins",
                str(params.get("max_pins", 100)),
                "--min-saves",
                str(params.get("min_saves", 0)),
                "--min-likes",
                str(params.get("min_likes", 0)),
                "--min-comments",
                str(params.get("min_comments", 0)),
                "--output",
                params.get("output_dir", "./output"),
                "--connect",
                "--cdp-endpoint",
                endpoint,
            ]

            # 添加爬坡模式参数
            if params.get("climb_mode"):
                cmd.append("--climb-mode")

            # 添加媒体类型参数
            cmd.append("--media-type")
            cmd.append(params.get("media_type", "all"))

        if params.get("debug"):
            cmd.append("--debug")

        return cmd
