"""爬虫API路由"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import threading
import asyncio
from functools import partial

router = APIRouter()

# 全局实例（由service_main.py设置）
task_manager = None


class ScrapeRequest(BaseModel):
    """爬虫请求参数"""

    query: str
    max_pins: int = 100
    min_saves: int = 0
    min_likes: int = 0
    min_comments: int = 0
    output_dir: Optional[str] = None
    chrome_port: int = 9222
    chrome_profile: str = ""
    chrome_headless: bool = False
    debug: bool = False
    media_type: str = "all"  # all, images, videos
    download_images: bool = True
    climb_mode: bool = False
    use_folder_structure: bool = False


@router.post("/scrape")
async def scrape(req: ScrapeRequest):
    """同步爬取（阻塞，但不阻塞事件循环）

    Args:
        req: 爬虫请求参数

    Returns:
        爬取结果
    """
    if not task_manager:
        raise HTTPException(status_code=500, detail="Task manager not initialized")

    params = req.model_dump()

    # 设置默认输出目录
    if not params["output_dir"]:
        params["output_dir"] = "./output"

    print(f"[API] 开始同步爬取: {params['query']}, max_pins={params['max_pins']}")

    # 用线程池执行同步阻塞任务，避免阻塞 asyncio 事件循环
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, partial(task_manager.run_scrape, params))

    print(f"[API] 爬取完成: {result.get('success', False)}")

    if not result["success"]:
        raise HTTPException(
            status_code=500, detail=result.get("error", "Unknown error")
        )

    return result


@router.post("/scrape/async")
async def scrape_async(req: ScrapeRequest):
    """异步爬取（后台线程）

    Args:
        req: 爬虫请求参数

    Returns:
        任务启动确认
    """
    if not task_manager:
        raise HTTPException(status_code=500, detail="Task manager not initialized")

    params = req.model_dump()

    # 设置默认输出目录
    if not params["output_dir"]:
        params["output_dir"] = "./output"

    # 启动后台线程
    def _run_in_background():
        task_manager.run_scrape(params)

    thread = threading.Thread(target=_run_in_background, daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": "Scrape task started in background",
        "query": params["query"],
    }
