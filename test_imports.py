#!/usr/bin/env python3
"""测试所有导入是否正常"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

print("测试导入...")

try:
    print("1. 测试 shared.models...")
    from shared.models import Pin
    print("   ✓ shared.models 导入成功")
except Exception as e:
    print(f"   ✗ shared.models 导入失败: {e}")
    sys.exit(1)

try:
    print("2. 测试 scraper...")
    from scraper import PinterestScraper
    print("   ✓ scraper 导入成功")
except Exception as e:
    print(f"   ✗ scraper 导入失败: {e}")
    sys.exit(1)

try:
    print("3. 测试 downloader...")
    from downloader import ImageDownloader
    print("   ✓ downloader 导入成功")
except Exception as e:
    print(f"   ✗ downloader 导入失败: {e}")
    sys.exit(1)

try:
    print("4. 测试 output...")
    from output import save_json, save_filtered_json
    print("   ✓ output 导入成功")
except Exception as e:
    print(f"   ✗ output 导入失败: {e}")
    sys.exit(1)

try:
    print("5. 测试 main...")
    import main
    print("   ✓ main 导入成功")
except Exception as e:
    print(f"   ✗ main 导入失败: {e}")
    sys.exit(1)

print("\n✓ 所有导入测试通过！")
print("程序可以正常运行。")
