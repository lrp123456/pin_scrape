"""Chrome 自动启动模块"""

import os
import subprocess
import time
import tempfile
import uuid
from typing import Optional
from pathlib import Path

import requests


def find_chrome_executable() -> str:
    """
    查找 Chrome/Chromium 可执行文件路径

    Returns:
        Chrome/Chromium 可执行文件的完整路径

    Raises:
        FileNotFoundError: 如果 Chrome 未安装
    """
    import platform

    system = platform.system()

    # Linux 常见路径（Docker 容器）
    if system == "Linux":
        possible_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            # 系统共享位置的 Chromium（所有用户可访问）
            "/usr/local/share/chromium/chrome-linux64/chrome",
            # Playwright 安装的 Chromium（root用户）
            "/root/.cache/ms-playwright/chromium-*/chrome-linux64/chrome",
        ]

        for path in possible_paths:
            if "*" in path:
                # 处理通配符
                import glob

                matches = glob.glob(path)
                if matches:
                    return matches[0]
            elif os.path.exists(path):
                return path

        # 尝试从 PATH 中查找
        import shutil

        for cmd in ["chromium", "chromium-browser", "google-chrome"]:
            found = shutil.which(cmd)
            if found:
                return found

        # 未找到
        raise FileNotFoundError(
            f"未找到 Chromium/Chrome 浏览器安装（Linux）。\n"
            f"请运行以下命令安装：\n"
            f"  playwright install chromium\n"
            f"或在 Dockerfile 中添加：\n"
            f"  RUN playwright install chromium"
        )

    # Windows 常见路径
    elif system == "Windows":
        possible_paths = [
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(
                r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

    # macOS 常见路径
    elif system == "Darwin":
        possible_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

    # 未找到 Chrome
    raise FileNotFoundError(
        f"未找到 Chrome/Chromium 浏览器安装。\n"
        f"系统: {system}\n"
        f"请安装 Google Chrome 或 Chromium，或使用 --connect 参数连接到已有浏览器。"
    )


class ChromeLauncher:
    """Chrome 进程生命周期管理器"""

    # 默认的持久化配置目录
    DEFAULT_PROFILE_DIR = Path.home() / 'AppData' / 'Local' / 'PinterestScraper' / 'chrome_profile'

    def __init__(
        self,
        port: int = 9222,
        timeout: int = 10,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
    ):
        """
        初始化 Chrome Launcher

        Args:
            port: CDP 调试端口
            timeout: 等待 Chrome 启动的超时时间（秒）
            user_data_dir: 用户数据目录路径（持久化登录状态）。如果为 None，使用默认持久化目录
            headless: 是否以无头模式启动（默认 True，适合容器环境）
        """
        self.port = port
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self.chrome_path: Optional[str] = None

        # 如果未指定用户数据目录，使用默认持久化目录
        if user_data_dir is None:
            self.user_data_dir = str(self.DEFAULT_PROFILE_DIR)
            self._is_temp_profile = False
        else:
            self.user_data_dir = user_data_dir
            self._is_temp_profile = False  # 所有指定目录都是持久化的

        self.headless = headless

    def __enter__(self) -> "ChromeLauncher":
        """启动 Chrome 并等待 CDP 端点就绪"""
        self.chrome_path = find_chrome_executable()

        # 创建用户数据目录（如果不存在）
        if self.user_data_dir:
            os.makedirs(self.user_data_dir, exist_ok=True)
            print(f"使用Chrome配置目录: {self.user_data_dir}")

        # 启动 Chrome
        self.process = self._launch_chrome()

        # 等待 CDP 端点就绪
        self._wait_for_cdp()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """关闭 Chrome 进程"""
        # 持久化配置不关闭浏览器，保留登录状态
        if not self._is_temp_profile:
            print("Chrome配置已保存，浏览器保持运行")
            return

        # 临时配置才关闭进程
        if self.process and self.process.poll() is None:
            # 进程仍在运行，尝试优雅关闭
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 超时后强制终止
                self.process.kill()
                self.process.wait()

    @property
    def endpoint(self) -> str:
        """返回 CDP 端点 URL"""
        return f"http://localhost:{self.port}"

    def _launch_chrome(self) -> subprocess.Popen:
        """
        启动 Chrome 浏览器

        Returns:
            Chrome 进程对象
        """
        cmd = [
            self.chrome_path,
            f"--remote-debugging-port={self.port}",
            "--remote-debugging-address=0.0.0.0",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-default-apps",
            "--disable-translate",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--metrics-recording-only",
            "--disable-default-apps",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ]

        # 检查代理环境变量并配置 Chrome 代理
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        if http_proxy:
            cmd.extend(
                [
                    f"--proxy-server={http_proxy}",
                    "--proxy-bypass-list=localhost,127.0.0.1",
                ]
            )

        if self.headless:
            cmd.append("--headless")

        cmd.append("about:blank")

        # 根据操作系统设置进程创建参数
        # Windows 使用 DETACHED_PROCESS，Linux/macOS 使用 start_new_session
        import platform

        popen_kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }

        if platform.system() == "Windows":
            popen_kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(cmd, **popen_kwargs)

        return process

    def _wait_for_cdp(self):
        """
        等待 CDP 端点就绪

        Raises:
            TimeoutError: 如果 Chrome 在超时时间内未启动
        """
        url = f"{self.endpoint}/json/version"
        max_attempts = self.timeout * 2  # 每 0.5 秒尝试一次

        for attempt in range(max_attempts):
            try:
                response = requests.get(url, timeout=1)
                if response.status_code == 200:
                    # CDP 端点已就绪
                    return
            except requests.exceptions.RequestException:
                # 端点未就绪，继续等待
                pass

            # 检查进程是否仍在运行
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Chrome 进程意外退出，退出码: {self.process.returncode}"
                )

            time.sleep(0.5)

        # 超时
        raise TimeoutError(
            f"Chrome 在 {self.timeout} 秒内未能启动。\n"
            f"请检查端口 {self.port} 是否被占用，或尝试使用其他端口。"
        )
