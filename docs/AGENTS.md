# Pinterest Scraper - AGENTS KNOWLEDGE BASE

**Updated:** 2026-05-03
**Stack:** Python + Playwright + FastAPI + PyStray
**Architecture:** Plugin-based (v2.0)
**Purpose:** Multi-site image scraper with human-like browsing

---

## OVERVIEW

Plugin-based web scraper using Playwright for browser automation. Supports CLI, FastAPI service, and Windows system tray app. Core feature: human-like browsing with randomized clicks and scrolls to avoid detection.

**Two running modes:**
1. **Traditional mode** (default): Direct call to `scraper.py` PinterestScraper
2. **Plugin mode** (`--use-plugin`): Through `core.engine` plugin architecture

---

## ENTRY POINTS

| Entry | File | Purpose |
|-------|------|---------|
| CLI | `main.py` | Command-line scraper with args |
| API | `api_service_enhanced/service_main.py` | FastAPI with progress tracking |
| Tray | `tray_app/tray_main.py` | Windows system tray GUI |
| Cookie CLI | `cookie_cli.py` | Cookie account management |
| Cookie Login | `cookie_login.py` | Interactive login tool |

---

## STRUCTURE

```
.
├── main.py                    # CLI entry (supports --use-plugin)
├── scraper.py                 # Legacy Pinterest scraper (~3573 lines)
├── downloader.py              # Image downloader
├── chrome_launcher.py         # Chrome debug launcher
├── cookie_cli.py              # Cookie management CLI
├── cookie_login.py            # Interactive login tool
├── output.py                  # JSON output handling
│
├── core/                      # Plugin architecture core
│   ├── __init__.py
│   ├── plugin_interface.py    # ScraperPlugin / PipelinePlugin interfaces
│   ├── browser_manager.py     # Unified browser lifecycle management
│   ├── config.py              # Unified config manager (singleton)
│   └── engine.py              # Plugin registry, discovery, task dispatch
│
├── plugins/                   # Scraper plugins
│   ├── __init__.py
│   ├── pinterest/             # Pinterest plugin (refactored from scraper.py)
│   │   ├── __init__.py        # register() function
│   │   ├── plugin.py          # PinterestPlugin (ScraperPlugin impl)
│   │   ├── auth.py            # Login & Cookie management
│   │   ├── navigator.py       # Page navigation & scrolling
│   │   ├── extractor.py       # Data extraction (DOM/JSON/modal)
│   │   └── collector.py       # Pin collection & AI filtering
│   └── tianjin/               # Tianjin housing plugin
│       ├── __init__.py        # register() function
│       └── plugin.py          # TianjinPlugin (PipelinePlugin impl)
│
├── scrapers/                  # Legacy scraper implementations
│   ├── base.py                # BaseScraper abstract class
│   ├── pipeline.py            # Tianjin 3-stage pipeline
│   ├── tj_gov_scraper.py      # Government housing data
│   ├── fang_scraper.py        # Fang.com name mapping
│   ├── sanvjia_scraper.py     # 3vjia floor plans
│   ├── kujiale_scraper.py     # Kujiale floor plans
│   └── storage.py             # Project storage (SQLite)
│
├── shared/                    # Shared modules
│   ├── models.py              # Pin dataclass
│   ├── cookie_manager.py      # Cookie DB management
│   ├── ai_filter_manager.py   # AI quality filtering
│   ├── coordinator.py         # Multi-worker coordination
│   ├── async_ai_worker.py     # Async AI evaluation
│   ├── ollama_client.py       # Ollama API client
│   ├── doubao_client.py       # Doubao API client
│   ├── openai_vision_client.py# OpenAI Vision client
│   ├── zhipu_glm_client.py    # Zhipu GLM client
│   ├── prompt_templates.py    # AI prompt templates
│   ├── dynamic_prompt.py      # Dynamic prompt builder
│   ├── config_manager.py      # Legacy config manager
│   ├── config_schema.py       # Config schema
│   ├── progress_state.py      # Progress state
│   ├── ollama_config.py       # Ollama config
│   └── redis_config.py        # Redis config
│
├── api_service_enhanced/      # FastAPI service
│   ├── service_main.py        # FastAPI app
│   ├── task_manager.py        # Async task handling
│   ├── chrome_manager.py      # Chrome process mgmt
│   ├── progress_tracker.py    # Progress tracking
│   └── routes/                # API endpoints
│       ├── scrape.py          # Scrape endpoints
│       ├── status.py          # Status endpoints
│       ├── config.py          # Config endpoints
│       ├── stop.py            # Stop endpoints
│       ├── cookies.py         # Cookie endpoints
│       └── plugin.py          # Plugin mode endpoints
│
├── tray_app/                  # Windows tray application
│   ├── tray_main.py           # Entry point
│   ├── tray_icon.py           # Icon/menu handling
│   ├── console_gui.py         # Web-based console
│   ├── process_manager.py     # Process control
│   ├── config_gui.py          # Config GUI
│   ├── config_manager.py      # Tray config
│   └── first_run_setup.py     # First run setup
│
├── build/                     # PyInstaller specs
│   ├── tray_app.spec
│   ├── scraper_worker.spec
│   └── api_service.spec
│
└── docs/                      # Documentation
    ├── AGENTS.md              # This file
    ├── architecture/          # Architecture docs
    ├── guides/                # Usage guides
    └── archive/               # Archived docs
```

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Plugin architecture | `core/` | Engine, interfaces, browser mgmt |
| Pinterest plugin | `plugins/pinterest/` | Refactored from scraper.py |
| Tianjin plugin | `plugins/tianjin/` | 3-stage pipeline |
| Legacy scraper | `scraper.py` | ~3573 lines, still used in default mode |
| CLI args | `main.py` | parse_args() + --use-plugin flag |
| API routes | `api_service_enhanced/routes/` | Including plugin mode |
| Models | `shared/models.py` | Pin dataclass |
| Cookie DB | `shared/cookie_manager.py` | SQLite persistence |
| AI filtering | `shared/ai_filter_manager.py` | Multi-provider AI |
| Chrome mgmt | `chrome_launcher.py` | Chrome debug launcher |

