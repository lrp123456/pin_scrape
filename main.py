#!/usr/bin/env python3
"""Pinterest 搜索爬虫 - CLI 入口"""

import argparse
import time
import random
import os
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from scraper import PinterestScraper
from downloader import ImageDownloader
from output import save_json, save_filtered_json, save_all_pins_json

# 确保导入路径正确
sys.path.insert(0, str(Path(__file__).parent))

# 进度文件路径（由TaskManager通过环境变量传入）
PROGRESS_FILE = os.getenv("PROGRESS_FILE", "")


def update_progress(stage: str, current: int, total: int, message: str):
    """更新进度文件"""
    if not PROGRESS_FILE:
        return
    try:
        progress = {
            "running": True,
            "stage": stage,
            "percentage": int(current / total * 100) if total > 0 else 0,
            "current": current,
            "total": total,
            "query": "",
            "message": message,
            "start_time": datetime.now().isoformat(),
            "error": None,
        }
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False)
    except Exception as e:
        print(f"更新进度失败: {e}")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Pinterest 搜索爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 方式1: 连接到已有浏览器（推荐，可绑过反爬检测）
  # 首先以调试模式启动 Chrome:
  #   chrome.exe --remote-debugging-port=9222
  # 然后运行:
  python main.py -q "cat" -n 100 --connect

  # 方式2: 自动启动浏览器（可能被反爬检测）
  python main.py -q "cat" -n 100
  python main.py -q "dog" -n 200 --min-saves 50 --min-comments 10
        """,
    )

    parser.add_argument("-q", "--query", type=str, required=True, help="搜索关键词")

    parser.add_argument(
        "-n", "--max-pins", type=int, default=100, help="最大爬取数量 (默认: 100)"
    )

    parser.add_argument(
        "--min-saves", type=int, default=0, help="save数筛选阈值 (默认: 0，不筛选)"
    )

    parser.add_argument(
        "--min-likes", type=int, default=0, help="点赞数筛选阈值 (默认: 0，不筛选)"
    )

    parser.add_argument(
        "--min-comments", type=int, default=0, help="评论数筛选阈值 (默认: 0，不筛选)"
    )

    parser.add_argument(
        "--climb-mode",
        action="store_true",
        help="纯爬坡模式，忽视最小保存数，持续找更优",
    )

    parser.add_argument(
        "-o", "--output", type=str, default="./output", help="输出目录 (默认: ./output)"
    )

    parser.add_argument(
        "--no-headless", action="store_true", help="显示浏览器窗口 (默认为无头模式)"
    )

    parser.add_argument("--debug", action="store_true", help="调试模式，保存截图和HTML")

    parser.add_argument(
        "--connect", action="store_true", help="连接到已有的 Chrome 浏览器 (端口 9222)"
    )

    parser.add_argument(
        "--auto-launch",
        action="store_true",
        help="自动启动 Chrome 调试实例 (需配合 --connect 使用)",
    )

    parser.add_argument(
        "--chrome-profile",
        type=str,
        default=None,
        help="Chrome 用户数据目录路径（持久化登录状态）。如果不指定，使用临时配置",
    )

    parser.add_argument(
        "--cdp-endpoint",
        type=str,
        default="http://localhost:9222",
        help="Chrome DevTools Protocol 端点 (默认: http://localhost:9222)",
    )

    parser.add_argument(
        "--media-type",
        type=str,
        default="all",
        choices=["all", "images", "video"],
        help="媒体类型筛选 all/images/video (默认: all)",
    )

    return parser.parse_args()


def main():
    """主函数"""
    print("[main.py] 开始执行...")
    args = parse_args()
    print(
        f"[main.py] 参数解析完成: query={args.query}, max_pins={args.max_pins}, connect={args.connect}"
    )

    # 验证参数组合
    if args.auto_launch and not args.connect:
        print("错误: --auto-launch 必须配合 --connect 使用")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"搜索关键词: {args.query}")
    print(f"最大爬取数量: {args.max_pins}")
    print(
        f"筛选条件: saves >= {args.min_saves}, likes >= {args.min_likes}, comments >= {args.min_comments}"
    )
    print(f"输出目录: {output_dir}")
    print("-" * 50)

    # 确定 CDP 端点和 Chrome 启动策略
    chrome_launcher = None
    cdp_endpoint = None

    if args.auto_launch:
        # 自动启动 Chrome
        from chrome_launcher import ChromeLauncher

        try:
            chrome_launcher = ChromeLauncher(
                port=9222,
                timeout=10,
                user_data_dir=args.chrome_profile,
                headless=not args.no_headless,
            )
            chrome_launcher.__enter__()
            cdp_endpoint = chrome_launcher.endpoint

            if args.chrome_profile:
                print(f"已自动启动 Chrome (PID: {chrome_launcher.process.pid})")
                print(f"使用持久化配置: {args.chrome_profile}")
            else:
                print(
                    f"已自动启动 Chrome (PID: {chrome_launcher.process.pid}) [临时配置]"
                )

            print(f"CDP 端点: {cdp_endpoint}")
        except Exception as e:
            print(f"Chrome 启动失败: {e}")
            return 1
    elif args.connect:
        # 连接到已有 Chrome
        cdp_endpoint = args.cdp_endpoint
        print(f"[main.py] 连接到已有 Chrome: {cdp_endpoint}")
        print(f"CDP 端点: {cdp_endpoint}")

    try:
        # 爬取数据
        print(f"[main.py] 初始化爬虫, cdp_endpoint={cdp_endpoint}")
        with PinterestScraper(
            headless=not args.no_headless, debug=args.debug, cdp_endpoint=cdp_endpoint
        ) as scraper:
            print(f"[main.py] 爬虫初始化完成，开始搜索: {args.query}")
            update_progress("searching", 0, args.max_pins, f"正在搜索: {args.query}")

            pins = scraper.search(
                args.query,
                args.max_pins,
                args.min_saves,
                progress_callback=update_progress,
                climb_mode=args.climb_mode,
                media_type=args.media_type,
            )
            print(f"[main.py] 搜索完成，收集到 {len(pins)} 个Pin")

            if not pins:
                print("未爬取到任何数据")
                return 0

            total_pins = len(pins)

            if args.min_saves > 0:
                update_progress(
                    "completed",
                    total_pins,
                    total_pins,
                    f"探索完成，共收集 {total_pins} 个pin",
                )
            else:
                update_progress(
                    "enriching",
                    total_pins,
                    total_pins,
                    f"已完成，收集到 {total_pins} 个pin",
                )

            if args.min_saves == 0:
                update_progress(
                    "enriching",
                    0,
                    total_pins,
                    f"搜索完成，准备获取 {total_pins} 个详情...",
                )
                print(
                    f"\n正在获取 {total_pins} 个 Pin 的详情（saves/likes/comments）..."
                )
                for i, pin in enumerate(pins):
                    print(
                        f"  [{i + 1}/{total_pins}] 获取详情: {pin.title[:40] if pin.title else pin.id}"
                    )
                    details = scraper.fetch_pin_details(pin.id)
                    if details:
                        if details.get("title"):
                            pin.title = details["title"]
                        if details.get("description"):
                            pin.description = details["description"]
                        if details.get("saves", 0) is not None:
                            pin.saves = details["saves"]
                        if details.get("likes", 0) is not None:
                            pin.likes = details["likes"]
                        if details.get("comments", 0) is not None:
                            pin.comments = details["comments"]
                        if details.get("pinner"):
                            pin.pinner = details["pinner"]
                        saves_str = f"{pin.saves:,}" if pin.saves else "0"
                        likes_str = f"{pin.likes:,}" if pin.likes else "0"
                        comments_str = f"{pin.comments:,}" if pin.comments else "0"
                        print(
                            f"    Saves: {saves_str} | Likes: {likes_str} | Comments: {comments_str}"
                        )
                    else:
                        print(f"    无法获取详情")

                    # 每获取一个详情后更新进度
                    update_progress(
                        "enriching",
                        i + 1,
                        total_pins,
                        f"已获取 {i + 1}/{total_pins} 个详情",
                    )

                    time.sleep(random.uniform(1.5, 3))

        # 分离达标和不达标的pins
        qualified_pins = [p for p in pins if p.saves >= args.min_saves]

        # 保存完整数据（data.json包含所有pins，但统计显示达标数量）
        if args.min_saves > 0:
            save_all_pins_json(
                pins, qualified_pins, str(output_dir / "data.json"), args.query
            )
            # 单独保存达标pins
            if qualified_pins:
                save_json(
                    qualified_pins,
                    str(output_dir / "qualified_pins.json"),
                    args.query,
                )
                print(f"[main.py] 达标数据已保存: {len(qualified_pins)} 个")
        else:
            # 普通模式：保存所有pins
            save_json(pins, str(output_dir / "data.json"), args.query)

        # 更新进度：正在下载图片
        update_progress("downloading", 0, len(pins), "正在下载图片...")

        # 筛选并下载图片
        downloader = ImageDownloader(str(output_dir))
        filtered_pins = downloader.filter_and_download(
            pins,
            min_saves=args.min_saves,
            min_likes=args.min_likes,
            min_comments=args.min_comments,
        )

        # 保存筛选后的数据
        if filtered_pins:
            save_filtered_json(
                filtered_pins, str(output_dir / "filtered_data.json"), args.query
            )

        # 更新进度：任务完成
        update_progress(
            "completed", len(pins), len(pins), f"任务完成! 总数据: {len(pins)} 条"
        )

        print("-" * 50)
        print("爬取完成!")
        if args.min_saves > 0:
            print(f"达标数据: {len(qualified_pins)} 条 (min_saves={args.min_saves})")
            print(f"探索数据: {len(pins) - len(qualified_pins)} 条")
            print(f"总收集: {len(pins)} 条")
        else:
            print(f"总数据: {len(pins)} 条")
        print(f"筛选后: {len(filtered_pins)} 条")
        print(f"数据文件: {output_dir / 'data.json'}")
        if args.min_saves > 0 and qualified_pins:
            print(f"达标数据: {output_dir / 'qualified_pins.json'}")
        print(f"筛选数据: {output_dir / 'filtered_data.json'}")
        print(f"图片目录: {output_dir / 'images'}")
        print("[main.py] ✓ 所有任务完成，准备退出")

        print("[main.py] 退出，返回码: 0")
        return 0

    except Exception as e:
        print(f"[main.py] ✗ 发生异常: {e}")
        import traceback

        traceback.print_exc()
        update_progress("error", 0, 0, f"发生异常: {e}")
        return 1

    finally:
        # 清理 Chrome 进程
        if chrome_launcher:
            chrome_launcher.__exit__(None, None, None)
            print("已关闭 Chrome")


if __name__ == "__main__":
    sys.exit(main())
