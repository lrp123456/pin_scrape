"""可视化配置GUI"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import json


class ConfigGUI:
    """配置窗口GUI"""

    def __init__(self, config_manager):
        """
        初始化配置GUI

        Args:
            config_manager: 配置管理器
        """
        self.config_manager = config_manager
        self.root = None

    def show(self):
        """显示配置窗口"""
        # 创建主窗口
        self.root = tk.Tk()
        self.root.title("Pinterest Scraper 配置")
        self.root.geometry("600x700")
        self.root.resizable(False, False)

        # 设置窗口图标（如果有）
        try:
            icon_path = Path(__file__).parent / "assets" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass

        # 创建主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # 创建配置分类
        self._create_widgets(main_frame)

        # 加载当前配置
        self._load_config()

        # 运行窗口
        self.root.mainloop()

    def _create_widgets(self, parent):
        """创建配置组件"""
        row = 0

        # 标题
        title_label = ttk.Label(
            parent, text="Pinterest Scraper 配置面板", font=("Arial", 14, "bold")
        )
        title_label.grid(row=row, column=0, columnspan=2, pady=10)
        row += 1

        # === 查询参数部分 ===
        query_frame = ttk.LabelFrame(parent, text="查询参数", padding="10")
        query_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1

        # 查询关键词
        ttk.Label(query_frame, text="搜索关键词:").grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.query_entry = ttk.Entry(query_frame, width=40)
        self.query_entry.grid(row=0, column=1, sticky="ew", pady=5)

        # 最大数量
        ttk.Label(query_frame, text="最大爬取数量:").grid(
            row=1, column=0, sticky="w", pady=5
        )
        self.max_pins_spinbox = ttk.Spinbox(
            query_frame, from_=10, to=1000, increment=10, width=38
        )
        self.max_pins_spinbox.grid(row=1, column=1, sticky="ew", pady=5)

        # 最小保存数
        ttk.Label(query_frame, text="最小保存数阈值:").grid(
            row=2, column=0, sticky="w", pady=5
        )
        self.min_saves_spinbox = ttk.Spinbox(
            query_frame, from_=0, to=10000, increment=10, width=38
        )
        self.min_saves_spinbox.grid(row=2, column=1, sticky="ew", pady=5)

        # 最小点赞数
        ttk.Label(query_frame, text="最小点赞数阈值:").grid(
            row=3, column=0, sticky="w", pady=5
        )
        self.min_likes_spinbox = ttk.Spinbox(
            query_frame, from_=0, to=10000, increment=10, width=38
        )
        self.min_likes_spinbox.grid(row=3, column=1, sticky="ew", pady=5)

        # 最小评论数
        ttk.Label(query_frame, text="最小评论数阈值:").grid(
            row=4, column=0, sticky="w", pady=5
        )
        self.min_comments_spinbox = ttk.Spinbox(
            query_frame, from_=0, to=10000, increment=10, width=38
        )
        self.min_comments_spinbox.grid(row=4, column=1, sticky="ew", pady=5)

        # === 服务配置部分 ===
        service_frame = ttk.LabelFrame(parent, text="服务配置", padding="10")
        service_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1

        # API端口
        ttk.Label(service_frame, text="API服务端口:").grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.api_port_spinbox = ttk.Spinbox(
            service_frame, from_=1024, to=65535, increment=1, width=38
        )
        self.api_port_spinbox.grid(row=0, column=1, sticky="ew", pady=5)

        # 输出目录
        ttk.Label(service_frame, text="输出目录:").grid(
            row=1, column=0, sticky="w", pady=5
        )
        output_frame = ttk.Frame(service_frame)
        output_frame.grid(row=1, column=1, sticky="ew", pady=5)

        self.output_dir_entry = ttk.Entry(output_frame, width=30)
        self.output_dir_entry.pack(side="left", fill="x", expand=True)

        ttk.Button(
            output_frame, text="浏览", command=self._browse_output_dir, width=8
        ).pack(side="right", padx=(5, 0))

        # === Chrome配置部分 ===
        chrome_frame = ttk.LabelFrame(parent, text="Chrome配置", padding="10")
        chrome_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1

        # Chrome端口
        ttk.Label(chrome_frame, text="Chrome调试端口:").grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.chrome_port_spinbox = ttk.Spinbox(
            chrome_frame, from_=1024, to=65535, increment=1, width=38
        )
        self.chrome_port_spinbox.grid(row=0, column=1, sticky="ew", pady=5)

        # 无头模式
        self.chrome_headless_var = tk.BooleanVar()
        ttk.Checkbutton(
            chrome_frame,
            text="无头模式（后台运行，不显示浏览器窗口）",
            variable=self.chrome_headless_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)

        # Redis配置
        redis_frame = ttk.LabelFrame(parent, text="Redis配置", padding="10")
        redis_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1

        ttk.Label(redis_frame, text="Redis主机:").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.redis_host_entry = ttk.Entry(redis_frame, width=38)
        self.redis_host_entry.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(redis_frame, text="Redis端口:").grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.redis_port_spinbox = ttk.Spinbox(
            redis_frame, from_=6379, to=6389, increment=1, width=36
        )
        self.redis_port_spinbox.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(redis_frame, text="Redis数据库:").grid(
            row=2, column=0, sticky="w", pady=2
        )
        self.redis_db_spinbox = ttk.Spinbox(
            redis_frame, from_=0, to=15, increment=1, width=36
        )
        self.redis_db_spinbox.grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(redis_frame, text="Redis密码:").grid(
            row=3, column=0, sticky="w", pady=2
        )
        self.redis_password_entry = ttk.Entry(redis_frame, width=38, show="*")
        self.redis_password_entry.grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Label(
            redis_frame,
            text="提示：留空表示使用默认配置",
            font=("Arial", 8),
            foreground="gray",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(5, 0))

        # Chrome配置目录
        ttk.Label(chrome_frame, text="Chrome配置目录:").grid(
            row=2, column=0, sticky="w", pady=5
        )
        profile_frame = ttk.Frame(chrome_frame)
        profile_frame.grid(row=2, column=1, sticky="ew", pady=5)

        self.chrome_profile_entry = ttk.Entry(profile_frame, width=30)
        self.chrome_profile_entry.pack(side="left", fill="x", expand=True)

        ttk.Button(
            profile_frame, text="浏览", command=self._browse_chrome_profile, width=8
        ).pack(side="right", padx=(5, 0))

        ttk.Label(
            chrome_frame,
            text="提示：配置目录用于保存登录状态，留空则每次重新登录",
            font=("Arial", 8),
            foreground="gray",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=2)

        # === 其他设置 ===
        other_frame = ttk.LabelFrame(parent, text="其他设置", padding="10")
        other_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)
        row += 1

        # 自定义图标
        ttk.Label(other_frame, text="自定义图标:").grid(
            row=0, column=0, sticky="w", pady=5
        )
        icon_frame = ttk.Frame(other_frame)
        icon_frame.grid(row=0, column=1, sticky="ew", pady=5)

        self.icon_path_entry = ttk.Entry(icon_frame, width=30)
        self.icon_path_entry.pack(side="left", fill="x", expand=True)

        ttk.Button(icon_frame, text="浏览", command=self._browse_icon, width=8).pack(
            side="right", padx=(5, 0)
        )

        # 开机自启
        self.auto_start_var = tk.BooleanVar()
        ttk.Checkbutton(
            other_frame, text="开机自动启动", variable=self.auto_start_var
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)

        # === 按钮部分 ===
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=2, pady=20)
        row += 1

        ttk.Button(
            button_frame, text="保存配置", command=self._save_config, width=15
        ).pack(side="left", padx=5)
        ttk.Button(
            button_frame, text="重置默认", command=self._reset_config, width=15
        ).pack(side="left", padx=5)
        ttk.Button(button_frame, text="取消", command=self._cancel, width=15).pack(
            side="left", padx=5
        )

        # === 说明文本 ===
        help_text = """
