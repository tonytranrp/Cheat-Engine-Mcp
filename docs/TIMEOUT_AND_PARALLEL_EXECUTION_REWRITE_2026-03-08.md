# Timeout And Parallel Execution Rewrite

This document records the `0.2.8` pass that focused on CE-session freeze recovery, bounded long-running tools, and parallel native request handling.

## Problems Observed

- A long `ce.dissect_module("Minecraft.Windows.exe")` pass could leave later calls appearing hung because the CE bridge session stayed busy even after the client timed out.
- Some broad memory-map and scan requests could run far longer than the MCP timeout budget, so the user only saw a timeout while Cheat Engine kept working in the background.
- The native bridge client handled incoming tool calls on the same socket thread that received them, so one slow request blocked every later request from even starting.
- The dev validation harness could kill a background listener on `5556` and then fail to restore it correctly because detached stdio relaunch is not a valid long-lived mode.

## Implemented Changes

- Native bridge transport:
  - `native/src/core/mcp_client.cpp` now queues `call` messages and processes them on a bounded worker pool.
  - socket receive stays responsive while tool work runs in parallel.
  - response sends are serialized with a dedicated send mutex.
- Native timeout enforcement:
  - `native/src/core/core_memory_tools.cpp` now consumes `__timeout_ms`.
  - `ce.query_memory_map` stops at the deadline and reports `timed_out` plus `truncated`.
  - native AOB scans stop at the deadline and report `timed_out` plus `truncated`.
- Python bridge hardening:
  - `python/src/ce_mcp_server/bridge.py` closes the CE session when a tool call times out.
  - later calls no longer stack up behind a poisoned request.
- Dissect workflow:
  - `python/src/ce_mcp_server/tools/structure_tools.py` rewrites `ce.dissect_module` to resolve committed executable regions, split them into chunks, and dispatch `ce.dissect_region` with a rolling timeout budget.
- Dev harness:
  - `python/src/ce_mcp_server/server.py` adds `--transport bridge-only`.
  - `tools/dev/live_runner_support.py` now restores detached listeners in `bridge-only` mode.
  - the same harness now refuses to kill a stdio-backed `ce_mcp_server` because that breaks the active MCP transport.

## Validation

Unit tests:

- `py -3 -m unittest discover -s tests -v`
- Result: `28` tests passed, `1` live integration test skipped by default

Full live suite:

- `py -3 .\tools\dev\run-live-tool-suite.py --process-name "Minecraft.Windows.exe" --manage-existing-backend`
- Result: `210/210` tools passed in `18366.653 ms`

Focused benchmark:

- `py -3 .\tools\dev\benchmark-live-tools.py --process-name "Minecraft.Windows.exe" --manage-existing-backend --iterations 12 --scan-iterations 6 --parallel-calls 24 --parallel-workers 8`
- Result highlights:
  - `ce.attach_process(same target)`: avg `14.06 ms`
  - `ce.verify_target`: avg `9.004 ms`
  - `ce.normalize_address`: avg `1.364 ms`
  - `ce.read_integer`: avg `0.874 ms`
  - `ce.structure_read`: avg `3.297 ms`
  - `ce.scan_once`: avg `38.623 ms`
  - `ce.aob_scan(range,x16)`: avg `0.61 ms`
  - `ce.aob_scan_unique(range,x16)`: avg `0.526 ms`
  - `ce.scan_string(range,ascii)`: avg `0.614 ms`
  - `ce.aob_scan_module_unique(main module)`: avg `242.894 ms`
  - `parallel_mixed_light`: `24` calls across `8` workers completed in `24.502 ms` wall time

## Remaining Heavy Paths

These are still relatively expensive, but they are no longer presenting as silent infinite hangs in the validated workflow:

- `ce.reinitialize_symbolhandler`
- `ce.debug_start`
- `ce.aob_scan_module_unique` across a full large module
- broad `ce.scan_once` / `ce.scan_value` workloads

## Operator Guidance

- Prefer bounded scopes for scans and memory walks.
- Use `timeout_seconds` explicitly on legitimately large operations.
- If Cheat Engine itself becomes unresponsive, use `tools/dev/restart-cheat-engine.ps1`.
- For isolated live validation on a machine that already has an interactive stdio backend, move the plugin to a different bridge port instead of stopping the active backend in place.
