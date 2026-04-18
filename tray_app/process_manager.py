"""API服务进程管理"""

import subprocess
import sys
import time
import requests
import psutil
from pathlib import Path
from typing import Optional


class ProcessManager:
    """API服务进程管理器"""

    def __init__(self, config_manager):
        """
        初始化进程管理器

        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.process: Optional[subprocess.Popen] = None
        self.api_url = f"http://localhost:{config_manager.get('api_port', 8000)}"

    def start(self):
        """启动API服务进程"""
        if self.is_running():
            print("API服务已在运行")
            return True

        try:
            # 检查端口是否被占用
            port = self.config_manager.get("api_port", 8000)
            if self._is_port_in_use():
                print(f"端口 {port} 已被占用")
                print("正在尝试关闭占用进程...")

                # 尝试关闭占用端口的进程
                if self._kill_port_process(port):
                    print("✓ 占用进程已关闭")
                    time.sleep(2)  # 等待端口释放
                else:
                    print("✗ 无法关闭占用进程")
                    print(
                        f"建议：手动关闭占用 {port} 端口的程序，或修改配置中的 api_port"
                    )
                    return False

            # 获取可执行文件路径
            api_exe = self._get_api_service_path()

            if not api_exe.exists():
                print(f"API服务文件不存在: {api_exe}")
                return False

            # 启动进程
            print(f"正在启动API服务: {api_exe}")

            # 判断是开发环境还是打包后环境
            if api_exe.suffix == ".py":
                # 开发环境：使用Python运行脚本
                cmd = [sys.executable, str(api_exe), "--port", str(port)]
            else:
                # 打包后环境：直接运行exe
                cmd = [str(api_exe), "--port", str(port)]

            # 不捕获输出，避免PIPE缓冲区满导致阻塞
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP,
            )

            # 等待服务就绪
            if self._wait_for_ready(timeout=15):
                print("API服务启动成功")
                return True
            else:
                print("API服务启动超时")
                self.stop()
                return False

        except Exception as e:
            print(f"启动API服务失败: {e}")
            return False

    def stop(self):
        """停止API服务进程"""
        if not self.is_running():
            print("API服务未运行")
            return

        try:
            # 发送停止信号
            try:
                requests.post(f"{self.api_url}/api/shutdown", timeout=2)
                if self.process:
                    self.process.wait(timeout=5)
            except:
                # 强制终止
                if self.process:
                    self.process.kill()
                    self.process.wait()

            self.process = None
            print("API服务已停止")

        except Exception as e:
            print(f"停止API服务失败: {e}")

    def restart(self):
        """重启API服务进程"""
        self.stop()
        time.sleep(2)
        return self.start()

    def is_running(self) -> bool:
        """检查进程是否运行

        Returns:
            是否运行
        """
        if self.process is None:
            return False

        # 检查进程是否还在运行
        if self.process.poll() is not None:
            # 进程已退出
            self.process = None
            return False

        return True

    def get_progress(self) -> dict:
        """获取进度信息

        Returns:
            进度信息字典
        """
        if not self.is_running():
            return {"running": False, "stage": "idle", "message": "服务未运行"}

        try:
            response = requests.get(f"{self.api_url}/api/progress", timeout=2)
            if response.status_code == 200:
                return response.json()
        except:
            pass

        return {"running": False, "stage": "idle", "message": "无法获取状态"}

    def _wait_for_ready(self, timeout: int = 10) -> bool:
        """等待服务就绪

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否就绪
        """
        start_time = time.time()
        check_interval = 0.1  # 每100ms检查一次

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.api_url}/api/health", timeout=0.5)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(check_interval)

        return False

    def _is_port_in_use(self) -> bool:
        """检查端口是否被占用

        Returns:
            是否被占用
        """
        port = self.config_manager.get("api_port", 8000)
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                return True
        return False

    def _kill_port_process(self, port: int) -> bool:
        """关闭占用端口的进程

        Args:
            port: 端口号

        Returns:
            是否成功关闭
        """
        try:
            # 查找占用端口的进程
            for conn in psutil.net_connections():
                if conn.laddr.port == port and conn.pid:
                    try:
                        # 关闭进程
                        process = psutil.Process(conn.pid)
                        process_name = process.name()
                        print(f"  关闭进程: {process_name} (PID: {conn.pid})")
                        process.terminate()

                        # 等待进程结束
                        try:
                            process.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            process.kill()

                        return True
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        print(f"  无法关闭进程: {e}")
                        continue

            return False
        except Exception as e:
            print(f"关闭进程出错: {e}")
            return False

    def _get_api_service_path(self) -> Path:
        """获取API服务可执行文件路径

        Returns:
            可执行文件路径
        """
        # 打包后的路径
        exe_dir = Path(sys.executable).parent
        api_exe = exe_dir / "api_service.exe"

        if api_exe.exists():
            return api_exe

        # 开发环境路径
        root_dir = Path(__file__).parent.parent
        return root_dir / "api_service_enhanced" / "service_main.py"
