# API Service Enhanced - AGENTS KNOWLEDGE BASE

**Purpose:** FastAPI service with async task management and progress tracking

---

## OVERVIEW

Enhanced FastAPI service v2.0.0 with:
- Async task queue
- Progress tracking via WebSocket/SSE
- Chrome lifecycle management
- Config endpoints

---

## STRUCTURE

```
api_service_enhanced/
├── service_main.py     # FastAPI app + lifespan
├── task_manager.py     # Async scrape tasks
├── chrome_manager.py   # Chrome process control
├── progress_tracker.py # Progress state management
└── routes/
    ├── __init__.py
    ├── scrape.py       # POST /api/scrape
    ├── status.py       # GET /api/progress
    └── config.py       # GET/POST /api/config
```

---

## KEY CLASSES

| Class | File | Role |
|-------|------|------|
| `TaskManager` | `task_manager.py:15` | Queue + cancel tasks |
| `ChromeManager` | `chrome_manager.py:11` | Start/kill Chrome |
| `ProgressTracker` | `progress_tracker.py:8` | State tracking |

---

## ROUTES

| Endpoint | Method | Handler | Purpose |
|----------|--------|---------|---------|
| `/api/scrape` | POST | `scrape.router` | Start scrape task |
| `/api/scrape/async` | POST | `scrape.router` | Async variant |
| `/api/progress` | GET | `status.router` | Get progress |
| `/api/status` | GET | `status.router` | Health check |
| `/api/config` | GET/POST | `config.router` | Config management |

---

## LIFECYCLE

```python
# service_main.py lifespan
1. Init ProgressTracker
2. Init ChromeManager
3. Init TaskManager
4. Register signal handlers (SIGTERM, SIGINT)
5. Yield (app runs)
6. Cleanup Chrome
7. Cancel running tasks
```

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add endpoint | `routes/scrape.py` | Include router in service_main.py:77 |
| Change port | `service_main.py:106` | --port arg |
| Progress format | `progress_tracker.py:10` | ProgressState model |
| Chrome args | `chrome_manager.py:25` | Launcher flags |

---

## ANTI-PATTERNS

- **Don't use sync scraper in async route** - Blocks event loop
- **Don't forget task.cancel()** - Orphans Chrome processes
- **Don't skip lifespan** - Global instances won't init

---

## NOTES

- Runs on 0.0.0.0:8000 by default
- Logs disabled for cleaner output
- Task cancellation stops Chrome + scraper
