"""API服务入口（增强版）"""

from fastapi import FastAPI
from contextlib import asynccontextmanager
import os
import sys
import signal
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from api_service_enhanced.progress_tracker import ProgressTracker
from api_service_enhanced.chrome_manager import ChromeManager
from api_service_enhanced.task_manager import TaskManager
from api_service_enhanced.routes import status, scrape, config, stop

# 全局实例
chrome_manager = None
task_manager = None
progress_tracker = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务生命周期管理"""
    global chrome_manager, task_manager, progress_tracker

    # 初始化
    progress_tracker = ProgressTracker()
    chrome_manager = ChromeManager(progress_tracker)
    task_manager = TaskManager(chrome_manager, progress_tracker)

    # 设置路由模块的全局实例
    status.progress_tracker = progress_tracker
    scrape.task_manager = task_manager
    stop.task_manager = task_manager

    # 注册关闭信号
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    print("Pinterest Scraper API服务已启动")
    yield

    # 清理
    if chrome_manager:
        chrome_manager.cleanup()
    if task_manager:
        task_manager.cancel_current()

    print("Pinterest Scraper API服务已关闭")


def handle_shutdown(signum, frame):
    """处理关闭信号"""
    global task_manager, chrome_manager

    print(f"\n接收到关闭信号 {signum}，正在清理...")

    if task_manager:
        task_manager.cancel_current()
    if chrome_manager:
        chrome_manager.cleanup()

    sys.exit(0)


# 创建FastAPI应用
app = FastAPI(
    title="Pinterest Scraper API",
    description="Pinterest图片爬虫API服务（增强版）",
    version="2.0.0",
    lifespan=lifespan,
)

# 注册路由
app.include_router(scrape.router, prefix="/api", tags=["爬虫"])
app.include_router(status.router, prefix="/api", tags=["状态"])
app.include_router(config.router, prefix="/api", tags=["配置"])
app.include_router(stop.router, prefix="/api", tags=["控制"])


# 根路径
@app.get("/")
async def root():
    """API文档"""
    return {
        "message": "Pinterest Scraper API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "scrape": "/api/scrape",
            "scrape_async": "/api/scrape/async",
            "progress": "/api/progress",
            "status": "/api/status",
            "config": "/api/config",
            "health": "/api/health",
        },
    }


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Pinterest Scraper API服务")
    parser.add_argument("--port", type=int, default=8000, help="API服务端口")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="API服务主机")

    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_config=None, access_log=False)
