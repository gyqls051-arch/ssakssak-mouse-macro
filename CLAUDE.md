# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Single-file PySide6 Windows desktop app (`app.py`) — a mouse-click macro with three modes (countdown delay, scheduled timestamp for ticketing/registration, repeat-interval clicker). Korean UI. **Windows-only** — uses `ctypes.windll.kernel32.SetThreadExecutionState` for sleep prevention.

## Commands

```powershell
# Run from source (requires PySide6 + pynput installed)
python app.py

# Build standalone EXE → dist\OffcutMouseMacro.exe
.\build.bat
```

`build.bat` invokes PyInstaller with `--onefile --windowed` and `--add-data` for `index.html`, `style.css`, `script.js`. **Those three web files are vestigial** — they're from an earlier browser-prototype version and the PySide6 app never reads them. Safe to remove from `build.bat` if cleaning up. `OffcutMouseMacro.spec` exists but `build.bat` regenerates the spec on every run (it doesn't invoke the existing .spec).

There are no tests, no linter config, no requirements.txt. Dependencies are just `PySide6` and `pynput`.

## Architecture

Everything lives in `app.py`. Key structural pieces:

- **`MacroWindow(QMainWindow)`** — the only window. Builds UI inline in `_build_ui()` (no separate .ui files / no Designer). Heavy inline QSS dark theme in `_setup_style()`.
- **`SignalBridge(QObject)`** — the thread-safety contract. Worker threads NEVER touch Qt widgets directly; they emit signals on `self.bridge` (log_signal, status_signal, countdown_tick, click_done_signal, etc.) that are connected to slots on the main GUI thread in `_connect_signals()`. **Any new worker-thread code must follow this pattern** — calling widget methods from a worker thread will crash.
- **Worker threads** — `_worker_countdown`, `_worker_scheduled`, `_worker_interval` each run on a `threading.Thread(daemon=True)`. They share a single `threading.Event` (`self.macro_stop`) for cancellation; they check `self.macro_stop.is_set()` inside their sleep loops. Only one worker runs at a time — `_on_start` calls `_on_stop` first if a thread is alive.
- **Global hotkeys** — `pynput.keyboard.Listener` runs on its own daemon thread (`_start_hotkey_listener`). F8 emits `coord_locked_signal`; F9/F10 use `QTimer.singleShot(0, ...)` to marshal back to the GUI thread before calling `_on_start`/`_on_stop`.
- **Sleep prevention** — `prevent_sleep()` is called when a macro starts and `_release_sleep()` is called in every worker's `finally` block AND in `_on_stop` AND in `closeEvent`. The `_sleep_prevented` flag guards against double-release. If you add a new worker, replicate this pattern or scheduled macros may silently die when Windows sleeps.
- **Scheduled-time precision** — `_worker_scheduled` uses coarse `time.sleep` until ~50ms before the target, then a tight busy-loop. Don't replace the busy-loop with `time.sleep` if you care about the sub-50ms precision the ticketing use case needs.
- **File logging** — `setup_logging()` writes `macro_log.txt` next to `sys.argv[0]` (so next to the EXE when frozen, next to `app.py` when run from source). The on-screen log box is separate (`_append_log`).

## Conventions

- UI strings are Korean; log levels use bracketed English-ish tags (`[LOCK]`, `[HOTKEY]`, `[ERROR]`, `[완료]`). Keep both when adding messages.
- Status badge colors are driven by **ordered** substring matching on the status text inside `_update_status` (`"IDLE"` → idle, `"중단"` → stopped, `"완료"` → done, `"클릭"` → clicking, `"대기"` → armed). Order matters — the idle string `"대기 중 (IDLE)"` also contains `"대기"`, so `"IDLE"` is checked first. If you change status strings, update that matcher. Badge colors map to Offcut tokens, not the old neon palette.
- UI follows the **Offcut design system** (see `fonts/` + the token constants at the top of `app.py`): light card-on-grey, flat (no shadows/gradients), Pretendard, fresh green `#03C75A`. No emoji. Pretendard TTFs are loaded via `QFontDatabase` (`load_app_fonts`) and bundled into the EXE by `build.bat`'s `--add-data "fonts;fonts"`.
- Worker threads must marshal **all** widget access through `self.bridge` signals — including `countdown_ring` (use `reset_ring_signal`, never call `.reset()` from a worker).
