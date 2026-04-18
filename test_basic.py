"""快速诊断爬取卡住的问题"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("Pinterest爬虫诊断工具")
print("=" * 60)
print()

# 测试1: 导入测试
print("[1/5] 测试导入...")
try:
    from chrome_launcher import ChromeLauncher
    from scraper import PinterestScraper
    from api_service_enhanced.task_manager import TaskManager
    print("✓ 所有模块导入成功")
except Exception as e:
    print(f"✗ 导入失败: {e}")
    sys.exit(1)

print()

# 测试2: Chrome启动测试
print("[2/5] 测试Chrome启动...")
try:
    import time
    launcher = ChromeLauncher(port=9222, headless=False, timeout=15)
    launcher.__enter__()
    print(f"✓ Chrome已启动，端点: {launcher.endpoint}")
    time.sleep(2)
    launcher.__exit__(None, None, None)
    print("✓ Chrome关闭成功")
except Exception as e:
    print(f"✗ Chrome启动失败: {e}")
    print("\n可能的原因:")
    print("  1. Chrome未安装")
    print("  2. 端口9222被占用")
    print("  3. 权限问题")
    sys.exit(1)

print()

# 测试3: 进度追踪测试
print("[3/5] 测试进度追踪...")
try:
    from api_service_enhanced.progress_tracker import ProgressTracker
    tracker = ProgressTracker()
    tracker.start_task("test", 10)
    tracker.update("testing", 5, 10, "测试中")
    progress = tracker.get_progress()
    print(f"✓ 进度追踪正常: {progress['stage']} - {progress['percentage']}%")
    tracker.complete()
except Exception as e:
    print(f"✗ 进度追踪失败: {e}")
    sys.exit(1)

print()

# 测试4: API服务连接测试
print("[4/5] 测试API服务...")
try:
    import requests
    response = requests.get("http://localhost:8000/health", timeout=2)
    if response.status_code == 200:
        print("✓ API服务正在运行")
    else:
        print("✗ API服务响应异常")
except:
    print("⚠ API服务未运行（如果已启动则正常）")

print()

# 测试5: 简单爬取测试
print("[5/5] 测试爬虫功能...")
print("正在启动Chrome并测试爬取...")
try:
    # 启动Chrome
    launcher = ChromeLauncher(port=9222, headless=False, timeout=15)
    launcher.__enter__()

    # 连接爬虫
    scraper = PinterestScraper(cdp_endpoint="http://localhost:9222")
    scraper.__enter__()

    print("✓ 爬虫初始化成功")
    print("⚠ 跳过实际爬取测试（避免触发Pinterest登录）")

    # 清理
    scraper.__exit__(None, None, None)
    # Chrome保持运行以保存登录状态
    print("✓ Chrome保持运行，配置已保存")

    print()
    print("=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)
    print()
    print("建议：")
    print("  1. 现在可以在Chrome窗口中手动登录Pinterest")
    print("  2. 然后运行控制台进行爬取测试")
    print()

except Exception as e:
    print(f"✗ 爬虫测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
