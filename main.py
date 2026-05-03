#!/usr/bin/env python3
"""Pinterest 搜索爬虫 - CLI 入口

支持两种运行模式:
  1. 传统模式 (默认): 直接调用 scraper.py 中的 PinterestScraper
  2. 插件模式 (--use-plugin): 通过 core.engine 调度插件化架构
"""

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


def update_progress(
    stage: str, current: int, total: int, message: str, output_dir: str = "", collected_count: int = 0
):
    """更新进度文件"""
    if not PROGRESS_FILE:
        return
    try:
        # 尝试读取现有进度，保留 output_dir 和 collected_count
        existing_output_dir = output_dir
        existing_collected = collected_count
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
                existing_output_dir = existing.get("output_dir", output_dir)
                if collected_count == 0:
                    existing_collected = existing.get("collected_count", 0)
        except:
            pass

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
            "output_dir": existing_output_dir,
            "collected_count": existing_collected if collected_count == 0 else collected_count,
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
示例 (Pinterest):
  python main.py -q "现代简约" -n 100 --connect --auto-launch --chrome-profile ./data/chrome-profile

示例 (天津住宅户型图):
  python main.py --site tianjin --connect --auto-launch --chrome-profile ./data/chrome-profile
  python main.py --site tianjin --days-limit 90 --max-gov-pages 200 --connect --auto-launch
        """,
    )

    parser.add_argument("-q", "--query", type=str, default=None, help="搜索关键词 (Pinterest模式必填)")

    parser.add_argument(
        "-n", "--max-pins", type=int, default=100, help="最大爬取数量 (默认: 100)"
    )

    parser.add_argument(
        "--min-saves", type=int, default=0, help="save数筛选阈值 (默认: 0，不筛选)"
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

    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="日志文件路径 (默认: 不写入文件)",
    )

    parser.add_argument(
        "--no-ai-filter",
        dest="enable_ai_filter",
        action="store_false",
        help="禁用 AI 图片筛选。默认启用AI筛选，加此参数可关闭以排查崩溃是否与本地AI(Ollama)有关",
    )
    parser.set_defaults(enable_ai_filter=True)

    parser.add_argument(
        "--ai-filter-timeout",
        type=int,
        default=180,
        help="AI 筛选超时时间（秒）(默认: 180)",
    )

    parser.add_argument(
        "--site",
        type=str,
        default="pinterest",
        choices=["pinterest", "tianjin"],
        help="目标站点 (默认: pinterest)",
    )

    parser.add_argument(
        "--max-gov-pages",
        type=int,
        default=100,
        help="住建委最大翻页数 (仅tianjin站点)",
    )

    parser.add_argument(
        "--days-limit",
        type=int,
        default=0,
        help="只爬取近N天的住宅项目 (仅tianjin站点，0表示默认90天)",
    )

    parser.add_argument(
        "--max-projects",
        type=int,
        default=40,
        help="每个户型图源最大处理小区数 (仅tianjin站点，默认40)",
    )

    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["3vjia", "kujiale"],
        default=["3vjia", "kujiale"],
        help="户型图源列表 (仅tianjin站点，默认: 3vjia kujiale)",
    )

    # ── 多 Worker 参数 ──
    parser.add_argument(
        "--worker-id",
        type=str,
        default="worker-0",
        help="Worker 标识（多 Worker 模式时使用，如 worker-1）",
    )
    parser.add_argument(
        "--proxy-server",
        type=str,
        default=None,
        help="Chrome 代理服务器地址，如 socks5://proxy.example.com:1080",
    )

    parser.add_argument(
        "--use-plugin",
        action="store_true",
        help="使用插件化架构运行（新架构，core.engine 调度）",
    )

    return parser.parse_args()


def run_tianjin_pipeline(args):
    """运行天津住宅户型图三阶段管道"""
    print("[main.py] 启动天津住宅户型图管道...")

    if args.auto_launch and not args.connect:
        print("错误: --auto-launch 必须配合 --connect 使用")
        return 1

    sys.path.insert(0, str(Path(__file__).parent))
    from scrapers.pipeline import Pipeline

    chrome_launcher = None
    cdp_endpoint = None

    if args.auto_launch:
        from chrome_launcher import ChromeLauncher

        try:
            chrome_launcher = ChromeLauncher(
                port=9222,
                timeout=10,
                user_data_dir=args.chrome_profile,
                headless=not args.no_headless,
                proxy_server=args.proxy_server,
            )
            chrome_launcher.__enter__()
            cdp_endpoint = chrome_launcher.endpoint

            if chrome_launcher.process:
                if args.chrome_profile:
                    print(f"已自动启动 Chrome (PID: {chrome_launcher.process.pid}) [配置目录: {args.chrome_profile}]")
                else:
                    print(f"已自动启动 Chrome (PID: {chrome_launcher.process.pid}) [临时配置]")
            else:
                print("已连接到已有的 Chrome 实例")

            time.sleep(3)
        except Exception as e:
            print(f"自动启动 Chrome 失败: {e}")
            if chrome_launcher:
                chrome_launcher.__exit__(None, None, None)
            return 1
    elif args.connect:
        cdp_endpoint = args.cdp_endpoint
        print(f"连接到已有浏览器: {cdp_endpoint}")
    else:
        print("将自动启动临时浏览器实例（非连接模式）")

    pipeline = Pipeline(
        output_dir=args.output,
        headless=not args.no_headless,
        debug=args.debug,
        cdp_endpoint=cdp_endpoint,
        delay=3.0,
        sources=args.sources,
    )

    try:
        stats = pipeline.run(
            max_gov_pages=args.max_gov_pages,
            max_plans_per_project=20,
            days_limit=args.days_limit,
            max_projects_per_source=args.max_projects,
        )
    finally:
        if chrome_launcher:
            chrome_launcher.__exit__(None, None, None)

    return 0


def run_with_plugin(args):
    """使用插件化架构运行"""
    from core.engine import ScraperEngine, discover_plugins

    discover_plugins()

    engine = ScraperEngine()

    plugin_name = args.site
    task_config = {}

    if plugin_name == "pinterest":
        if not args.query:
            print("错误: Pinterest 模式必须提供 -q/--query 参数")
            return 1
        task_config = {
            "query": args.query,
            "max_pins": args.max_pins,
            "min_saves": args.min_saves,
            "climb_mode": args.climb_mode,
            "output_dir": args.output,
        }
    elif plugin_name == "tianjin":
        task_config = {
            "days_limit": args.days_limit,
            "max_gov_pages": args.max_gov_pages,
            "max_projects": args.max_projects,
            "sources": args.sources,
        }

    plugin_kwargs = {
        "headless": not args.no_headless,
        "debug": args.debug,
        "cdp_endpoint": args.cdp_endpoint if args.connect else None,
        "worker_id": args.worker_id,
    }

    try:
        engine.create_plugin(plugin_name, **plugin_kwargs)
        result = engine.run_task(plugin_name, task_config, progress_callback=update_progress)

        if result.status.value == "completed":
            print(f"[插件模式] 任务完成: 收集 {result.total_collected} 条")
            if result.output_dir:
                print(f"[插件模式] 输出目录: {result.output_dir}")
            return 0
        else:
            print(f"[插件模式] 任务失败: {result.error}")
            return 1
    except Exception as e:
        print(f"[插件模式] 异常: {e}")
        return 1
    finally:
        engine.shutdown()


def main():
    """主函数"""
    print("[main.py] 开始执行...")
    args = parse_args()

    if args.use_plugin:
        return run_with_plugin(args)

    if args.site == "tianjin":
        return run_tianjin_pipeline(args)

    # Pinterest 模式必须提供 --query
    if not args.query:
        print("错误: Pinterest 模式必须提供 -q/--query 参数")
        return 1

    print(
        f"[main.py] 参数解析完成: query={args.query}, max_pins={args.max_pins}, connect={args.connect}"
    )

    # 验证参数组合
    if args.auto_launch and not args.connect:
        print("错误: --auto-launch 必须配合 --connect 使用")
        return 1

    # 判断是否已包含时间戳子目录（API传入时已包含，CLI直接运行时需要创建）
    output_dir = Path(args.output)
    if "_20" not in output_dir.name:
        # CLI直接运行：创建带时间戳的子目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(
            c for c in args.query if c.isalnum() or c in (" ", "_", "-")
        ).strip().replace(" ", "_")
        output_dir = output_dir / f"{safe_query}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"搜索关键词: {args.query}")
    print(f"最大爬取数量: {args.max_pins}")
    print(
        f"筛选条件: saves >= {args.min_saves}, comments >= {args.min_comments}"
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
                proxy_server=args.proxy_server,
            )
            chrome_launcher.__enter__()
            cdp_endpoint = chrome_launcher.endpoint

            if chrome_launcher.process:
                if args.chrome_profile:
                    print(f"已自动启动 Chrome (PID: {chrome_launcher.process.pid})")
                    print(f"使用持久化配置: {args.chrome_profile}")
                else:
                    print(
                        f"已自动启动 Chrome (PID: {chrome_launcher.process.pid}) [临时配置]"
                    )
            else:
                print("已连接到已有的 Chrome 实例")

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
        # 确定日志文件路径
        log_file = args.log_file
        if log_file is None and output_dir:
            log_file = str(output_dir / "scraper.log")

        # 爬取数据
        print(f"[main.py] 初始化爬虫, cdp_endpoint={cdp_endpoint}")

        # 确定 user_data_dir：优先使用 args.chrome_profile，否则使用默认目录
        from chrome_launcher import ChromeLauncher
        user_data_dir = args.chrome_profile or str(ChromeLauncher.DEFAULT_PROFILE_DIR)

        with PinterestScraper(
            headless=not args.no_headless,
            debug=args.debug,
            cdp_endpoint=cdp_endpoint,
            log_file=log_file,
            user_data_dir=user_data_dir,
            enable_ai_filter=args.enable_ai_filter,
            ai_filter_timeout=args.ai_filter_timeout,
            worker_id=args.worker_id,
            proxy_server=args.proxy_server,
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
            
            # 更新进度：显示已收集数量
            update_progress(
                "collecting",
                len(pins),
                args.max_pins,
                f"搜索完成，已收集 {len(pins)} 个Pin",
                collected_count=len(pins),
            )

            if not pins:
                print("未爬取到任何数据")
                return 0

            total_pins = len(pins)

            if args.min_saves == 0:
                update_progress(
                    "enriching",
                    0,
                    total_pins,
                    f"搜索完成，准备获取 {total_pins} 个详情...",
                )
                print(
                    f"\n正在获取 {total_pins} 个 Pin 的详情（saves/comments）..."
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
                        if details.get("comments", 0) is not None:
                            pin.comments = details["comments"]
                        if details.get("pinner"):
                            pin.pinner = details["pinner"]
                        saves_str = f"{pin.saves:,}" if pin.saves else "0"
                        comments_str = f"{pin.comments:,}" if pin.comments else "0"
                        print(
                            f"    Saves: {saves_str} | Comments: {comments_str}"
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
        update_progress("downloading", 0, len(pins), "正在下载图片...", collected_count=len(pins))

        # 筛选并下载图片
        downloader = ImageDownloader(str(output_dir))
        filtered_pins = downloader.filter_and_download(
            pins,
            min_saves=args.min_saves,
            min_comments=args.min_comments,
        )

        # 保存筛选后的数据
        if filtered_pins:
            save_filtered_json(
                filtered_pins, str(output_dir / "filtered_data.json"), args.query
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
        
        # 更新进度为完成
        update_progress("completed", len(filtered_pins), len(filtered_pins), "任务完成", collected_count=len(pins))

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
