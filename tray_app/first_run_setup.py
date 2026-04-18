"""首次运行安装检查"""

import subprocess
import sys
from pathlib import Path


def check_playwright_driver() -> bool:
    """
    检查Playwright驱动是否已安装

    Returns:
        是否已安装
    """
    try:
        import playwright
        from playwright.sync_api import sync_playwright

        # 尝试启动Playwright检查驱动
        try:
            p = sync_playwright().start()
            p.stop()
            return True
        except Exception as e:
            print(f"Playwright驱动检查失败: {e}")
            return False

    except ImportError:
        print("Playwright库未安装")
        return False


def install_playwright_driver() -> bool:
    """
    安装Playwright驱动

    Returns:
        是否安装成功
    """
    print("=" * 60)
    print("首次运行检测")
    print("=" * 60)
    print()
    print("正在安装浏览器驱动组件...")
    print("这个过程只需要进行一次，大约需要1-2分钟")
    print()

    try:
        # 安装Playwright驱动
        result = subprocess.run(
            [sys.executable, '-m', 'playwright', 'install'],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )

        if result.returncode == 0:
            print()
            print("=" * 60)
            print("✓ 浏览器驱动安装成功！")
            print("=" * 60)
            print()
            return True
        else:
            print()
            print("=" * 60)
            print("✗ 安装失败")
            print("=" * 60)
            print(f"错误信息: {result.stderr}")
            print()
            print("请手动运行以下命令安装：")
            print("  python -m playwright install")
            return False

    except subprocess.TimeoutExpired:
        print("安装超时，请检查网络连接")
        return False
    except Exception as e:
        print(f"安装过程出错: {e}")
        return False


def ensure_playwright_ready() -> bool:
    """
    确保Playwright驱动已准备好

    Returns:
        是否准备就绪
    """
    if check_playwright_driver():
        return True

    # 未安装，尝试自动安装
    return install_playwright_driver()


if __name__ == "__main__":
    # 测试
    print("检查Playwright驱动...")
    if check_playwright_driver():
        print("✓ 已安装")
    else:
        print("✗ 未安装")
        print()
        install_playwright_driver()
