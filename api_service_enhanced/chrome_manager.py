"""Chrome生命周期管理"""

import time
import threading
from typing import Optional
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome_launcher import ChromeLauncher
from api_service_enhanced.progress_tracker import ProgressTracker


class ChromeManager:
    """Chrome生命周期管理器"""

    AUTO_CLOSE_TIMEOUT = 300  # 5分钟无使用自动关闭

    def __init__(self, progress_tracker: ProgressTracker):
        self.progress_tracker = progress_tracker
        self.chrome_launcher: Optional[ChromeLauncher] = None
        self.last_used_time = 0
        self.lock = threading.Lock()
        self.auto_close_thread = None
        self.running = True

    def start_chrome(
        self, port: int = 9222, profile: str = "", headless: bool = False
    ) -> str:
        """启动Chrome

        Args:
            port: CDP端口
            profile: Chrome配置目录路径
            headless: 是否无头模式

        Returns:
            CDP端点URL
        """
        with self.lock:
            if self.chrome_launcher:
                # 已启动，检查是否正常
                if (
                    self.chrome_launcher.process
                    and self.chrome_launcher.process.poll() is None
                ):
                    self.last_used_time = time.time()
                    return self.chrome_launcher.endpoint
                else:
                    # 进程已退出，重新启动
                    self.chrome_launcher = None

            # 更新进度
            self.progress_tracker.update(
                "starting_chrome", 0, 100, "启动Chrome浏览器..."
            )

            # 启动Chrome
            try:
                self.chrome_launcher = ChromeLauncher(
                    port=port,
                    timeout=10,
                    user_data_dir=profile if profile else None,
                    headless=headless,
                )
                self.chrome_launcher.__enter__()
                self.last_used_time = time.time()

                # 启动自动关闭监控
                if not self.auto_close_thread:
                    self.auto_close_thread = threading.Thread(
                        target=self._auto_close_monitor, daemon=True
                    )
                    self.auto_close_thread.start()

                return self.chrome_launcher.endpoint

            except Exception as e:
                self.progress_tracker.error(f"Chrome启动失败: {str(e)}")
                raise

    def stop_chrome(self):
        """停止Chrome"""
        import psutil

        with self.lock:
            if self.chrome_launcher and self.chrome_launcher.process:
                pid = self.chrome_launcher.process.pid
                print(f"[ChromeManager] 正在停止Chrome (PID: {pid})...")

                try:
                    # 使用psutil终止进程树
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)

                    # 终止所有子进程
                    for child in children:
                        try:
                            child.terminate()
                        except:
                            pass

                    # 等待子进程结束
                    gone, alive = psutil.wait_procs(children, timeout=2)
                    for child in alive:
                        try:
                            child.kill()
                        except:
                            pass

                    # 终止主进程
                    parent.terminate()
                    parent.wait(timeout=2)

                except psutil.NoSuchProcess:
                    pass
                except Exception as e:
                    print(f"[ChromeManager] 停止Chrome失败: {e}")
                    # 备用方案
                    try:
                        self.chrome_launcher.process.kill()
                        self.chrome_launcher.process.wait()
                    except:
                        pass

                self.chrome_launcher = None
                print("[ChromeManager] Chrome已停止")

    def get_endpoint(self) -> Optional[str]:
        """获取CDP端点

        Returns:
            CDP端点URL，如果Chrome未运行则返回None
        """
        with self.lock:
            if self.chrome_launcher and self.chrome_launcher.process:
                if self.chrome_launcher.process.poll() is None:
                    self.last_used_time = time.time()
                    return self.chrome_launcher.endpoint
            return None

    def is_running(self) -> bool:
        """检查Chrome是否运行"""
        with self.lock:
            return (
                self.chrome_launcher is not None
                and self.chrome_launcher.process is not None
                and self.chrome_launcher.process.poll() is None
            )

    def _auto_close_monitor(self):
        """自动关闭监控"""
        while self.running:
            time.sleep(60)  # 每分钟检查一次

            with self.lock:
                if self.chrome_launcher and self.chrome_launcher.process:
                    if self.chrome_launcher.process.poll() is None:
                        # 进程仍在运行
                        idle_time = time.time() - self.last_used_time
                        if idle_time > self.AUTO_CLOSE_TIMEOUT:
                            # 超时未使用，关闭Chrome
                            print(f"Chrome已空闲{int(idle_time)}秒，自动关闭...")
                            try:
                                self.chrome_launcher.__exit__(None, None, None)
                            except Exception as e:
                                print(f"自动关闭Chrome时出错: {e}")
                            finally:
                                self.chrome_launcher = None

    def cleanup(self):
        """清理资源"""
        self.running = False
        self.stop_chrome()
