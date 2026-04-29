# Pinterest Scraper - AGENTS KNOWLEDGE BASE

**Generated:** 2026-04-20
**Stack:** Python + Playwright + FastAPI + PyStray
**Purpose:** Pinterest image scraper with human-like browsing

---

## OVERVIEW

Pinterest search scraper using Playwright for browser automation. Supports CLI, FastAPI service, and Windows system tray app. Core feature: human-like browsing with randomized clicks and scrolls to avoid detection.

---

## ENTRY POINTS

| Entry | File | Purpose |
|-------|------|---------|
| CLI | `main.py` | Command-line scraper with args |
| API | `api_service.py` | Basic FastAPI service |
| API v2 | `api_service_enhanced/service_main.py` | Enhanced FastAPI with progress tracking |
| Tray | `tray_app/tray_main.py` | Windows system tray GUI |

---

## STRUCTURE

```
.
├── main.py              # CLI entry
├── scraper.py            # Core scraper logic (~2360 lines)
├── downloader.py        # Image downloader
├── api_service.py       # Basic FastAPI
├── api_service_enhanced/# Enhanced API service
│   ├── service_main.py  # FastAPI app
│   ├── task_manager.py  # Async task handling
│   ├── chrome_manager.py# Chrome process mgmt
│   └── routes/          # API endpoints
├── tray_app/            # Windows tray application
│   ├── tray_main.py     # Entry point
│   ├── tray_icon.py     # Icon/menu handling
│   ├── console_gui.py   # Web-based console
│   └── process_manager.py# Process control
├── scrapers/            # Multi-site scraper framework
│   ├── __init__.py
│   └── base.py          # BaseScraper abstract class
├── shared/              # Shared modules
│   ├── models.py        # Pin dataclass
│   ├── config_manager.py# Config management
│   └── progress_state.py# Progress state
└── output.py            # JSON output handling
```

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Scrape logic | `scraper.py` | PinterestScraper class, ~2360 lines |
| CLI args | `main.py:18-89` | parse_args() function |
| API routes | `api_service_enhanced/routes/` | scrape.py, status.py, config.py |
| Models | `shared/models.py` | Pin dataclass |
| Tray GUI | `tray_app/console_gui.py` | Web-based console UI |
| Chrome mgmt | `chrome_launcher.py` | Chrome debug launcher |
| Multi-site | `scrapers/base.py` | BaseScraper for extending |

---

## KEY CLASSES

| Class | Location | Role |
|-------|----------|------|
| `PinterestScraper` | `scraper.py:31` | Main scraper with stealth mode |
| `Pin` | `shared/models.py:8` | Data model for pins |
| `TaskManager` | `api_service_enhanced/task_manager.py` | Async task control |
| `ChromeManager` | `api_service_enhanced/chrome_manager.py` | Browser lifecycle |
| `TrayIconManager` | `tray_app/tray_icon.py` | System tray UI |
| `BaseScraper` | `scrapers/base.py` | Abstract base for multi-site |

---

## CONVENTIONS

### Code Style
- Chinese comments throughout (project origin)
- Type hints used in shared/, minimal elsewhere
- Dataclasses for models
- Context managers (`__enter__`, `__exit__`) for resource management

### Module Pattern
```python
# All modules add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### File Naming
- `*_main.py` for entry points
- `*.py` modules use snake_case
- Routes grouped in `routes/` subdirectory

---

## ANTI-PATTERNS (AVOID)

- **Don't use sync_playwright in async contexts** - causes deadlocks
- **Don't skip stealth mode** - scraper.py:apply_stealth() required
- **Don't forget path insertion** - modules won't import without sys.path fix
- **Don't modify scraper.py without testing** - ~2360 lines, complex flow

---

## COMMANDS

```bash
# CLI usage
python main.py -q "modern design" -n 100 --connect --auto-launch

# Start API
python api_service_enhanced/service_main.py --port 8000

# Start tray app
python tray_app/tray_main.py

# Install deps
pip install -r requirements.txt
playwright install chromium
```

---

## NOTES

- Chrome debug mode required (`--remote-debugging-port=9222`)
- First run requires manual login to Pinterest
- Profile persistence via `--chrome-profile` flag
- Tray app is Windows-only (pystray + Windows paths)
- Large files: scraper.py (~2360 lines) - test carefully
- See `SCALING_GUIDE.md` for extending to multiple websites
