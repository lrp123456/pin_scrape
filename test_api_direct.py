"""直接测试API端点"""

import requests
import time

API_URL = "http://localhost:8000"

print("=" * 60)
print("测试 Pinterest Scraper API")
print("=" * 60)

# 1. 检查服务状态
print("\n[1] 检查服务状态...")
try:
    response = requests.get(f"{API_URL}/health", timeout=2)
    print(f"✓ API服务运行中: {response.status_code}")
except Exception as e:
    print(f"✗ API服务未运行: {e}")
    print("\n请先启动API服务:")
    print("  python api_service_enhanced/service_main.py")
    exit(1)

# 2. 检查Chrome状态
print("\n[2] 检查Chrome状态...")
try:
    response = requests.get(f"{API_URL}/api/status", timeout=2)
    status = response.json()
    print(f"Chrome运行状态: {status.get('chrome_running', False)}")
    print(f"当前任务: {status.get('task_running', False)}")
except Exception as e:
    print(f"✗ 无法获取状态: {e}")

# 3. 发送爬取请求
print("\n[3] 发送爬取请求...")
params = {
    'query': '简约风格',
    'max_pins': 5,
    'min_saves': 0,
    'min_likes': 0,
    'min_comments': 0,
    'output_dir': './output',
    'chrome_port': 9222,
    'chrome_headless': False,
}

print(f"参数: {params}")
print("开始爬取...")

start_time = time.time()
try:
    response = requests.post(
        f"{API_URL}/api/scrape",
        json=params,
        timeout=600  # 10分钟超时
    )
    elapsed = time.time() - start_time

    print(f"\n✓ 请求完成，耗时: {elapsed:.1f}秒")
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")

except requests.exceptions.Timeout:
    print(f"✗ 请求超时（600秒）")
except Exception as e:
    print(f"✗ 请求失败: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
