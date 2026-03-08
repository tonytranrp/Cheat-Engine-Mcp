# Debug Breakpoint Visibility Fix

This document records the `0.2.9` pass that fixed debugger breakpoint visibility for the CE MCP debug/watch tools.

## Problem

Cheat Engine's raw `debug_getBreakpointList()` output does not consistently show hardware-register access/write watches the same way it shows execute breakpoints.

That meant:

- `ce.debug_watch_accesses_start` and `ce.debug_watch_writes_start` could be working and capturing hits
- while `ce.debug_list_breakpoints` still looked incomplete because it only mirrored the raw CE list

## Shipped fix

`ce.debug_list_breakpoints` and `ce.debug_status` now return an effective breakpoint view by default.

Returned fields:

- `count` and `breakpoints`: active CE MCP watches plus any extra raw CE breakpoints
- `raw_count` and `raw_breakpoints`: the direct Cheat Engine raw breakpoint list
- `active_watch_count` and `watch_breakpoints`: active CE MCP watch registrations
- `count_strategy`: currently `effective`

This keeps the raw CE view available without forcing users to guess whether a missing access/write watch is actually inactive.

## Live validation

Focused live validation on the reopened Cheat Engine session showed:

- access watch: captured repeated hits
- write watch: captured repeated hits
- execute watch: captured repeated hits
- after starting all three watches:
  - `count = 3`
  - `active_watch_count = 3`
- `raw_count` remains available separately because its exact value can vary by CE build and debugger interface
- after `ce.debug_watch_stop` on the execute watch:
  - `count = 2`
- after `ce.debug_watch_stop_all`:
  - `count = 0`
  - `raw_count = 0`

The full live suite also passed against `Minecraft.Windows.exe` with `210/210` tools invoked.

## Related work

The earlier teardown and freeze-recovery pass is documented in `docs/TIMEOUT_AND_PARALLEL_EXECUTION_REWRITE_2026-03-08.md`.
