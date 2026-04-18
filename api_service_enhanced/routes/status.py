"""状态查询路由"""

from fastapi import APIRouter

router = APIRouter()

# 全局实例（由service_main.py设置）
progress_tracker = None


@router.get("/progress")
async def get_progress():
    """获取当前任务进度

    Returns:
        进度信息
    """
    if not progress_tracker:
        return {
            "running": False,
            "stage": "idle",
            "percentage": 0,
            "message": "服务未初始化",
        }

    return progress_tracker.get_progress()


@router.get("/status")
async def get_status():
    """获取服务状态

    Returns:
        服务状态信息
    """
    if not progress_tracker:
        return {
            "running": False,
            "stage": "idle",
            "percentage": 0,
            "message": "服务未初始化",
        }

    progress = progress_tracker.get_progress()
    return {
        "running": progress["running"],
        "stage": progress["stage"],
        "percentage": progress["percentage"],
        "query": progress["query"],
        "message": progress["message"],
    }


@router.get("/health")
async def health_check():
    """健康检查

    Returns:
        健康状态
    """
    return {"status": "ok"}


@router.post("/shutdown")
async def shutdown():
    """关闭服务

    Returns:
        关闭确认
    """
    import asyncio
    import os
    import signal

    # 发送SIGTERM给自己
    def delayed_shutdown():
        os.kill(os.getpid(), signal.SIGTERM)

    # 延迟100ms执行，让HTTP响应先返回
    loop = asyncio.get_event_loop()
    loop.call_later(0.1, delayed_shutdown)

    return {"status": "shutting_down", "message": "服务正在关闭"}
