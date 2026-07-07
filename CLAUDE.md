# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Single-file PySide6 desktop app (`app.py`) — a mouse-click macro with three modes (countdown delay, scheduled timestamp for ticketing/registration, repeat-interval clicker). Korean UI. **Windows + macOS** — OS-specific code is gated on the `IS_WINDOWS` / `IS_MACOS` module constants: sleep prevention (`SetThreadExecutionState` vs a `caffeinate -dims` child process), log dir (`%LOCALAPPDATA%\OffcutMouseMacro` vs `~/Library/Logs/OffcutMouseMacro`), and fallback fonts (`FALLBACK_SANS`/`MONO_FAMILY`: Malgun Gothic/Consolas vs Apple SD Gothic Neo/Menlo). Gate any new OS-specific code the same way.

macOS caveats: pynput needs Accessibility + Input Monitoring permissions (the app logs a startup warning about this); F8–F10 need Fn or the "standard function keys" setting; rebuilding the .app can reset TCC permissions, so `build_mac.sh` ad-hoc codesigns. `.sh` files must stay LF — enforced by `.gitattributes`.

## Commands

```powershell
# Run from source (requires PySide6 + pynput installed)
python app.py

# Build standalone EXE → dist\OffcutMouseMacro.exe (Windows)
.\build.bat
```

```bash
# Build .app bundle → dist/OffcutMouseMacro.app (macOS)
./build_mac.sh
```

Both build scripts invoke PyInstaller with `--onefile --windowed` and bundle `fonts/` via `--add-data` (separator is `;` on Windows, `:` on macOS). `OffcutMouseMacro.spec` exists but the build scripts regenerate the spec on every run (they don't invoke the existing .spec). The old browser-prototype files live in `legacy_unused/` and are never read by the app.

There are no tests and no linter config. Dependencies (`requirements.txt`) are just `PySide6` and `pynput`.

## Architecture

Everything lives in `app.py`. Key structural pieces:

- **`MacroWindow(QMainWindow)`** — the only window. Builds UI inline in `_build_ui()` (no separate .ui files / no Designer). Heavy inline QSS dark theme in `_setup_style()`.
- **`SignalBridge(QObject)`** — the thread-safety contract. Worker threads NEVER touch Qt widgets directly; they emit signals on `self.bridge` (log_signal, status_signal, countdown_tick, click_done_signal, etc.) that are connected to slots on the main GUI thread in `_connect_signals()`. **Any new worker-thread code must follow this pattern** — calling widget methods from a worker thread will crash.
- **Worker threads** — `_worker_countdown`, `_worker_scheduled`, `_worker_interval` each run on a `threading.Thread(daemon=True)`. They share a single `threading.Event` (`self.macro_stop`) for cancellation; they check `self.macro_stop.is_set()` inside their sleep loops. Only one worker runs at a time — `_on_start` calls `_on_stop` first if a thread is alive.
- **Global hotkeys** — `pynput.keyboard.Listener` runs on its own daemon thread (`_start_hotkey_listener`). F8 emits `coord_locked_signal`; F9/F10 use `QTimer.singleShot(0, ...)` to marshal back to the GUI thread before calling `_on_start`/`_on_stop`.
- **Sleep prevention** — `prevent_sleep()` is called when a macro starts and `_release_sleep()` is called in every worker's `finally` block AND in `_on_stop` AND in `closeEvent`. The `_sleep_prevented` flag guards against double-release. If you add a new worker, replicate this pattern or scheduled macros may silently die when the OS sleeps.
- **Scheduled-time precision** — `_worker_scheduled` uses coarse `time.sleep` until ~50ms before the target, then a tight busy-loop. Don't replace the busy-loop with `time.sleep` if you care about the sub-50ms precision the ticketing use case needs.
- **File logging** — `setup_logging()` writes a rotating `macro_log.txt` into the per-user app-data dir returned by `_log_dir()` (`%LOCALAPPDATA%\OffcutMouseMacro` on Windows, `~/Library/Logs/OffcutMouseMacro` on macOS), falling back next to `sys.argv[0]`. The on-screen log box is separate (`_append_log`).

## Conventions

- UI strings are Korean; log levels use bracketed English-ish tags (`[LOCK]`, `[HOTKEY]`, `[ERROR]`, `[완료]`). Keep both when adding messages.
- Status badge colors are driven by **ordered** substring matching on the status text inside `_update_status` (`"IDLE"` → idle, `"중단"` → stopped, `"완료"` → done, `"클릭"` → clicking, `"대기"` → armed). Order matters — the idle string `"대기 중 (IDLE)"` also contains `"대기"`, so `"IDLE"` is checked first. If you change status strings, update that matcher. Badge colors map to Offcut tokens, not the old neon palette.
- UI follows the **Offcut design system** (see `fonts/` + the token constants at the top of `app.py`): light card-on-grey, flat (no shadows/gradients), Pretendard, fresh green `#03C75A`. No emoji. Pretendard TTFs are loaded via `QFontDatabase` (`load_app_fonts`) and bundled into the EXE by `build.bat`'s `--add-data "fonts;fonts"`.
- Worker threads must marshal **all** widget access through `self.bridge` signals — including `countdown_ring` (use `reset_ring_signal`, never call `.reset()` from a worker).
