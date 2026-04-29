"""天津住宅户型图爬取管道（增量版 + 多源支持）

支持多个户型图源：
1. 3vjia - 主要来源
2. 酷家乐(kujiale) - 备用来源

三阶段管道：
1. 住建委 → 提取住宅项目备案名（自动跳过已completed）
2. 房天下 → 备案名转宣传名（只处理pending项目）
3. 多源户型图 → 用宣传名从多个源搜索并下载户型图

多源策略：
- 并行从多个源获取同一小区的户型图
- 合并去重（按image_url）
- 标记数据来源
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright

from scrapers.tj_gov_scraper import TJGovScraper
from scrapers.fang_scraper import FangScraper
from scrapers.sanvjia_scraper import SanvjiaScraper
from scrapers.kujiale_scraper import KujialeScraper
from scrapers.storage import ProjectStorage


class Pipeline:
    """天津住宅户型图三阶段爬取管道"""
    
    # 支持的户型图源
    FLOOR_PLAN_SOURCES = ["3vjia", "kujiale"]
    
    def __init__(self, output_dir: str = "./output/tianjin",
                 headless: bool = True, debug: bool = False,
                 cdp_endpoint: str = None, delay: float = 3.0,
                 sources: List[str] = None):
        """初始化管道
        
        Args:
            output_dir: 输出目录
            headless: 是否无头模式
            debug: 是否调试模式
            cdp_endpoint: Chrome DevTools Protocol端点
            delay: 请求间隔（秒）
            sources: 户型图源列表，默认全部（["3vjia", "kujiale"]）
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.debug = debug
        self.cdp_endpoint = cdp_endpoint
        self.delay = delay
        
        # 设置户型图源（默认全部）
        self.sources = sources or self.FLOOR_PLAN_SOURCES.copy()
        # 验证源名称
        invalid_sources = [s for s in self.sources if s not in self.FLOOR_PLAN_SOURCES]
        if invalid_sources:
            raise ValueError(f"不支持的户型图源: {invalid_sources}。支持的源: {self.FLOOR_PLAN_SOURCES}")
        
        self.storage = ProjectStorage(str(self.output_dir / "storage.json"))
        self.tj_gov_output = self.output_dir / "01_tj_gov_projects.json"
        self.fang_output = self.output_dir / "02_fang_mapping.json"
        
        # 多源输出路径
        self.source_outputs = {
            "3vjia": {
                "json": self.output_dir / "03_3vjia_results.json",
                "img_dir": self.output_dir / "floor_plans_3vjia",
            },
            "kujiale": {
                "json": self.output_dir / "03_kujiale_results.json",
                "img_dir": self.output_dir / "floor_plans_kujiale",
            },
        }
        
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
    
    def _start_browser(self):
        """启动浏览器"""
        self._playwright = sync_playwright().start()
        if self.cdp_endpoint:
            self._browser = self._playwright.chromium.connect_over_cdp(self.cdp_endpoint)
            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        else:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context(viewport={"width": 1920, "height": 1080})
            self._page = self._context.new_page()
        
        self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        print("[管道] 浏览器已启动，所有 stage 将复用同一实例")
    
    def _close_browser(self):
        """关闭浏览器"""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        print("[管道] 浏览器已关闭")
    
    def run(self, max_gov_pages: int = 100, max_plans_per_project: int = 20,
            days_limit: int = 0, max_projects_per_source: int = 40) -> Dict:
        """运行完整管道
        
        Args:
            max_gov_pages: 住建委最大翻页数
            max_plans_per_project: 每小区最大户型数
            days_limit: 只爬取近N天的项目（0表示默认90天）
            max_projects_per_source: 每个户型图源最大处理小区数
            
        Returns:
            统计信息字典
        """
        stats = {
            "stage1": {},
            "stage2": {},
            "stage3": {},
        }
        
        self._start_browser()
        
        try:
            # Stage 1: 爬取住建委住宅项目
            print("\n" + "=" * 60)
            print("Stage 1: 爬取天津住建委住宅项目")
            print("=" * 60)
            self.storage.print_stats()
            
            with TJGovScraper(
                headless=self.headless,
                debug=self.debug,
                cdp_endpoint=self.cdp_endpoint,
                page=self._page,
                storage=self.storage,
            ) as scraper:
                projects = scraper.fetch_all_residential_projects(
                    max_pages=max_gov_pages, days_limit=days_limit
                )
                scraper.save_results(projects, str(self.tj_gov_output))
                
                new_names = [p.clean_name for p in projects]
                self.storage.add_record_names(new_names)
                
                stats["stage1"] = {
                    "total_raw": len(projects),
                    "output_file": str(self.tj_gov_output),
                }
            
            # Stage 2: 备案名→宣传名转换
            print("\n" + "=" * 60)
            print("Stage 2: 备案名→宣传名转换")
            print("=" * 60)
            
            pending_names = self.storage.get_names_without_promo()
            print(f"[管道] 待转换备案名: {len(pending_names)} 个")
            
            if pending_names:
                with FangScraper(
                    page=self._page,
                    headless=self.headless,
                    debug=self.debug,
                    cdp_endpoint=self.cdp_endpoint,
                    delay=self.delay,
                ) as scraper:
                    mappings = scraper.convert_names(pending_names)
                    scraper.save_results(mappings, str(self.fang_output))
                    
                    for m in mappings:
                        if m.promo_name:
                            self.storage.update_promo_name(
                                m.record_name, m.promo_name, m.confidence, m.fang_url
                            )
                    
                    valid = [m for m in mappings if m.promo_name]
                    stats["stage2"] = {
                        "total_input": len(mappings),
                        "success": len(valid),
                        "failed": len(mappings) - len(valid),
                        "output_file": str(self.fang_output),
                    }
            else:
                print("[管道] 所有备案名已转换，跳过 Stage 2")
                stats["stage2"] = {"skipped": True}
            
            # Stage 3: 多源搜索并下载户型图（优先级策略）
            print("\n" + "=" * 60)
            print(f"Stage 3: 搜索并下载户型图（策略: 优先3vjia，失败用酷家乐兜底）")
            print("=" * 60)
            
            projects_to_download = []
            for name, proj in self.storage._data["projects"].items():
                if proj.get("status") in ("name_converted", "pending") and proj.get("promo_name"):
                    projects_to_download.append((name, proj["promo_name"]))
            
            print(f"[管道] 待下载户型图: {len(projects_to_download)} 个")
            
            if not projects_to_download:
                print("[管道] 无待下载项目，跳过 Stage 3")
                stats["stage3"] = {"skipped": True}
            else:
                # 限制处理数量
                limit = max_projects_per_source
                if len(projects_to_download) > limit:
                    skipped = projects_to_download[limit:]
                    projects_to_download = projects_to_download[:limit]
                    print(f"[管道] 本次限制处理 {limit} 个小区，剩余 {len(skipped)} 个留到下次")
                    for name, promo in skipped:
                        print(f"  [跳过] {name} ({promo})")
                
                # 按优先级策略获取户型图
                all_results = self._fetch_with_priority(
                    projects_to_download, max_plans_per_project
                )
                
                # 统计
                total_plans = sum(
                    sum(len(v) for v in r.get("results", {}).values())
                    for r in all_results.values()
                )
                total_downloaded = sum(
                    sum(r.get("downloads", {}).values())
                    for r in all_results.values()
                )
                
                print(f"\n[管道] 总计: {total_plans} 个户型，下载成功 {total_downloaded} 张")
                
                stats["stage3"] = {
                    "sources": list(all_results.keys()),
                    "total_projects": len(projects_to_download),
                    "total_plans": total_plans,
                    "downloaded": total_downloaded,
                    "source_details": {
                        source: {
                            "output_json": str(self.source_outputs[source]["json"]),
                            "output_dir": str(self.source_outputs[source]["img_dir"]),
                            "projects": len(r.get("results", {})),
                            "plans": sum(len(v) for v in r.get("results", {}).values()),
                            "downloaded": sum(r.get("downloads", {}).values()),
                        }
                        for source, r in all_results.items()
                    },
                }
        
        finally:
            self._close_browser()
        
        self._save_stats(stats)
        self._export_outputs()
        return stats
    
    def _fetch_with_priority(self, projects_to_download: List[Tuple[str, str]],
                              max_plans_per_project: int) -> Dict[str, Dict]:
        """按优先级策略获取户型图

        策略：
        1. 先用3vjia尝试获取每个小区的户型图
        2. 如果3vjia返回空或失败，再用酷家乐兜底
        3. 每个小区只从最多一个源获取，避免浪费

        Args:
            projects_to_download: [(备案名, 宣传名), ...]
            max_plans_per_project: 每小区最大户型数

        Returns:
            Dict[源名, {results: 结果, downloads: 下载统计}]
        """
        # 确定优先级顺序
        priority_order = []
        if "3vjia" in self.sources:
            priority_order.append("3vjia")
        if "kujiale" in self.sources:
            priority_order.append("kujiale")

        if not priority_order:
            print("[管道] 错误：没有可用的户型图源")
            return {}

        # 统计每个源处理的小区
        source_projects = {source: [] for source in priority_order}

        # 先用优先级最高的源尝试所有小区
        primary_source = priority_order[0]
        print(f"\n[管道] 优先使用 {primary_source} 获取户型图...")

        primary_results, primary_downloads = self._fetch_from_source(
            primary_source, projects_to_download, max_plans_per_project
        )

        source_projects[primary_source] = list(primary_results.keys())

        # 如果还有兜底源，处理失败的小区
        if len(priority_order) > 1:
            fallback_source = priority_order[1]

            # 找出在primary源中失败的小区
            failed_projects = [
                (record_name, promo_name)
                for record_name, promo_name in projects_to_download
                if promo_name not in primary_results or not primary_results.get(promo_name)
            ]

            if failed_projects:
                print(f"\n[管道] {primary_source} 未获取到 {len(failed_projects)} 个小区，"
                      f"使用 {fallback_source} 兜底...")

                fallback_results, fallback_downloads = self._fetch_from_source(
                    fallback_source, failed_projects, max_plans_per_project
                )

                source_projects[fallback_source] = list(fallback_results.keys())

                # 合并结果
                all_results = {
                    primary_source: {
                        "results": primary_results,
                        "downloads": primary_downloads,
                    },
                    fallback_source: {
                        "results": fallback_results,
                        "downloads": fallback_downloads,
                    },
                }
            else:
                print(f"[管道] {primary_source} 成功获取所有小区，无需兜底")
                all_results = {
                    primary_source: {
                        "results": primary_results,
                        "downloads": primary_downloads,
                    },
                }
        else:
            all_results = {
                primary_source: {
                    "results": primary_results,
                    "downloads": primary_downloads,
                },
            }

        # 打印汇总
        print("\n[管道] 数据来源汇总:")
        for source, projects in source_projects.items():
            if projects:
                print(f"  {source}: {len(projects)} 个小区")

        return all_results

    def _fetch_from_source(self, source: str, projects_to_download: List[Tuple[str, str]],
                           max_plans_per_project: int) -> tuple:
        """从指定源获取户型图

        Args:
            source: 源名称（3vjia/kujiale）
            projects_to_download: [(备案名, 宣传名), ...]
            max_plans_per_project: 每小区最大户型数

        Returns:
            (results_dict, downloads_dict)
        """
        promo_names = [p[1] for p in projects_to_download]
        record_map = {p[1]: p[0] for p in projects_to_download}

        if source == "3vjia":
            return self._fetch_from_3vjia(promo_names, record_map, max_plans_per_project)
        elif source == "kujiale":
            return self._fetch_from_kujiale(promo_names, record_map, max_plans_per_project)
        else:
            print(f"[管道] 未知源: {source}")
            return {}, {}
    
    def _fetch_from_3vjia(self, promo_names: List[str], record_map: Dict[str, str],
                          max_plans: int) -> Tuple[Dict, Dict]:
        """从3vjia获取户型图"""
        output_config = self.source_outputs["3vjia"]
        
        with SanvjiaScraper(
            headless=self.headless,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint,
            output_dir=str(output_config["img_dir"]),
            page=self._page,
        ) as scraper:
            results = scraper.search_floor_plans(promo_names, max_plans)
            scraper.save_results(results, str(output_config["json"]))
            
            # 更新storage
            for promo_name, plans in results.items():
                record_name = record_map.get(promo_name, promo_name)
                plan_dicts = [p.to_dict() for p in plans]
                # 添加来源标记
                for p in plan_dicts:
                    p["source"] = "3vjia"
                self.storage.add_floor_plans(record_name, plan_dicts)
            
            downloads = scraper.download_floor_plans(results)
            
            for promo_name, count in downloads.items():
                record_name = record_map.get(promo_name, promo_name)
                print(f"[存储] {record_name} (3vjia): 下载 {count} 张户型图")
            
            return results, downloads
    
    def _fetch_from_kujiale(self, promo_names: List[str], record_map: Dict[str, str],
                            max_plans: int) -> Tuple[Dict, Dict]:
        """从酷家乐获取户型图"""
        output_config = self.source_outputs["kujiale"]
        
        with KujialeScraper(
            headless=self.headless,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint,
            output_dir=str(output_config["img_dir"]),
            page=self._page,
            city_code="120100",  # 天津
        ) as scraper:
            results = scraper.search_floor_plans(promo_names, max_plans)
            scraper.save_results(results, str(output_config["json"]))
            
            # 更新storage
            for promo_name, plans in results.items():
                record_name = record_map.get(promo_name, promo_name)
                plan_dicts = [p.to_dict() for p in plans]
                # 添加来源标记
                for p in plan_dicts:
                    p["source"] = "kujiale"
                self.storage.add_floor_plans(record_name, plan_dicts)
            
            downloads = scraper.download_floor_plans(results)
            
            for promo_name, count in downloads.items():
                record_name = record_map.get(promo_name, promo_name)
                print(f"[存储] {record_name} (酷家乐): 下载 {count} 张户型图")
            
            return results, downloads
    
    def _export_outputs(self):
        """导出输出文件"""
        csv_path = self.output_dir / "projects.csv"
        md_path = self.output_dir / "projects.md"
        self.storage.export_csv(str(csv_path))
        self.storage.export_markdown(str(md_path))
        self.storage.print_stats()
    
    def _save_stats(self, stats: Dict):
        """保存统计信息"""
        stats_file = self.output_dir / "pipeline_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 60)
        print("管道执行完成!")
        print("=" * 60)
        print(f"Stage 1 (住建委): {stats['stage1'].get('total_raw', 0)} 个住宅项目")
        if not stats["stage2"].get("skipped"):
            print(f"Stage 2 (房天下): {stats['stage2'].get('success', 0)}/{stats['stage2'].get('total_input', 0)} 个转换成功")
        if not stats["stage3"].get("skipped"):
            print(f"Stage 3 (户型图): {stats['stage3'].get('downloaded', 0)}/{stats['stage3'].get('total_plans', 0)} 张户型图下载成功")
            print(f"  数据源: {', '.join(stats['stage3'].get('sources', []))}")
        
        print(f"\n输出目录: {self.output_dir}")
        print(f"  └─ storage.json (主数据)")
        print(f"  └─ projects.csv (表格视图)")
        print(f"  └─ projects.md (文档视图)")
        print(f"  └─ {self.tj_gov_output.name}")
        print(f"  └─ {self.fang_output.name}")
        for source in self.sources:
            config = self.source_outputs[source]
            print(f"  └─ {config['json'].name} ({source})")
            print(f"  └─ {config['img_dir'].name}/ ({source})")


