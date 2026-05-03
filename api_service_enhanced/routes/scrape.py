"""爬虫API路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import threading
import asyncio
from functools import partial

router = APIRouter()

task_manager = None


class ScrapeRequest(BaseModel):
    """爬虫请求参数"""

    query: str
    max_pins: int = 100
    min_saves: int = 0
    min_comments: int = 0
    output_dir: Optional[str] = None
    chrome_port: int = 9222
    chrome_profile: str = ""
    chrome_headless: bool = False
    debug: bool = False
    media_type: str = "all"
    download_images: bool = True
    climb_mode: bool = False
    use_folder_structure: bool = False
    enable_ai_filter: bool = True
    ai_filter_timeout: int = 180
    site: str = "pinterest"
    max_gov_pages: int = 100
    worker_id: Optional[str] = None
    proxy_server: Optional[str] = None


@router.post("/scrape")
async def scrape(req: ScrapeRequest):
    """同步爬取（阻塞，但不阻塞事件循环）"""
    if not task_manager:
        raise HTTPException(status_code=500, detail="Task manager not initialized")

    params = req.model_dump()

    if not params["output_dir"]:
        params["output_dir"] = "./output"

    worker_id = params.get("worker_id", "worker-0")
    print(f"[API] 开始同步爬取: {params['query']}, worker={worker_id}")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, partial(task_manager.run_scrape, params))

    print(f"[API] 爬取完成: {result.get('success', False)}, worker={worker_id}")

    if not result["success"]:
        raise HTTPException(
            status_code=500, detail=result.get("error", "Unknown error")
        )

    return result


@router.post("/scrape/async")
async def scrape_async(req: ScrapeRequest):
    """异步爬取（后台线程）"""
    if not task_manager:
        raise HTTPException(status_code=500, detail="Task manager not initialized")

    params = req.model_dump()

    if not params["output_dir"]:
        params["output_dir"] = "./output"

    worker_id = params.get("worker_id", "worker-0")
    print(f"[API] 开始异步爬取: {params['query']}, worker={worker_id}, AI筛选={params.get('enable_ai_filter', True)}")

    def _run_in_background():
        task_manager.run_scrape(params)

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": "Scrape task started in background",
        "query": params["query"],
        "worker_id": worker_id,
        "ai_filter_enabled": params.get("enable_ai_filter", True),
    }
