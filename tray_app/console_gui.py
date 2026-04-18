"""Pinterest爬虫控制台"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import threading
from datetime import datetime


class ScraperConsole:
    """爬虫控制台"""

    def __init__(self):
        """初始化控制台"""
        self.root = None
        self.api_url = "http://localhost:8000"
        self.task_running = False

    def show(self):
        """显示控制台窗口（支持双击重新打开）"""
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("Pinterest爬虫控制台")
        self.root.geometry("700x600")
        self.root.resizable(True, True)

        # 设置窗口图标
        try:
            from pathlib import Path

            icon_path = Path(__file__).parent / "assets" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass

        # 双击事件绑定 - 双击窗口标题栏可重新打开配置
        self.root.bind("<Double-1>", self._on_double_click)

        # 创建主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # 配置权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

        # 创建组件
        self._create_input_panel(main_frame)
        self._create_button_panel(main_frame)
        self._create_progress_panel(main_frame)
        self._create_log_panel(main_frame)

        # 启动进度更新线程
        self._start_progress_monitor()

        # 运行窗口
        self.root.mainloop()

    def _on_double_click(self, event):
        """双击事件处理 - 重新加载配置"""
        from shared.config_manager import get_config, save_config

        config = get_config()

        # 弹出配置修改对话框
        config_window = tk.Toplevel(self.root)
        config_window.title("高级系统配置")
        config_window.geometry("400x350")
        config_window.transient(self.root)
        config_window.grab_set()

        # Redis配置输入框
        ttk.Label(config_window, text="Redis主机:").grid(
            row=0, column=0, sticky="w", padx=10, pady=5
        )
        redis_host_var = tk.StringVar(value=config.get("redis_host", "localhost"))
        ttk.Entry(config_window, textvariable=redis_host_var, width=40).grid(
            row=0, column=1, padx=10, pady=5
        )

        ttk.Label(config_window, text="Redis端口:").grid(
            row=1, column=0, sticky="w", padx=10, pady=5
        )
        redis_port_var = tk.IntVar(value=config.get("redis_port", 6379))
        ttk.Entry(config_window, textvariable=redis_port_var, width=40).grid(
            row=1, column=1, padx=10, pady=5
        )

        ttk.Label(config_window, text="Redis数据库:").grid(
            row=2, column=0, sticky="w", padx=10, pady=5
        )
        redis_db_var = tk.IntVar(value=config.get("redis_db", 0))
        ttk.Entry(config_window, textvariable=redis_db_var, width=40).grid(
            row=2, column=1, padx=10, pady=5
        )

        ttk.Label(config_window, text="Redis密码:").grid(
            row=3, column=0, sticky="w", padx=10, pady=5
        )
        redis_password_var = tk.StringVar(value=config.get("redis_password", ""))
        ttk.Entry(
            config_window, textvariable=redis_password_var, width=40, show="*"
        ).grid(row=3, column=1, padx=10, pady=5)

        # 输出路径配置
        ttk.Label(config_window, text="输出路径:").grid(
            row=4, column=0, sticky="w", padx=10, pady=5
        )
        output_dir_var = tk.StringVar(value=config.get("output_dir", ""))
        ttk.Entry(config_window, textvariable=output_dir_var, width=40).grid(
            row=4, column=1, padx=10, pady=5
        )

        def save_and_test():
            """保存配置并测试连接"""
            new_config = {
                "redis_host": redis_host_var.get(),
                "redis_port": redis_port_var.get(),
                "redis_db": redis_db_var.get(),
                "redis_password": redis_password_var.get(),
                "output_dir": output_dir_var.get(),
            }

            # 测试Redis连接
            from shared.config_manager import test_redis_connection

            if test_redis_connection(new_config):
                save_config(new_config)
                messagebox.showinfo("成功", "配置保存成功，Redis连接正常！")
                config_window.destroy()
            else:
                messagebox.showerror("错误", "Redis连接失败，请检查配置")

        ttk.Button(config_window, text="保存并测试", command=save_and_test).grid(
            row=5, column=1, pady=10, sticky="e"
        )

    def _create_input_panel(self, parent):
        """创建输入面板"""
        input_frame = ttk.LabelFrame(parent, text="爬虫参数", padding="10")
        input_frame.grid(row=0, column=0, sticky="ew", pady=5)
        input_frame.columnconfigure(1, weight=1)

        # 搜索关键词
        ttk.Label(input_frame, text="搜索关键词:").grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.query_entry = ttk.Entry(input_frame, width=50)
        self.query_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=(5, 0))
        self.query_entry.insert(0, "简约风格")  # 默认值

        # 最大数量
        ttk.Label(input_frame, text="最大爬取数量:").grid(
            row=1, column=0, sticky="w", pady=5
        )
        self.max_pins_spinbox = ttk.Spinbox(
            input_frame, from_=10, to=1000, increment=10, width=47
        )
        self.max_pins_spinbox.grid(row=1, column=1, sticky="ew", pady=5, padx=(5, 0))
        self.max_pins_spinbox.delete(0, tk.END)
        self.max_pins_spinbox.insert(0, "50")

        # 筛选条件框架
        filter_frame = ttk.Frame(input_frame)
        filter_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)

        # 最小保存数
        ttk.Label(filter_frame, text="最小保存数:").grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        self.min_saves_spinbox = ttk.Spinbox(
            filter_frame, from_=0, to=10000, increment=10, width=10
        )
        self.min_saves_spinbox.grid(row=0, column=1, sticky="w", padx=(0, 20))
        self.min_saves_spinbox.delete(0, tk.END)
        self.min_saves_spinbox.insert(0, "0")

        # 最小点赞数
        ttk.Label(filter_frame, text="最小点赞数:").grid(
            row=0, column=2, sticky="w", padx=(0, 5)
        )
        self.min_likes_spinbox = ttk.Spinbox(
            filter_frame, from_=0, to=10000, increment=10, width=10
        )
        self.min_likes_spinbox.grid(row=0, column=3, sticky="w", padx=(0, 20))
        self.min_likes_spinbox.delete(0, tk.END)
        self.min_likes_spinbox.insert(0, "0")

        # 最小评论数
        ttk.Label(filter_frame, text="最小评论数:").grid(
            row=0, column=4, sticky="w", padx=(0, 5)
        )
        self.min_comments_spinbox = ttk.Spinbox(
            filter_frame, from_=0, to=10000, increment=10, width=10
        )
        self.min_comments_spinbox.grid(row=0, column=5, sticky="w")
        self.min_comments_spinbox.delete(0, tk.END)
        self.min_comments_spinbox.insert(0, "0")

        # 下载图片选项
        download_frame = ttk.Frame(input_frame)
        download_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)

        self.download_images_var = tk.BooleanVar(value=True)
        self.download_images_check = ttk.Checkbutton(
            download_frame,
            text="下载图片",
            variable=self.download_images_var,
        )
        self.download_images_check.pack(side="left", padx=(0, 20))

        # 媒体类型选择
        self.media_type_var = tk.StringVar(value="all")
        self.media_type_label = ttk.Label(download_frame, text="媒体类型:")
        self.media_type_label.pack(side="left")
        self.media_type_menu = ttk.OptionMenu(
            download_frame,
            self.media_type_var,
            "all",
            "all",
            "images",
            "video",
        )
        self.media_type_menu.pack(side="left", padx=(0, 10))

        # 纯爬坡模式（不检查min_saves，一直爬坡收集）
        self.climb_mode_var = tk.BooleanVar(value=False)
        self.climb_mode_check = ttk.Checkbutton(
            download_frame,
            text="纯爬坡模式(忽视最小保存数，持续找更优)",
            variable=self.climb_mode_var,
        )
        self.climb_mode_check.pack(side="left")

    def _create_button_panel(self, parent):
        """创建按钮面板"""
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=1, column=0, pady=10)

        # 开始爬取按钮
        self.start_button = ttk.Button(
            button_frame, text="🚀 开始爬取", command=self._start_scrape, width=15
        )
        self.start_button.pack(side="left", padx=5)

        # 异步爬取按钮
        self.async_button = ttk.Button(
            button_frame, text="⚡ 后台爬取", command=self._start_scrape_async, width=15
        )
        self.async_button.pack(side="left", padx=5)

        # 停止按钮
        self.stop_button = ttk.Button(
            button_frame,
            text="⏹ 停止任务",
            command=self._stop_scrape,
            width=15,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=5)

        # 打开API文档
        ttk.Button(
            button_frame, text="📖 API文档", command=self._open_api_docs, width=15
        ).pack(side="left", padx=5)

        # 打开输出目录
        ttk.Button(
            button_frame, text="📁 输出目录", command=self._open_output_dir, width=15
        ).pack(side="left", padx=5)

    def _create_progress_panel(self, parent):
        """创建进度面板"""
        progress_frame = ttk.LabelFrame(parent, text="任务进度", padding="10")
        progress_frame.grid(row=2, column=0, sticky="ew", pady=5)
        progress_frame.columnconfigure(1, weight=1)

        # 状态标签
        ttk.Label(progress_frame, text="状态:").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.status_label = ttk.Label(progress_frame, text="空闲", foreground="gray")
        self.status_label.grid(row=0, column=1, sticky="w", pady=2, padx=(5, 0))

        # 进度条
        ttk.Label(progress_frame, text="进度:").grid(
            row=1, column=0, sticky="w", pady=5
        )
        self.progress_bar = ttk.Progressbar(
            progress_frame, length=400, mode="determinate"
        )
        self.progress_bar.grid(row=1, column=1, sticky="ew", pady=5, padx=(5, 0))

        # 进度文本
        self.progress_label = ttk.Label(progress_frame, text="0%")
        self.progress_label.grid(row=1, column=2, sticky="w", pady=5, padx=(5, 0))

        # 当前任务信息
        ttk.Label(progress_frame, text="任务信息:").grid(
            row=2, column=0, sticky="w", pady=2
        )
        self.task_info_label = ttk.Label(
            progress_frame, text="无任务", foreground="gray"
        )
        self.task_info_label.grid(
            row=2, column=1, columnspan=2, sticky="w", pady=2, padx=(5, 0)
        )

    def _create_log_panel(self, parent):
        """创建日志面板"""
        log_frame = ttk.LabelFrame(parent, text="执行日志", padding="10")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(
            log_frame, width=80, height=15, state="disabled", font=("Consolas", 9)
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        # 清空日志按钮
        ttk.Button(log_frame, text="清空日志", command=self._clear_log, width=10).grid(
            row=1, column=0, sticky="e", pady=(5, 0)
        )

    def _start_scrape(self):
        """开始同步爬取"""
        if self.task_running:
            messagebox.showwarning("警告", "已有任务在运行中")
            return

        # 获取参数
        params = self._get_params()
        if not params["query"]:
            messagebox.showerror("错误", "请输入搜索关键词")
            return

        self._log(f"开始爬取: {params['query']}")
        self._set_ui_running(True)

        # 在后台线程执行
        def run_scrape():
            try:
                response = requests.post(
                    f"{self.api_url}/api/scrape", json=params, timeout=600
                )

                if response.status_code == 200:
                    result = response.json()
                    self._log(f"✓ 爬取完成！")
                    self._log(f"结果: {result.get('message', '成功')}")
                else:
                    error = response.json().get("detail", "未知错误")
                    self._log(f"✗ 爬取失败: {error}")

            except Exception as e:
                self._log(f"✗ 请求失败: {str(e)}")
            finally:
                self._set_ui_running(False)

        thread = threading.Thread(target=run_scrape, daemon=True)
        thread.start()

    def _start_scrape_async(self):
        """开始异步爬取"""
        if self.task_running:
            messagebox.showwarning("警告", "已有任务在运行中")
            return

        # 获取参数
        params = self._get_params()
        if not params["query"]:
            messagebox.showerror("错误", "请输入搜索关键词")
            return

        try:
            response = requests.post(
                f"{self.api_url}/api/scrape/async", json=params, timeout=10
            )

            if response.status_code == 200:
                self._log(f"✓ 后台任务已启动: {params['query']}")
                self._set_ui_running(True)
            else:
                error = response.json().get("detail", "未知错误")
                self._log(f"✗ 启动失败: {error}")

        except Exception as e:
            self._log(f"✗ 请求失败: {str(e)}")

    def _stop_scrape(self):
        """停止爬取"""
        try:
            response = requests.post(f"{self.api_url}/api/stop", timeout=5)
            if response.status_code == 200:
                self._log("⏹ 正在停止任务...")
                self._set_ui_running(False)
            else:
                self._log("✗ 停止失败")
        except Exception as e:
            self._log(f"✗ 请求失败: {str(e)}")

    def _get_params(self):
        """获取爬取参数"""
        climb_mode = self.climb_mode_var.get()
        min_saves = int(self.min_saves_spinbox.get())

        # 纯爬坡模式：强制min_saves=0，使用相似推荐探索模式
        if climb_mode:
            min_saves = 0

        return {
            "query": self.query_entry.get().strip(),
            "max_pins": int(self.max_pins_spinbox.get()),
            "min_saves": min_saves,
            "min_likes": int(self.min_likes_spinbox.get()),
            "min_comments": int(self.min_comments_spinbox.get()),
            "media_type": self.media_type_var.get(),
            "download_images": self.download_images_var.get(),
            "climb_mode": climb_mode,
            "use_folder_structure": False,  # 默认不使用文件夹结构
        }

    def _set_ui_running(self, running):
        """设置UI状态"""
        self.task_running = running

        if running:
            self.start_button.config(state="disabled")
            self.async_button.config(state="disabled")
            self.stop_button.config(state="normal")
        else:
            self.start_button.config(state="normal")
            self.async_button.config(state="normal")
            self.stop_button.config(state="disabled")

    def _start_progress_monitor(self):
        """启动进度监控线程"""

        def monitor_loop():
            while True:
                try:
                    response = requests.get(f"{self.api_url}/api/progress", timeout=2)

                    if response.status_code == 200:
                        progress = response.json()

                        # 更新状态
                        running = progress.get("running", False)
                        stage = progress.get("stage", "idle")
                        percentage = progress.get("percentage", 0)
                        current = progress.get("current", 0)
                        total = progress.get("total", 0)
                        query = progress.get("query", "")
                        message = progress.get("message", "")

                        # 更新UI
                        self.root.after(
                            0,
                            self._update_progress_ui,
                            running,
                            stage,
                            percentage,
                            current,
                            total,
                            query,
                            message,
                        )

                except:
                    pass

                import time

                time.sleep(2)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()

    def _update_progress_ui(
        self, running, stage, percentage, current, total, query, message
    ):
        """更新进度UI"""
        # 更新状态标签
        if running:
            self.status_label.config(text=f"运行中 - {stage}", foreground="green")
            self._set_ui_running(True)
        else:
            self.status_label.config(text="空闲", foreground="gray")
            self._set_ui_running(False)

        # 更新进度条
        self.progress_bar["value"] = percentage
        self.progress_label.config(text=f"{percentage}%")

        # 更新任务信息
        if running and query:
            self.task_info_label.config(
                text=f"关键词: {query} | 进度: {current}/{total} | {message}",
                foreground="black",
            )
        else:
            self.task_info_label.config(text="无任务", foreground="gray")

    def _log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _clear_log(self):
        """清空日志"""
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

    def _open_api_docs(self):
        """打开API文档"""
        import webbrowser

        webbrowser.open(f"{self.api_url}/docs")

    def _open_output_dir(self):
        """打开输出目录"""
        import subprocess
        from pathlib import Path

        # 尝试获取配置的输出目录
        try:
            response = requests.get(f"{self.api_url}/api/config", timeout=2)
            if response.status_code == 200:
                config = response.json()
                output_dir = config.get("output_dir", "")
                if output_dir:
                    output_path = Path(output_dir)
                    output_path.mkdir(parents=True, exist_ok=True)
                    subprocess.run(["explorer", str(output_path)])
                    return
        except:
            pass

        # 使用默认目录
        output_path = Path.home() / "PinterestScraper" / "output"
        output_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["explorer", str(output_path)])


if __name__ == "__main__":
    console = ScraperConsole()
    console.show()
