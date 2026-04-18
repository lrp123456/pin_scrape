"""托盘图标和菜单管理"""

import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import time

import pystray
from PIL import Image, ImageDraw


class TrayIconManager:
    """托盘图标管理器"""

    def __init__(self, process_manager, config_manager):
        """
        初始化托盘图标管理器

        Args:
            process_manager: 进程管理器
            config_manager: 配置管理器
        """
        self.process_manager = process_manager
        self.config_manager = config_manager
        self.icon = None
        self._update_thread = None
        self._running = True

    def get_icon(self):
        """创建或加载托盘图标

        Returns:
            PIL.Image对象
        """
        # 优先加载自定义图标
        custom_icon = self.config_manager.get("custom_icon_path", "")
        if custom_icon:
            try:
                icon_path = Path(custom_icon)
                if icon_path.exists():
                    return Image.open(icon_path)
            except Exception as e:
                print(f"加载自定义图标失败: {e}")

        # 尝试加载默认图标文件
        icon_path = Path(__file__).parent / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                return Image.open(icon_path)
            except:
                pass

        # 动态生成带状态颜色的图标
        return self._create_status_icon()

    def _create_status_icon(self, size: int = 64):
        """创建带状态颜色的图标

        Args:
            size: 图标尺寸

        Returns:
            PIL.Image对象
        """
        # 创建图标图像
        image = Image.new("RGB", (size, size), color="white")
        dc = ImageDraw.Draw(image)

        # 根据服务状态选择颜色
        if self.process_manager.is_running():
            # 服务运行中 - 绿色
            bg_color = "#4CAF50"
            outline_color = "#388E3C"
        else:
            # 服务未运行 - 灰色
            bg_color = "#9E9E9E"
            outline_color = "#757575"

        # 绘制圆形背景
        dc.ellipse(
            [8, 8, size - 8, size - 8], fill=bg_color, outline=outline_color, width=2
        )

        # 绘制P字母
        dc.text((20, 15), "P", fill="white")

        return image

    def _create_default_icon(self, size: int = 64):
        """创建默认图标（向后兼容）

        Args:
            size: 图标尺寸

        Returns:
            PIL.Image对象
        """
        return self._create_status_icon(size)

    def setup_menu(self, icon):
        """设置右键菜单

        Args:
            icon: pystray.Icon实例
        """
        self.icon = icon
        icon.menu = pystray.Menu(
            # 服务状态
            pystray.MenuItem(
                lambda item: f"服务状态: {self._get_service_status()}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            # 服务控制
            pystray.MenuItem("启动服务", self._start_service),
            pystray.MenuItem("停止服务", self._stop_service),
            pystray.MenuItem("重启服务", self._restart_service),
            pystray.Menu.SEPARATOR,
            # 快捷操作
            pystray.MenuItem("控制台", self._show_console),
            pystray.MenuItem("打开API文档", self._open_api_docs),
            pystray.MenuItem("打开输出目录", self._open_output_dir),
            pystray.MenuItem("查看日志", self._open_logs),
            pystray.Menu.SEPARATOR,
            # 配置
            pystray.MenuItem("配置设置", self._show_config),
            pystray.MenuItem("修改图标", self._change_icon),
            pystray.MenuItem(
                "开机自启",
                self._toggle_autostart,
                checked=lambda item: self.config_manager.is_autostart(),
            ),
            pystray.Menu.SEPARATOR,
            # 退出
            pystray.MenuItem("退出", self._exit_app),
        )

        # 启动状态更新线程
        self._start_status_update()

    def _get_service_status(self) -> str:
        """获取服务状态文本

        Returns:
            状态文本
        """
        if self.process_manager.is_running():
            progress = self.process_manager.get_progress()
            if progress.get("running"):
                stage = progress.get("stage", "running")
                percentage = progress.get("percentage", 0)
                return f"运行中 - {stage} {percentage}%"
            return "运行中 - 空闲"
        return "已停止"

    def _start_service(self):
        """启动服务"""
        threading.Thread(target=self.process_manager.start, daemon=True).start()

    def _stop_service(self):
        """停止服务"""
        self.process_manager.stop()

    def _restart_service(self):
        """重启服务"""
        threading.Thread(target=self.process_manager.restart, daemon=True).start()

    def _open_api_docs(self):
        """打开API文档"""
        port = self.config_manager.get("api_port", 8000)
        url = f"http://localhost:{port}/docs"
        webbrowser.open(url)

    def _open_output_dir(self):
        """打开输出目录"""
        output_dir = self.config_manager.get("output_dir", "")
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            subprocess.run(["explorer", str(output_path)])

    def _open_logs(self):
        """打开日志文件"""
        # 日志目录
        app_data = Path.home() / "AppData" / "Roaming" / "PinterestScraper"
        log_file = app_data / "logs" / "api_service.log"

        if log_file.exists():
            subprocess.run(["notepad", str(log_file)])
        else:
            # 打开日志目录
            log_dir = log_file.parent
            log_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["explorer", str(log_dir)])

    def _show_console(self, event=None):
        """显示爬虫控制台（支持双击事件）"""
        try:
            # 导入控制台GUI
            from tray_app.console_gui import ScraperConsole

            # 在新线程中显示GUI（避免阻塞托盘）
            def show_console():
                try:
                    console = ScraperConsole()
                    console.show()
                except Exception as e:
                    print(f"控制台界面出错: {e}")

            thread = threading.Thread(target=show_console, daemon=True)
            thread.start()

        except Exception as e:
            print(f"打开控制台失败: {e}")

    def _show_config(self):
        """显示配置界面"""
        try:
            # 导入配置GUI
            from tray_app.config_gui import ConfigGUI

            # 在新线程中显示GUI（避免阻塞托盘）
            def show_gui():
                try:
                    gui = ConfigGUI(self.config_manager)
                    gui.show()
                except Exception as e:
                    print(f"配置界面出错: {e}")

            thread = threading.Thread(target=show_gui, daemon=True)
            thread.start()

        except Exception as e:
            print(f"打开配置界面失败: {e}")
            # 降级：使用记事本打开配置文件
            try:
                config_file = self.config_manager.config_path
                if not config_file.exists():
                    self.config_manager._save_config()
                config_file.parent.mkdir(parents=True, exist_ok=True)
                subprocess.Popen(["notepad", str(config_file)])
            except Exception as e2:
                print(f"打开配置文件也失败: {e2}")

    def _toggle_autostart(self):
        """切换开机自启"""
        current = self.config_manager.is_autostart()
        self.config_manager.set_autostart(not current)

    def _change_icon(self):
        """修改托盘图标"""
        try:
            # 使用PowerShell文件选择对话框（Windows原生）
            powershell_cmd = """
            Add-Type -AssemblyName System.Windows.Forms
            $dialog = New-Object System.Windows.Forms.OpenFileDialog
            $dialog.Title = "选择图标文件"
            $dialog.Filter = "图标文件 (*.ico)|*.ico|图片文件 (*.png, *.jpg)|*.png;*.jpg|所有文件 (*.*)|*.*"
            $dialog.ShowDialog() | Out-Null
            $dialog.FileName
            """

            result = subprocess.run(
                ["powershell", "-Command", powershell_cmd],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            icon_path = result.stdout.strip()

            if icon_path:
                # 验证图标文件
                try:
                    test_img = Image.open(icon_path)
                    test_img.close()

                    # 保存图标路径到配置
                    self.config_manager.set("custom_icon_path", icon_path)

                    print(f"✓ 图标已更新: {icon_path}")
                    print("✓ 重启应用后生效")

                    # 尝试立即更新
                    try:
                        new_icon = Image.open(icon_path)
                        if self.icon:
                            self.icon.icon = new_icon
                            print("✓ 图标已立即更新")
                    except Exception as e:
                        print(f"立即更新失败: {e}，重启后生效")

                except Exception as e:
                    print(f"✗ 无法加载图标文件: {e}")
                    print("请确保文件存在且格式正确")

        except Exception as e:
            print(f"修改图标失败: {e}")
            print("您也可以手动编辑配置文件设置图标路径")

    def _exit_app(self):
        """退出应用"""
        self._running = False
        if self.icon:
            self.icon.stop()

    def _start_status_update(self):
        """启动状态更新线程"""

        def update_loop():
            while self._running:
                try:
                    # 每隔2秒更新一次菜单和图标
                    if self.icon:
                        # 更新菜单（状态文本）
                        self.icon.update_menu()

                        # 更新图标颜色
                        try:
                            new_icon = self._create_status_icon()
                            self.icon.icon = new_icon
                        except:
                            pass
                except Exception as e:
                    print(f"状态更新出错: {e}")
                time.sleep(2)

        self._update_thread = threading.Thread(target=update_loop, daemon=True)
        self._update_thread.start()
