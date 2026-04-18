from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import subprocess
import json
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
import threading
import importlib.util

# 配置日志
log_file = os.path.join(os.path.dirname(__file__), "service.log")
handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# 全局状态
active_ws = None
scrape_active = False
scrape_result = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Service starting up")
    yield
    logger.info("Service shutting down")


app = FastAPI(title="Pinterest Scraper API", lifespan=lifespan)


class ScrapeRequest(BaseModel):
    query: str
    max_pins: int = 100
    min_saves: int = 0
    min_likes: int = 0
    min_comments: int = 0
    download_images: bool = True


def get_scraper_script_path():
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "main.py")
    else:
        return os.path.join(os.path.dirname(__file__), "main.py")


def get_output_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "output")
    else:
        return os.path.join(os.path.dirname(__file__), "output")


def run_scrape_sync(
    query, max_pins, min_saves, min_likes, min_comments, download_images
):
    global scrape_active
    scrape_active = True
    output_dir = get_output_dir()
    try:
        logger.info(f"Starting scrape: query={query}, max_pins={max_pins}")
        script_path = get_scraper_script_path()
        cmd = [
            sys.executable,
            script_path,
            "--query",
            query,
            "--max-pins",
            str(max_pins),
            "--min-saves",
            str(min_saves),
            "--min-likes",
            str(min_likes),
            "--min-comments",
            str(min_comments),
            "--connect",
            "--no-headless",
            "--cdp-endpoint",
            "http://127.0.0.1:9222",
            "--debug",
            "--output",
            output_dir,
        ]
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        logger.info(
            f"Scrape stdout: {result.stdout[-500:] if result.stdout else 'empty'}"
        )
        logger.info(
            f"Scrape stderr: {result.stderr[-500:] if result.stderr else 'empty'}"
        )
        if result.returncode != 0:
            logger.error(f"Scrape failed (exit {result.returncode}): {result.stderr}")
            raise HTTPException(status_code=500, detail=result.stderr[:2000])
        filtered_path = os.path.join(output_dir, "filtered_data.json")
        data_path = os.path.join(output_dir, "data.json")
        if os.path.exists(filtered_path):
            with open(filtered_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Returning filtered data: {data.get('total_pins', 0)} pins")
            return data
        elif os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Returning raw data: {data.get('total_pins', 0)} pins")
            return data
        else:
            logger.error("No output files found")
            raise HTTPException(
                status_code=500, detail="Scrape completed but no output files found"
            )
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        logger.error("Scrape timed out after 600s")
        raise HTTPException(
            status_code=504, detail="Scrape timed out after 600 seconds"
        )
    except Exception as e:
        logger.error(f"Scrape error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        scrape_active = False


@app.post("/api/scrape")
async def scrape(req: ScrapeRequest):
    import asyncio

    if scrape_active:
        raise HTTPException(status_code=409, detail="Another scrape is already running")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        run_scrape_sync,
        req.query,
        req.max_pins,
        req.min_saves,
        req.min_likes,
        req.min_comments,
        req.download_images,
    )


@app.post("/api/scrape/async")
async def scrape_async(req: ScrapeRequest):
    if scrape_active:
        raise HTTPException(status_code=409, detail="Another scrape is already running")
    global scrape_result
    scrape_result = None

    def _run():
        global scrape_active, scrape_result
        try:
            result = run_scrape_sync(
                req.query,
                req.max_pins,
                req.min_saves,
                req.min_likes,
                req.min_comments,
                req.download_images,
            )
            scrape_result = result
        except HTTPException as e:
            scrape_result = {"success": False, "error": e.detail}
        except Exception as e:
            scrape_result = {"success": False, "error": str(e)}

    import threading

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"status": "started", "message": "Scrape task started in background"}


@app.get("/health")
async def health():
    return {"status": "ok", "scrape_active": scrape_active}


@app.get("/api/status")
async def status():
    return {
        "running": scrape_active,
        "pins": 0,
        "status": "running" if scrape_active else "idle",
        "time": "...",
    }


@app.post("/api/stop")
async def stop():
    global scrape_active
    scrape_active = False
    return {"status": "stopping"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global active_ws
    active_ws = websocket
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        active_ws = None


@app.get("/", response_class=FileResponse)
async def get_console():
    return FileResponse(os.path.join(os.path.dirname(__file__), "console.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None, access_log=False)
