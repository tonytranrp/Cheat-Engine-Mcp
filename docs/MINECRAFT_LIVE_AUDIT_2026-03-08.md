# Minecraft Live Audit 2026-03-08

This document records the live CE MCP audit run against `Minecraft.Windows.exe`, the user-facing inconveniences found during that pass, and the fixes added immediately afterward.

## Target

- Process: `Minecraft.Windows.exe`
- Environment: Cheat Engine live bridge with the MCP backend on `127.0.0.1:5556`

## Findings

### 1. `run-live-tool-suite.py` failed with a raw port-bind error when the normal backend was already running

Before the fix, the dev live suite tried to bind `127.0.0.1:5556` directly and crashed if `ce_mcp_server` was already listening.

Fix:

- added `tools/dev/live_runner_support.py`
- added `--manage-existing-backend` to `tools/dev/run-live-tool-suite.py`
- the helper now stops the existing backend cleanly, runs the live suite, waits for the port to clear, and restarts the backend with startup-failure reporting

### 2. Repeated live-suite runs polluted the Lua environment

Before the fix, repeated `ce.lua_configure_environment(...)` calls only added search paths. Long sessions accumulated stale temp paths.

Fix:

- added `ce.lua_remove_library_root`
- added `ce.lua_reset_environment`
- added `reset_managed=True` support to `ce.lua_configure_environment`
- the live suite now cleans up its own Lua environment after the script-tool phase

### 3. Repeated `ce.attach_process` calls were much slower than they needed to be

Before the fix, the native bridge still called `openProcessEx()` even when Cheat Engine was already attached to the requested PID.

Fix:

- added an already-attached fast path in `native/src/core/core_process_tools.cpp`

## Timing Results

### Full live suite against Minecraft

Before the attach fast path and backend-management fix:

- total runtime was about `77.5s`
- running the suite while the backend was already active failed with a raw socket-bind error

After the fix:

- total runtime: `20445.765 ms`
- `_run_native_tools`: `544.295 ms`
- `_run_structure_and_dissect_tools`: `4007.983 ms`
- `_run_debug_tools`: `2606.225 ms`
- `run_pointer_chain_string_smoke`: `1603.813 ms`
- `ce.attach_process` timing inside the suite:
  - count: `18`
  - average: `131.017 ms`
  - max: `709.44 ms`

### Focused benchmark run

Command:

```powershell
py -3 .\tools\dev\benchmark-live-tools.py --process-name "Minecraft.Windows.exe" --manage-existing-backend
```

Results from the live benchmark pass:

- `ce.attach_process(same target)`: avg `20.541 ms`, max `26.683 ms`
- `ce.verify_target`: avg `13.738 ms`
- `ce.normalize_address`: avg `1.689 ms`
- `ce.read_integer`: avg `1.29 ms`
- `ce.read_bytes_table`: avg `1.363 ms`
- `ce.lua_eval`: avg `0.952 ms`
- `ce.lua_call(readInteger)`: avg `0.884 ms`
- `ce.lua_eval_with_globals`: avg `1.438 ms`
- `ce.structure_read`: avg `5.061 ms`
- `ce.scan_once`: avg `52.643 ms`
- `parallel_mixed_light` with `18` calls across `6` workers:
  - per-call avg `6.134 ms`
  - wall time `21.929 ms`

## New Dev Commands

```powershell
py -3 .\tools\dev\run-live-tool-suite.py --process-name "Minecraft.Windows.exe" --manage-existing-backend
py -3 .\tools\dev\benchmark-live-tools.py --process-name "Minecraft.Windows.exe" --manage-existing-backend
```
