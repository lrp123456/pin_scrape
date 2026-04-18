"""停止任务路由"""

from fastapi import APIRouter

router = APIRouter()

task_manager = None


@router.post("/stop")
async def stop_task():
    """停止当前任务

    Returns:
        停止结果
    """
    if not task_manager:
        return {"success": False, "message": "Task manager not initialized"}

    try:
        task_manager.cancel_current()
        return {"success": True, "message": "Task cancellation requested"}
    except Exception as e:
        return {"success": False, "message": f"Failed to cancel task: {str(e)}"}
