"""测试命令构建和执行"""

import sys
import subprocess
from pathlib import Path

# 模拟 task_manager 中的命令构建
base_path = Path(__file__).parent  # 项目根目录
main_py = base_path / 'main.py'

# 测试参数
params = {
    'query': 'test',
    'max_pins': 5,
    'min_saves': 0,
    'min_likes': 0,
    'min_comments': 0,
    'output_dir': './output',
}

endpoint = "http://localhost:9222"

# 构建命令
cmd = [
    sys.executable,
    str(main_py),
    '--query', params['query'],
    '--max-pins', str(params.get('max_pins', 100)),
    '--min-saves', str(params.get('min_saves', 0)),
    '--min-likes', str(params.get('min_likes', 0)),
    '--min-comments', str(params.get('min_comments', 0)),
    '--output', params.get('output_dir', './output'),
    '--connect',
    '--cdp-endpoint', endpoint,
]

print("=" * 60)
print("测试命令构建")
print("=" * 60)
print(f"main.py 路径: {main_py}")
print(f"文件存在: {main_py.exists()}")
print(f"\n命令: {' '.join(cmd)}")
print("=" * 60)

# 尝试执行（会失败因为没有Chrome运行）
print("\n尝试执行命令（预期会失败，因为Chrome未运行）...")
try:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10
    )
    print(f"\n返回码: {result.returncode}")
    print(f"\nStdout:\n{result.stdout}")
    print(f"\nStderr:\n{result.stderr}")
except subprocess.TimeoutExpired:
    print("✗ 命令执行超时")
except Exception as e:
    print(f"✗ 执行失败: {e}")
