"""停止任务路由"""

from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()

task_manager = None


@router.post("/stop")
async def stop_task(
    worker_id: Optional[str] = Query(None, description="Worker ID，如 worker-0。不传则停止所有")
):
    """停止任务

    Args:
        worker_id: 可选，指定Worker ID停止

    Returns:
        停止结果
    """
    if not task_manager:
        return {"success": False, "message": "Task manager not initialized"}

    try:
        task_manager.cancel_current(worker_id=worker_id)
        label = f"Worker {worker_id}" if worker_id else "所有Worker"
        return {"success": True, "message": f"{label} cancellation requested"}
    except Exception as e:
        return {"success": False, "message": f"Failed to cancel task: {str(e)}"}
