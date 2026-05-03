"""插件模式API路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

_engine = None


class PluginScrapeRequest(BaseModel):
    plugin_name: str
    task_config: dict = {}
    headless: bool = True
    debug: bool = False
    cdp_endpoint: Optional[str] = None
    worker_id: str = "worker-0"


@router.get("/plugins")
async def list_plugins():
    """列出所有已注册的插件"""
    from core.engine import list_plugins, discover_plugins

    discover_plugins()
    return {"plugins": list_plugins()}


@router.post("/plugins/scrape")
async def plugin_scrape(req: PluginScrapeRequest):
    """使用插件模式执行爬取"""
    from core.engine import ScraperEngine, discover_plugins

    discover_plugins()

    engine = ScraperEngine()
    try:
        engine.create_plugin(
            req.plugin_name,
            headless=req.headless,
            debug=req.debug,
            cdp_endpoint=req.cdp_endpoint,
            worker_id=req.worker_id,
        )
        result = engine.run_task(req.plugin_name, req.task_config)

        if result.status.value == "completed":
            return {
                "code": 200,
                "data": {
                    "total_collected": result.total_collected,
                    "output_dir": result.output_dir,
                    "items_count": len(result.items),
                },
                "msg": "任务完成",
            }
        else:
            return {
                "code": 500,
                "data": None,
                "msg": f"任务失败: {result.error}",
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        engine.shutdown()
