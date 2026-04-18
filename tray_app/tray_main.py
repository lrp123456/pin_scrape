"""托盘应用入口"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import pystray
from tray_app.tray_icon import TrayIconManager
from tray_app.process_manager import ProcessManager
from tray_app.config_manager import ConfigManager
from tray_app.first_run_setup import ensure_playwright_ready


def main():
    """托盘应用主函数"""

    # 首次运行检查：确保Playwright驱动已安装
    if not ensure_playwright_ready():
        print("警告：Playwright驱动安装失败，某些功能可能无法使用")
        print("请手动运行: python -m playwright install")

    # 获取应用数据目录
    app_data = Path.home() / 'AppData' / 'Roaming'
    config_dir = app_data / 'PinterestScraper'
    config_dir.mkdir(parents=True, exist_ok=True)

    # 初始化配置管理器
    config_manager = ConfigManager(config_dir / 'config.json')

    # 初始化进程管理器
    process_manager = ProcessManager(config_manager)

    # 初始化托盘图标管理器
    icon_manager = TrayIconManager(process_manager, config_manager)

    # 创建托盘图标
    icon = pystray.Icon(
        'Pinterest Scraper',
        icon_manager.get_icon(),
        menu=None  # 菜单将在setup_menu中设置
    )

    # 设置菜单
    icon_manager.setup_menu(icon)

    # 检查开机自启
    if config_manager.is_autostart():
        print("开机自启已启用")

    # 运行托盘应用
    print("Pinterest Scraper托盘应用启动")
    icon.run()


if __name__ == "__main__":
    main()
