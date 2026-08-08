# Atlas Runtime Project Memory

## Project Overview
Atlas Runtime is an Android automation runtime running on Samsung One UI 8.5 + Termux, using asyncio async architecture, orchestrating Shell executors, UI automation, high-privilege operations via a microkernel scheduler.

## Key Architecture (v9.1 — 2026-08-08)
- **6-layer architecture**: models/ → storage/ → device/ → executors/ → core/ → transport/ → runtime/app.py
- **Layer 0: models/** — pure data contracts (BatteryStatus, MemoryStatus, SystemHealth, SimInfo, SimStatus, SimSwitchResult, Task, TaskStatus, StorageFullError, etc.)
- **Layer 2: device/** — platform detection + health checking (named "device" not "platform" to avoid Python stdlib conflict)
- **Layer 3: executors/** — BaseExecutor ABC fully adopted: SafeShellExecutor inherits it; Scheduler calls `executor.execute(cmd, timeout)` instead of plain function
- **core/platform.py, core/health_checker.py, core/shell_executor.py** = compatibility stubs re-exporting from device/ and executors/
- **SIM switching**: Shizuku/Rish is the ONLY approach; AutoJS6SimSwitcher is an ABC stub for future use
- **Dependency rule**: Top-down only; all layers can safely import from models/; transport → models only (no core dep)
- **Termux paths**: canonical source is `device/detector.py` (TERMUX_PREFIX, TERMUX_HOME, TERMUX_TMP)

## Naming Convention
- Logger names preserved across module migrations (e.g., `Atlas.HealthChecker`, `Atlas.HighPrivilege`)
- `device/` directory name chosen over `platform/` to avoid collision with Python stdlib `platform` module

## External Integration Layer (2026-08-08)
- **30 new files** generated across 5 phases
- **Phase 1**: core/memory_controller.py (3-tier probe + 2-level gate), core/circuit_breaker.py (3-state), core/dedup.py (TTL window)
- **Phase 2**: runtime/trigger_atlas.sh (FIFO+HTTP), transport/result_callback.py (atomic write), transport/autojs_launcher.py (dual-pkg fallback)
- **Phase 3**: config/tasker/ — 8 XML files (1 project + 3 profiles + 4 tasks)
- **Phase 4**: scripts/autojs/ — 6 JS files (1 template + 5 specialized scripts)
- **Phase 5**: E2E checklist (5 scenarios/30 items), Tasker guide, AutoJS6 guide
- All new modules integrate via optional constructor injection (backward compatible)

## Testing
- ~345 total tests (291 passing on Windows with flaky exclusions)
- 7 new test files: test_models.py, test_device.py, test_executor_base.py, test_sim_switch.py, test_memory_controller.py, test_circuit_breaker.py, test_dedup.py (109 tests)
- Known pre-existing failures: bootstrap teardown SQLite lock on Windows, scheduler retry timeout (timing-dependent), rotator transaction errors on Windows
- Use `python -m pytest tests/ -k "not test_task_retries and not test_rotate_if_needed_above_limit and not test_archive_file_created and not bootstrap"` for clean runs

## Compatibility Commitments
- All `from core.platform import ...`, `from core.health_checker import ...`, `from core.shell_executor import ...`, `from storage.driver import StorageFullError` remain valid
- New code should use `from device import ...`, `from executors import ...`, `from models import ...`
- `from models import Task, TaskStatus` is the canonical path (migrated from core.scheduler)
