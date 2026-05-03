"""Cookie管理路由"""

from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter()

cookie_manager = None


@router.get("/cookies")
async def list_cookies():
    """获取所有Cookie账号列表"""
    if not cookie_manager:
        return {"code": 500, "msg": "CookieManager not initialized", "data": None}

    try:
        accounts = cookie_manager.get_all_accounts()
        status_map = {1: "有效", 0: "失效", -1: "待登录"}
        for acc in accounts:
            acc["status_label"] = status_map.get(acc["status"], "未知")
        return {"code": 200, "msg": None, "data": accounts}
    except Exception as e:
        return {"code": 500, "msg": f"获取Cookie列表失败: {str(e)}", "data": None}


@router.post("/cookies/add")
async def add_cookie(label: str = Query("", description="账号标签")):
    """添加一个新的Cookie账号（待登录状态）"""
    if not cookie_manager:
        return {"code": 500, "msg": "CookieManager not initialized", "data": None}

    try:
        account_id = cookie_manager.add_account(label=label)
        return {"code": 200, "msg": "已创建待登录账号", "data": {"id": account_id}}
    except Exception as e:
        return {"code": 500, "msg": f"添加Cookie失败: {str(e)}", "data": None}


@router.post("/cookies/ensure")
async def ensure_cookies(num_workers: int = Query(1, description="Worker数量")):
    """确保有足够的Cookie账号供所有Worker使用"""
    if not cookie_manager:
        return {"code": 500, "msg": "CookieManager not initialized", "data": None}

    try:
        accounts = cookie_manager.ensure_accounts_for_workers(num_workers)
        return {"code": 200, "msg": f"已确保 {num_workers} 个Worker的Cookie", "data": accounts}
    except Exception as e:
        return {"code": 500, "msg": f"确保Cookie失败: {str(e)}", "data": None}


@router.delete("/cookies/{account_id}")
async def delete_cookie(account_id: int):
    """删除指定Cookie账号"""
    if not cookie_manager:
        return {"code": 500, "msg": "CookieManager not initialized", "data": None}

    try:
        success = cookie_manager.delete_account(account_id)
        if success:
            return {"code": 200, "msg": "已删除", "data": None}
        return {"code": 404, "msg": "账号不存在", "data": None}
    except Exception as e:
        return {"code": 500, "msg": f"删除Cookie失败: {str(e)}", "data": None}


@router.post("/cookies/{account_id}/invalidate")
async def invalidate_cookie(account_id: int):
    """标记Cookie为失效状态"""
    if not cookie_manager:
        return {"code": 500, "msg": "CookieManager not initialized", "data": None}

    try:
        cookie_manager.set_status(account_id, 0)
        return {"code": 200, "msg": "已标记为失效", "data": None}
    except Exception as e:
        return {"code": 500, "msg": f"操作失败: {str(e)}", "data": None}


@router.post("/cookies/{account_id}/release")
async def release_cookie(account_id: int, worker_id: str = Query(None, description="Worker ID")):
    """释放Cookie的Worker绑定"""
    if not cookie_manager:
        return {"code": 500, "msg": "CookieManager not initialized", "data": None}

    try:
        if worker_id:
            cookie_manager.release_worker(worker_id)
        return {"code": 200, "msg": "已释放绑定", "data": None}
    except Exception as e:
        return {"code": 500, "msg": f"操作失败: {str(e)}", "data": None}
