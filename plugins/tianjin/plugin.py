"""天津住宅户型图爬虫插件

实现 PipelinePlugin 接口，三阶段管道:
  1. 住建委 → 提取住宅项目备案名
  2. 房天下 → 备案名转宣传名
  3. 多源户型图 → 用宣传名搜索并下载户型图

复用现有 scrapers/ 目录下的爬虫实现。
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from core.plugin_interface import PipelinePlugin, PluginInfo, ScrapeResult, TaskStatus

logger = logging.getLogger(__name__)


class TianjinPlugin(PipelinePlugin):
    """天津住宅户型图管道插件"""

    STAGES = ["gov", "fang", "floor_plans"]

    def __init__(self, **kwargs):
        self.headless = kwargs.get("headless", True)
        self.debug = kwargs.get("debug", False)
        self.cdp_endpoint = kwargs.get("cdp_endpoint")
        self.delay = kwargs.get("delay", 3.0)
        self.sources = kwargs.get("sources", ["3vjia", "kujiale"])
        self.days_limit = kwargs.get("days_limit", 30)
        self.max_gov_pages = kwargs.get("max_gov_pages", 5)
        self.max_projects = kwargs.get("max_projects", 0)

        self._pipeline = None
        self._cancelled = False
        self._status: Dict[str, Any] = {"state": "idle"}

    @classmethod
    def info(cls) -> PluginInfo:
        return PluginInfo(
            name="tianjin",
            version="2.0.0",
            description="天津住宅户型图三阶段管道爬虫",
            supported_sites=["tj.gov.cn", "fang.com", "3vjia.com", "kujiale.com"],
            config_schema={
                "days_limit": {"type": "int", "default": 30},
                "max_gov_pages": {"type": "int", "default": 5},
                "max_projects": {"type": "int", "default": 0},
                "sources": {"type": "list", "default": ["3vjia", "kujiale"]},
            },
        )

    @classmethod
    def validate_config(cls, config: Dict[str, Any]) -> bool:
        return True

    @classmethod
    def default_config(cls) -> Dict[str, Any]:
        return {
            "days_limit": 30,
            "max_gov_pages": 5,
            "max_projects": 0,
            "sources": ["3vjia", "kujiale"],
            "headless": True,
            "debug": False,
        }

    def start(self) -> None:
        from scrapers.pipeline import Pipeline
        self._pipeline = Pipeline(
            headless=self.headless,
            debug=self.debug,
            cdp_endpoint=self.cdp_endpoint,
            delay=self.delay,
            sources=self.sources,
        )
        self._status = {"state": "ready"}
        logger.info("天津住宅插件已启动")

    def stop(self) -> None:
        self._pipeline = None
        self._status = {"state": "stopped"}
        logger.info("天津住宅插件已停止")

    def get_stages(self) -> List[str]:
        return self.STAGES

    def run_stage(self, stage_name: str, task_config: Dict[str, Any],
                  progress_callback: Optional[Callable] = None) -> ScrapeResult:
        if not self._pipeline:
            return ScrapeResult(status=TaskStatus.FAILED, error="管道未初始化")

        try:
            if stage_name == "gov":
                return self._run_gov_stage(task_config, progress_callback)
            elif stage_name == "fang":
                return self._run_fang_stage(task_config, progress_callback)
            elif stage_name == "floor_plans":
                return self._run_floor_plans_stage(task_config, progress_callback)
            else:
                return ScrapeResult(status=TaskStatus.FAILED, error=f"未知阶段: {stage_name}")
        except Exception as e:
            logger.error(f"阶段 {stage_name} 失败: {e}")
            return ScrapeResult(status=TaskStatus.FAILED, error=str(e))

    def _run_gov_stage(self, task_config: Dict, callback: Optional[Callable]) -> ScrapeResult:
        from scrapers.tj_gov_scraper import TJGovScraper
        from scrapers.storage import ProjectStorage

        storage = ProjectStorage()
        with TJGovScraper(
            headless=self.headless, debug=self.debug,
            cdp_endpoint=self.cdp_endpoint
        ) as scraper:
            projects = scraper.scrape(
                days_limit=self.days_limit,
                max_pages=self.max_gov_pages,
                max_projects=self.max_projects,
            )
            for proj in projects:
                storage.save_project(proj)

        return ScrapeResult(
            items=[vars(p) if hasattr(p, "__dict__") else p for p in projects],
            total_collected=len(projects),
            status=TaskStatus.COMPLETED,
        )

    def _run_fang_stage(self, task_config: Dict, callback: Optional[Callable]) -> ScrapeResult:
        from scrapers.fang_scraper import FangScraper
        from scrapers.storage import ProjectStorage

        storage = ProjectStorage()
        pending = storage.get_pending_projects()

        if not pending:
            return ScrapeResult(status=TaskStatus.COMPLETED, items=[], total_collected=0)

        with FangScraper(
            headless=self.headless, debug=self.debug,
            cdp_endpoint=self.cdp_endpoint, delay=self.delay
        ) as scraper:
            mappings = scraper.search_all([p.get("record_name", "") for p in pending])

        for m in mappings:
            if m.promo_name:
                storage.update_promo_name(m.record_name, m.promo_name, m.fang_url)

        return ScrapeResult(
            items=[vars(m) if hasattr(m, "__dict__") else m for m in mappings if m.promo_name],
            total_collected=sum(1 for m in mappings if m.promo_name),
            status=TaskStatus.COMPLETED,
        )

    def _run_floor_plans_stage(self, task_config: Dict, callback: Optional[Callable]) -> ScrapeResult:
        from scrapers.pipeline import Pipeline

        if not self._pipeline:
            return ScrapeResult(status=TaskStatus.FAILED, error="管道未初始化")

        results = self._pipeline.run_floor_plan_stage()
        return ScrapeResult(
            items=results if isinstance(results, list) else [],
            total_collected=len(results) if isinstance(results, list) else 0,
            status=TaskStatus.COMPLETED,
        )

    def run(self, task_config: Dict[str, Any],
            progress_callback: Optional[Callable] = None) -> ScrapeResult:
        if not self._pipeline:
            self.start()

        try:
            self._pipeline.run()
            self._status = {"state": "completed"}
            return ScrapeResult(status=TaskStatus.COMPLETED)
        except Exception as e:
            self._status = {"state": "failed", "error": str(e)}
            return ScrapeResult(status=TaskStatus.FAILED, error=str(e))

    def get_status(self) -> Dict[str, Any]:
        return self._status.copy()

    def cancel(self) -> None:
        self._cancelled = True
        self._status = {"state": "cancelled"}
