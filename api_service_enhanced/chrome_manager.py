"""Chrome生命周期管理（支持多Worker多实例）"""

import time
import threading
from typing import Optional, Dict
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome_launcher import ChromeLauncher
from api_service_enhanced.progress_tracker import ProgressTracker


class ChromeManager:
    """Chrome生命周期管理器（支持多Worker多实例）"""

    AUTO_CLOSE_TIMEOUT = 300

    def __init__(self, progress_tracker: ProgressTracker):
        self.progress_tracker = progress_tracker
        self._launchers: Dict[str, ChromeLauncher] = {}
        self._last_used: Dict[str, float] = {}
        self.lock = threading.Lock()
        self.auto_close_thread = None
        self.running = True

    def start_chrome(
        self, port: int = 9222, profile: str = "", headless: bool = False,
        proxy_server: Optional[str] = None, worker_id: str = "worker-0"
    ) -> str:
        """启动Chrome

        Args:
            port: CDP端口
            profile: Chrome配置目录路径。空字符串使用默认持久化目录，"worker_N"使用Worker专用目录
            headless: 是否无头模式
            proxy_server: 代理服务器地址
            worker_id: Worker标识

        Returns:
            CDP端点URL
        """
        with self.lock:
            if worker_id in self._launchers:
                launcher = self._launchers[worker_id]
                if launcher.process and launcher.process.poll() is None:
                    self._last_used[worker_id] = time.time()
                    return launcher.endpoint
                else:
                    self._launchers.pop(worker_id, None)

            self.progress_tracker.update(
                "starting_chrome", 0, 100, f"启动Chrome浏览器 ({worker_id})...",
                worker_id=worker_id,
            )

            try:
                user_data_dir = self._resolve_profile(profile, worker_id)

                launcher = ChromeLauncher(
                    port=port,
                    timeout=10,
                    user_data_dir=user_data_dir,
                    headless=headless,
                    proxy_server=proxy_server,
                )
                launcher.__enter__()
                self._launchers[worker_id] = launcher
                self._last_used[worker_id] = time.time()

                if not self.auto_close_thread:
                    self.auto_close_thread = threading.Thread(
                        target=self._auto_close_monitor, daemon=True
                    )
                    self.auto_close_thread.start()

                return launcher.endpoint

            except Exception as e:
                self.progress_tracker.error(f"Chrome启动失败: {str(e)}", worker_id=worker_id)
                raise

    def _resolve_profile(self, profile: str, worker_id: str) -> str:
        """解析Chrome配置目录

        Args:
            profile: 请求的配置路径
            worker_id: Worker标识

        Returns:
            实际的配置目录路径
        """
        if profile:
            if profile.startswith("worker_"):
                base_dir = ChromeLauncher.DEFAULT_PROFILE_DIR.parent / profile
                base_dir.mkdir(parents=True, exist_ok=True)
                return str(base_dir)
            return profile
        if worker_id == "worker-0":
            return None
        w_idx = worker_id.rsplit("-", 1)[-1]
        worker_dir = ChromeLauncher.DEFAULT_PROFILE_DIR.parent / f"worker_{w_idx}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        return str(worker_dir)

    def stop_chrome(self, worker_id: str = None):
        """停止Chrome

        Args:
            worker_id: 指定Worker ID停止，None则停止所有
        """
        import psutil

        with self.lock:
            target_ids = [worker_id] if worker_id else list(self._launchers.keys())
            for wid in target_ids:
                launcher = self._launchers.get(wid)
                if launcher and launcher.process:
                    pid = launcher.process.pid
                    print(f"[ChromeManager][{wid}] 正在停止Chrome (PID: {pid})...")

                    try:
                        parent = psutil.Process(pid)
                        children = parent.children(recursive=True)

                        for child in children:
                            try:
                                child.terminate()
                            except:
                                pass

                        gone, alive = psutil.wait_procs(children, timeout=2)
                        for child in alive:
                            try:
                                child.kill()
                            except:
                                pass

                        parent.terminate()
                        parent.wait(timeout=2)

                    except psutil.NoSuchProcess:
                        pass
                    except Exception as e:
                        print(f"[ChromeManager][{wid}] 停止Chrome失败: {e}")
                        try:
                            launcher.process.kill()
                            launcher.process.wait()
                        except:
                            pass

                    self._launchers.pop(wid, None)
                    self._last_used.pop(wid, None)
                    print(f"[ChromeManager][{wid}] Chrome已停止")

    def stop_all(self):
        """停止所有Chrome实例"""
        self.stop_chrome()

    def get_endpoint(self, worker_id: str = "worker-0") -> Optional[str]:
        """获取CDP端点

        Args:
            worker_id: Worker标识

        Returns:
            CDP端点URL，如果Chrome未运行则返回None
        """
        with self.lock:
            launcher = self._launchers.get(worker_id)
            if launcher and launcher.process:
                if launcher.process.poll() is None:
                    self._last_used[worker_id] = time.time()
                    return launcher.endpoint
            return None

    def is_running(self, worker_id: str = "worker-0") -> bool:
        """检查Chrome是否运行"""
        with self.lock:
            launcher = self._launchers.get(worker_id)
            return (
                launcher is not None
                and launcher.process is not None
                and launcher.process.poll() is None
            )

    def _auto_close_monitor(self):
        """自动关闭监控"""
        while self.running:
            time.sleep(60)

            with self.lock:
                to_remove = []
                for wid, launcher in self._launchers.items():
                    if launcher.process and launcher.process.poll() is None:
                        idle_time = time.time() - self._last_used.get(wid, time.time())
                        if idle_time > self.AUTO_CLOSE_TIMEOUT:
                            print(f"[ChromeManager][{wid}] 已空闲{int(idle_time)}秒，自动关闭...")
                            try:
                                launcher.__exit__(None, None, None)
                            except Exception as e:
                                print(f"[ChromeManager][{wid}] 自动关闭出错: {e}")
                            to_remove.append(wid)

                for wid in to_remove:
                    self._launchers.pop(wid, None)
                    self._last_used.pop(wid, None)

    def cleanup(self):
        """清理资源"""
        self.running = False
        self.stop_all()