---

## KEY CLASSES

| Class | Location | Role |
|-------|----------|------|
| `ScraperPlugin` | `core/plugin_interface.py` | Plugin interface (ABC) |
| `PipelinePlugin` | `core/plugin_interface.py` | Multi-stage pipeline interface |
| `PinterestPlugin` | `plugins/pinterest/plugin.py` | Pinterest plugin impl |
| `PinterestAuth` | `plugins/pinterest/auth.py` | Login & Cookie management |
| `PinterestNavigator` | `plugins/pinterest/navigator.py` | Page navigation |
| `PinterestExtractor` | `plugins/pinterest/extractor.py` | Data extraction |
| `PinterestCollector` | `plugins/pinterest/collector.py` | Collection & AI filter |
| `TianjinPlugin` | `plugins/tianjin/plugin.py` | Tianjin pipeline plugin |
| `ScraperEngine` | `core/engine.py` | Plugin registry & dispatch |
| `BrowserManager` | `core/browser_manager.py` | Unified browser lifecycle |
| `ConfigManager` | `core/config.py` | Singleton config manager |
| `PinterestScraper` | `scraper.py` | Legacy scraper (default mode) |
| `Pin` | `shared/models.py` | Data model for pins |
| `CookieManager` | `shared/cookie_manager.py` | Cookie DB management |
| `TaskManager` | `api_service_enhanced/task_manager.py` | Async task control |

---

## HOW TO ADD A NEW PLUGIN

1. Create `plugins/yoursite/` directory
2. Create `__init__.py` with `register()` function
3. Implement `ScraperPlugin` or `PipelinePlugin` in `plugin.py`
4. Plugin will be auto-discovered by `engine.discover_plugins()`

```python
# plugins/yoursite/__init__.py
from plugins.yoursite.plugin import YourPlugin

def register():
    from core.engine import register_plugin
    register_plugin("yoursite", YourPlugin)
```

---

## CONVENTIONS

### Code Style
- Chinese comments throughout (project origin)
- Type hints used in core/ and shared/, minimal elsewhere
- Dataclasses for models
- Context managers (`__enter__`, `__exit__`) for resource management

### Module Pattern
```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### File Naming
- `*_main.py` for entry points
- `*.py` modules use snake_case
- Routes grouped in `routes/` subdirectory
- Plugins grouped in `plugins/` subdirectory

### Debug Output
- All debug files saved to `logs/debug/<site>/` (only in --debug mode)
- Never save debug files to project root

---

## ANTI-PATTERNS (AVOID)

- **Don't use sync_playwright in async contexts** - causes deadlocks
- **Don't skip stealth mode** - required for anti-detection
- **Don't save debug files to project root** - use `logs/debug/`
- **Don't modify scraper.py without testing** - ~3573 lines, complex flow
- **Don't create plugins without implementing ScraperPlugin** - use the interface

---

## COMMANDS

```bash
# CLI - Traditional mode (default)
python main.py -q "modern design" -n 100 --connect --auto-launch

# CLI - Plugin mode (new architecture)
python main.py -q "modern design" -n 100 --connect --auto-launch --use-plugin

# CLI - Tianjin housing
python main.py --site tianjin --connect --auto-launch --no-headless --debug

# Start API
python api_service_enhanced/service_main.py --port 8000

# Start tray app
python tray_app/tray_main.py

# Cookie management
python cookie_cli.py list
python cookie_cli.py check --id 1
python cookie_login.py --id 1

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
- Plugin mode is the recommended way forward
- Legacy scraper.py still works in default mode for backward compatibility
- Debug files are saved to `logs/debug/` (not project root)
- Cookie database stored in `db/cookies.db`
