"""简单导入测试"""

print("测试1: 导入 chrome_launcher...")
try:
    from chrome_launcher import ChromeLauncher
    print("✓ chrome_launcher 导入成功")
except Exception as e:
    print(f"✗ chrome_launcher 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试2: 导入 progress_tracker...")
try:
    from api_service_enhanced.progress_tracker import ProgressTracker
    print("✓ progress_tracker 导入成功")
except Exception as e:
    print(f"✗ progress_tracker 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试3: 导入 chrome_manager...")
try:
    from api_service_enhanced.chrome_manager import ChromeManager
    print("✓ chrome_manager 导入成功")
except Exception as e:
    print(f"✗ chrome_manager 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试4: 导入 task_manager...")
try:
    from api_service_enhanced.task_manager import TaskManager
    print("✓ task_manager 导入成功")
except Exception as e:
    print(f"✗ task_manager 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n测试5: 导入 service_main...")
try:
    from api_service_enhanced.service_main import app
    print("✓ service_main 导入成功")
except Exception as e:
    print(f"✗ service_main 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n所有导入测试完成！")
