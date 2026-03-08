# Live Usage Review 2026-03-08

This document records the real issues found during live use against `Tic-tak-toe.exe`, and the changes shipped in `0.2.4` and `0.2.5` to close them.

## Fixed In 0.2.4

### 1. Native raw-memory tools now accept symbolic addresses consistently

Fixed tools:

- `ce.query_memory`
- `ce.query_memory_map`
- `ce.aob_scan`
- `ce.read_memory`
- `ce.write_memory`
- `ce.resolve_symbol(address=...)`

Before this fix, the Python tool surface documented `int | str`, but the native bridge accepted only raw integers in several paths.

Implementation:

- Added shared `parse_or_resolve_address(...)` handling in the native bridge
- Reused that path across direct address reads and range-based native APIs

## 2. Cheat-table record types now accept common CE UI labels

Fixed behavior:

- `ce.record_set_type(record_id=..., value_type="4 Bytes")`
- `ce.record_create(options={"type": "4 Bytes"})`
- `ce.record_create_many(...)`
- `ce.record_create_group(...)`

Accepted aliases now include common UI strings such as:

- `4 Bytes`
- `8 Bytes`
- `Byte Array`
- `Auto Assembler`

The table runtime also returns cleaner `invalid_record_type:*` messages instead of leaking raw Lua traceback noise.

## 3. Added missing workflow helpers discovered during live use

New tools:

- `ce.normalize_address`
- `ce.verify_target`
- `ce.record_create_many`
- `ce.record_create_group`

These cover the manual workflows that kept recurring during live CE analysis:

- resolve an expression before a raw-memory call
- confirm the current attachment and main module quickly
- build grouped CE record layouts without dropping to ad hoc Lua

## Verification

Validated in the repo after the fix pass:

- Python registry count increased from `192` to `196`
- README, troubleshooting, and release metadata updated to `0.2.4`
- Live suite coverage extended to exercise symbolic native-address paths and the new record helpers

## Follow-Up

This review started as an issue list. It is now a shipped-fix record for the `0.2.4` release.

## Fixed In 0.2.5

### 1. Structure analysis now has a direct live-instance dump path

New tool:

- `ce.structure_read`

This closes the gap between defining a structure and actually dumping a live object as named fields. The new path supports:

- scalar field reads by CE vartype
- raw-byte snapshots for each element
- nested child structures
- pointer-to-structure dereference and recursion

This is the missing piece for workflows like:

- define a `Field` layout for `Tic-tak-toe.exe`
- point the tool at `Tic-tak-toe.exe+1202E0`
- dump the live object in a single MCP call

### 2. Lua library workflows now support real environment management

New tools:

- `ce.lua_get_environment`
- `ce.lua_configure_environment`
- `ce.lua_remove_package_path`
- `ce.lua_remove_package_cpath`
- `ce.lua_list_loaded_modules`
- `ce.lua_list_preloaded_modules`
- `ce.lua_preload_module`
- `ce.lua_preload_file`
- `ce.lua_unpreload_module`
- `ce.lua_eval_with_globals`
- `ce.lua_exec_with_globals`

These were added to support practical CE scripting instead of single-string `lua_eval` calls only. The new runtime now handles:

- external Lua search path setup
- explicit cleanup of stale package entries
- preloading source or file-backed modules without relying on search paths
- temporary globals injection without permanently mutating `_G`

### 3. Repeated runtime calls now pay less per-call overhead

The Python backend previously rebuilt larger wrapper scripts for many runtime-backed Lua calls. `0.2.5` now loads a CE-side dispatcher once per session and reuses compact call sites for:

- runtime module dispatch
- direct global Lua calls

This reduces repeated boilerplate, lowers steady-state latency, and keeps the runtime/module cache behavior more predictable across live sessions.

## Verification

Validated in the repo after the `0.2.5` pass:

- Python registry count increased from `196` to `208`
- README, release metadata, and troubleshooting docs updated to `0.2.5`
- Unit coverage extended for structure-instance dumping and globals-scoped Lua execution
- Live integration coverage extended for structure reads plus Lua environment/preload workflows
- The dev live suite now accepts a target-process override and was hardened for repeated runs and debugger-capability differences

## Status

This review is now the shipped-fix record for the `0.2.4` and `0.2.5` releases.