提示：
• 查询参数设置爬虫的默认搜索条件
• Chrome配置目录留空则每次需要重新登录Pinterest
• API端口修改后需要重启服务
• 配置保存在：%APPDATA%\\PinterestScraper\\config.json
        """
        ttk.Label(parent, text=help_text, justify="left", foreground="gray").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=10
        )

    def _load_config(self):
        """加载当前配置"""
        config = self.config_manager.config

        # 查询参数
        self.query_entry.insert(0, config.get("default_query", ""))
        self.max_pins_spinbox.delete(0, tk.END)
        self.max_pins_spinbox.insert(0, config.get("default_max_pins", 100))
        self.min_saves_spinbox.delete(0, tk.END)
        self.min_saves_spinbox.insert(0, config.get("default_min_saves", 0))
        self.min_likes_spinbox.delete(0, tk.END)
        self.min_likes_spinbox.insert(0, config.get("default_min_likes", 0))
        self.min_comments_spinbox.delete(0, tk.END)
        self.min_comments_spinbox.insert(0, config.get("default_min_comments", 0))

        # 服务配置
        self.api_port_spinbox.delete(0, tk.END)
        self.api_port_spinbox.insert(0, config.get("api_port", 8000))
        self.output_dir_entry.insert(0, config.get("output_dir", ""))

        # Chrome配置
        self.chrome_port_spinbox.delete(0, tk.END)
        self.chrome_port_spinbox.insert(0, config.get("chrome_port", 9222))
        self.chrome_headless_var.set(config.get("chrome_headless", False))
        self.chrome_profile_entry.insert(0, config.get("chrome_profile", ""))

        # 其他设置
        self.icon_path_entry.insert(0, config.get("custom_icon_path", ""))

        # Redis配置
        self.redis_host_entry.insert(0, config.get("redis_host", "localhost"))
        self.redis_port_spinbox.insert(0, config.get("redis_port", 6379))
        self.redis_db_spinbox.insert(0, config.get("redis_db", 0))
        self.redis_password_entry.insert(0, config.get("redis_password", ""))

        self.auto_start_var.set(self.config_manager.is_autostart())

    def _save_config(self):
        """保存配置"""
        try:
            # 获取所有配置值
            config_updates = {
                "default_query": self.query_entry.get().strip(),
                "default_max_pins": int(self.max_pins_spinbox.get()),
                "default_min_saves": int(self.min_saves_spinbox.get()),
                "default_min_likes": int(self.min_likes_spinbox.get()),
                "default_min_comments": int(self.min_comments_spinbox.get()),
                "api_port": int(self.api_port_spinbox.get()),
                "output_dir": self.output_dir_entry.get().strip(),
                "chrome_port": int(self.chrome_port_spinbox.get()),
                "chrome_headless": self.chrome_headless_var.get(),
                "chrome_profile": self.chrome_profile_entry.get().strip(),
                "custom_icon_path": self.icon_path_entry.get().strip(),
            }

            # 验证路径
            output_dir = config_updates["output_dir"]
            if output_dir:
                Path(output_dir).mkdir(parents=True, exist_ok=True)

            # Redis配置
            redis_updates = {
                "redis_host": self.redis_host_entry.get().strip(),
                "redis_port": int(self.redis_port_spinbox.get()),
                "redis_db": int(self.redis_db_spinbox.get()),
                "redis_password": self.redis_password_entry.get().strip(),
            }

            # 更新配置
            for key, value in {**config_updates, **redis_updates}.items():
                self.config_manager.set(key, value)

            # 设置开机自启
            auto_start = self.auto_start_var.get()
            self.config_manager.set_autostart(auto_start)

            messagebox.showinfo("成功", "配置已保存！\n部分设置需要重启服务生效。")
            self.root.destroy()

        except ValueError as e:
            messagebox.showerror("错误", f"配置值无效：{str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败：{str(e)}")

    def _reset_config(self):
        """重置为默认配置"""
        if messagebox.askyesno("确认", "确定要重置所有配置为默认值吗？"):
            self.config_manager.config = self.config_manager.DEFAULT_CONFIG.copy()
            self.config_manager._save_config()
            self._load_config()
            messagebox.showinfo("成功", "配置已重置为默认值")

    def _cancel(self):
        """取消"""
        self.root.destroy()

    def _browse_output_dir(self):
        """浏览输出目录"""
        dir_path = filedialog.askdirectory(title="选择输出目录")
        if dir_path:
            self.output_dir_entry.delete(0, tk.END)
            self.output_dir_entry.insert(0, dir_path)

    def _browse_chrome_profile(self):
        """浏览Chrome配置目录"""
        dir_path = filedialog.askdirectory(title="选择Chrome配置目录")
        if dir_path:
            self.chrome_profile_entry.delete(0, tk.END)
            self.chrome_profile_entry.insert(0, dir_path)

    def _browse_icon(self):
        """浏览图标文件"""
        file_path = filedialog.askopenfilename(
            title="选择图标文件",
            filetypes=[
                ("图标文件", "*.ico"),
                ("图片文件", "*.png *.jpg *.jpeg *.bmp"),
                ("所有文件", "*.*"),
            ],
        )
        if file_path:
            self.icon_path_entry.delete(0, tk.END)
            self.icon_path_entry.insert(0, file_path)


if __name__ == "__main__":
    # 测试GUI
    import sys
    from pathlib import Path

    # 添加项目路径
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from tray_app.config_manager import ConfigManager

    config_manager = ConfigManager()
    gui = ConfigGUI(config_manager)
    gui.show()
