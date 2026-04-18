# Tray App - AGENTS KNOWLEDGE BASE

**Purpose:** Windows system tray application for Pinterest Scraper

---

## OVERVIEW

Windows-native system tray GUI using pystray. Provides web-based console for controlling scraper without terminal.

---

## STRUCTURE

```
tray_app/
├── tray_main.py        # Entry point
├── tray_icon.py        # Icon and menu management
├── console_gui.py      # Web-based console (408 lines)
├── process_manager.py  # Chrome + API process control
├── config_manager.py   # Settings persistence
├── config_gui.py       # Configuration dialog
└── first_run_setup.py  # Initial setup
```

---

## KEY CLASSES

| Class | File | Role |
|-------|------|------|
| `TrayIconManager` | `tray_icon.py` | Menu + icon handling |
| `ProcessManager` | `process_manager.py` | Start/stop Chrome/API |
| `ConfigManager` | `config_manager.py` | JSON config I/O |
| `ConsoleRequestHandler` | `console_gui.py` | HTTP request handler |

---

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Menu items | `tray_icon.py:setup_menu()` | Add/edit menu actions |
| Console UI | `console_gui.py` | HTML + JS embedded in Python |
| Process control | `process_manager.py` | subprocess management |
| Config schema | `config_manager.py` | Default values + validation |
| First-run | `first_run_setup.py` | Playwright install check |

---

## ANTI-PATTERNS

- **Don't use Unix paths** - Windows-only, use `Path.home() / 'AppData'`
- **Don't skip ensure_playwright_ready()** - First run will fail
- **Don't block icon.run()** - Run in main thread only

---

## NOTES

- Console runs on localhost (dynamic port)
- Uses Windows Registry for autostart
- Icon assets in `tray_app/assets/`
