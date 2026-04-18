"""
Pinterest Scraper - n8n 集成示例

此脚本展示如何在 n8n 工作流中调用 Pinterest 爬虫
"""

import sys
import json
import argparse
from pathlib import Path

# 添加 pinterest-scraper 到路径
sys.path.insert(0, '/home/node/scripts/pinterest-scraper')

from main import main as scraper_main


def run_scraper_for_n8n(
    query: str,
    max_pins: int = 100,
    output_dir: str = "/tmp/results/pinterest",
    chrome_profile: str = "/home/node/.chrome-profile",
    min_saves: int = 0,
    min_likes: int = 0,
    min_comments: int = 0
) -> dict:
    """
    为 n8n 工作流运行 Pinterest 爬虫

    Args:
        query: 搜索关键词
        max_pins: 最大爬取数量
        output_dir: 输出目录
        chrome_profile: Chrome 配置目录（持久化登录状态）
        min_saves: 最小 save 数筛选
        min_likes: 最小点赞数筛选
        min_comments: 最小评论数筛选

    Returns:
        包含结果信息的字典
    """
    import sys

    # 保存原始 sys.argv
    original_argv = sys.argv

    try:
        # 构造命令行参数
        sys.argv = [
            'main.py',
            '-q', query,
            '-n', str(max_pins),
            '--connect',
            '--auto-launch',
            '--chrome-profile', chrome_profile,
            '-o', output_dir,
            '--min-saves', str(min_saves),
            '--min-likes', str(min_likes),
            '--min-comments', str(min_comments)
        ]

        # 运行爬虫
        exit_code = scraper_main()

        # 读取结果
        output_path = Path(output_dir)
        data_file = output_path / "data.json"

        if data_file.exists():
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return {
                "success": True,
                "exit_code": exit_code,
                "total_pins": data.get('total_pins', 0),
                "main_pins": data.get('main_pins', 0),
                "similar_pins": data.get('similar_pins', 0),
                "filtered_pins": data.get('filtered_pins', 0),
                "output_file": str(data_file),
                "data": data
            }
        else:
            return {
                "success": False,
                "error": "输出文件不存在",
                "exit_code": exit_code
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exit_code": 1
        }

    finally:
        # 恢复原始 sys.argv
        sys.argv = original_argv


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pinterest Scraper for n8n')
    parser.add_argument('--query', required=True, help='搜索关键词')
    parser.add_argument('--max-pins', type=int, default=100, help='最大爬取数量')
    parser.add_argument('--output', default='/tmp/results/pinterest', help='输出目录')
    parser.add_argument('--chrome-profile', default='/home/node/.chrome-profile', help='Chrome 配置目录')
    parser.add_argument('--min-saves', type=int, default=0, help='最小 save 数')
    parser.add_argument('--min-likes', type=int, default=0, help='最小点赞数')
    parser.add_argument('--min-comments', type=int, default=0, help='最小评论数')

    args = parser.parse_args()

    result = run_scraper_for_n8n(
        query=args.query,
        max_pins=args.max_pins,
        output_dir=args.output,
        chrome_profile=args.chrome_profile,
        min_saves=args.min_saves,
        min_likes=args.min_likes,
        min_comments=args.min_comments
    )

    # 输出 JSON 结果给 n8n
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 返回退出码
    sys.exit(0 if result['success'] else 1)