def main():
    """CLI入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="天津住宅户型图三阶段爬取管道（增量版 + 多源支持）")
    parser.add_argument("--output-dir", default="output/tianjin", help="输出目录")
    parser.add_argument("--max-gov-pages", type=int, default=100, help="住建委最大翻页")
    parser.add_argument("--max-plans", type=int, default=20, help="每小区最大户型数")
    parser.add_argument("--max-projects", type=int, default=40, help="每个户型图源最大处理小区数")
    parser.add_argument("--sources", nargs="+", choices=Pipeline.FLOOR_PLAN_SOURCES,
                       default=Pipeline.FLOOR_PLAN_SOURCES,
                       help="户型图源列表（默认: 3vjia kujiale）")
    parser.add_argument("--connect", action="store_true", help="连接已有浏览器")
    parser.add_argument("--cdp-endpoint", default="http://localhost:9222")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--delay", type=float, default=3.0, help="请求间隔(秒)")
    args = parser.parse_args()
    
    pipeline = Pipeline(
        output_dir=args.output_dir,
        headless=not args.debug,
        debug=args.debug,
        cdp_endpoint=args.cdp_endpoint if args.connect else None,
        delay=args.delay,
        sources=args.sources,
    )
    
    stats = pipeline.run(
        max_gov_pages=args.max_gov_pages,
        max_plans_per_project=args.max_plans,
        max_projects_per_source=args.max_projects,
    )


if __name__ == "__main__":
    main()
