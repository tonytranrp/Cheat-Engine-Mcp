# Cheat Engine MCP

Cheat Engine MCP is a Windows-first MCP server and Cheat Engine plugin pair.
It gives Codex a live Cheat Engine backend for process attach, memory access, pointer chains, scans, table records, Lua scripting, and raw `ExportedFunctions` introspection.

## Features

- Hot-reloadable Cheat Engine plugin architecture
  - stable loader DLL inside Cheat Engine
  - swappable core DLL for fast iteration
- Packaged MCP backend
  - `ce-mcp-server` Python entrypoint
  - `npx` launcher for Codex setup without `.py` paths
- Live Cheat Engine scripting
  - `ce.lua_eval`
  - `ce.lua_exec`
  - `ce.auto_assemble`
  - `ce.lua_call`
- Broad MCP surface
  - 210+ MCP tools currently registered
  - process, modules, symbols, memory, scans, pointer chains, tables, records, exported SDK fields
- Raw SDK visibility
  - full copied `ExportedFunctions` block exposed through MCP metadata tools

## What Changed In 0.2.8

This pass hardens the freeze-prone bridge paths, moves native request handling onto a parallel worker queue, and makes the slowest memory/dissect workflows fail fast instead of wedging the whole CE session.

### Fixes and behavior changes

- The native CE bridge client no longer runs tool calls on the socket thread. Incoming `call` messages are queued and processed by a small worker pool, so one long request stops blocking unrelated reads, Lua calls, and bounded scans.
- `ce.query_memory_map` and native AOB scans now honor an internal deadline from the MCP timeout budget and return `timed_out` plus `truncated` instead of running until the client gives up.
- Python-side bridge timeouts now poison the stuck CE session on purpose. A timed-out request closes the session so later calls do not pile up forever behind a wedged operation.
- `ce.dissect_module` no longer does one monolithic `DissectCode` pass over the full module. It resolves committed executable regions, chunks them, and feeds them to `ce.dissect_region` under a rolling timeout budget.
- Same-target `ce.attach_process` remains on the faster short-circuit path, which keeps repeated attach-heavy workflows cheap during validation and scripting loops.
- The live validation harness now restores detached bridge listeners with `--transport bridge-only` instead of trying to relaunch a background stdio server that immediately exits.
- The dev harness now refuses to tear down a stdio-backed `ce_mcp_server` process when `--manage-existing-backend` would sever an active MCP client transport.

### Tooling and test improvements

- Unit coverage now exercises timeout-session teardown, bridge-only restore behavior, and the new stdio-backend safety guard in the live harness.
- Full live suite against `Minecraft.Windows.exe`: `210/210` tools passed in `18.37s`.
- Focused live timings from the latest Minecraft benchmark:
  - `ce.attach_process(same target)`: avg `14.06 ms`
  - `ce.verify_target`: avg `9.004 ms`
  - `ce.normalize_address`: avg `1.364 ms`
  - `ce.read_integer`: avg `0.874 ms`
  - `ce.structure_read`: avg `3.297 ms`
  - `ce.scan_once`: avg `38.623 ms`
  - `ce.aob_scan(range,x16)`: avg `0.61 ms`
  - `ce.scan_string(range,ascii)`: avg `0.614 ms`
  - `parallel_mixed_light`: `24` calls across `8` workers in `24.502 ms` wall time
- Full details for this pass live in `docs/TIMEOUT_AND_PARALLEL_EXECUTION_REWRITE_2026-03-08.md`.

### Repository layout

- Native CE plugin code lives under `native/`
- Installable MCP backend lives under `python/src/ce_mcp_server/`
- Dev-only operators and test runners live under `tools/dev/`
- Vendored `libhat` lives under `native/vendor/libhat/`
- The loader/core split remains:
  - `ce_mcp_plugin.dll`: stable Cheat Engine loader
  - `ce_mcp_plugin_core.dll`: hot-swappable runtime core

## Quick Start

### Documentation

- Setup and usage: [README.md](README.md)
- Troubleshooting and manual recovery: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

### Codex install command

GitHub-backed `npx` command:

```powershell
codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
```

If the packaged `npx` launcher is unstable on your machine, use the direct Python backend instead:

```toml
[mcp_servers.cheat-engine]
command = 'C:\Path\To\Python\python.exe'
args = ["-m", "ce_mcp_server"]
startup_timeout_sec = 120
```

Local installed command:

```powershell
codex mcp add cheat-engine -- ce-mcp-server
```

Inspect the registration later:

```powershell
codex mcp get cheat-engine
codex mcp list
```

## Cheat Engine Setup

1. Build the native targets:

```powershell
cmake --fresh -S . -B build -G "NMake Makefiles"
cmake --build build --target ce_mcp_loader_deploy ce_mcp_core
```

2. In Cheat Engine, load the stable loader plugin:

```text
build/loader/ce_mcp_plugin.dll
```

3. Leave that loader enabled.

Do not point Cheat Engine directly at `ce_mcp_plugin_core.dll`.

## How It Works

```text
Codex
  -> stdio MCP transport
  -> ce-mcp-server
  -> TCP bridge (127.0.0.1:5556)
  -> ce_mcp_plugin.dll loader inside Cheat Engine
  -> ce_mcp_plugin_core.dll hot-swappable bridge core
  -> Cheat Engine APIs / Lua / ExportedFunctions
```

## Tool Surface

Current registered MCP tool count: `210`

### Native bridge and session tools

`ce.list_tools` reports the native plugin subset only. It does not enumerate the full runtime-backed MCP surface registered by the Python server.

- `ce.bridge_status`
- `ce.list_sessions`
- `ce.normalize_address`
- `ce.verify_target`
- `ce.list_tools`
- `ce.get_attached_process`
- `ce.attach_process`
- `ce.detach_process`
- `ce.get_process_list`
- `ce.list_modules`
- `ce.list_modules_full`
- `ce.query_memory`
- `ce.query_memory_map`
- `ce.resolve_symbol`
- `ce.aob_scan`
- `ce.read_memory`
- `ce.write_memory`

### CE scripting tools

- `ce.lua_eval`
- `ce.lua_exec`
- `ce.lua_eval_with_globals`
- `ce.lua_exec_with_globals`
- `ce.auto_assemble`
- `ce.lua_call`
- `ce.lua_get_global`
- `ce.lua_set_global`
- `ce.run_script_file`

### Lua package and module tools

- `ce.lua_get_package_paths`
- `ce.lua_get_environment`
- `ce.lua_add_package_path`
- `ce.lua_remove_package_path`
- `ce.lua_add_package_cpath`
- `ce.lua_remove_package_cpath`
- `ce.lua_add_library_root`
- `ce.lua_remove_library_root`
- `ce.lua_configure_environment`
- `ce.lua_reset_environment`
- `ce.lua_require_module`
- `ce.lua_unload_module`
- `ce.lua_list_loaded_modules`
- `ce.lua_list_preloaded_modules`
- `ce.lua_preload_module`
- `ce.lua_preload_file`
- `ce.lua_unpreload_module`
- `ce.lua_call_module_function`
- `ce.lua_run_file`

### ExportedFunctions tools

- `ce.exported.list`
- `ce.exported.get`
- `ce.exported.list_available`
- `ce.exported.list_typed_functions`
- `ce.exported.list_pointer_fields`
- `ce.exported.search_fields`
- `ce.exported.get_many`

### Process and symbol tools

- `ce.get_ce_version`
- `ce.get_cheat_engine_dir`
- `ce.get_process_id_from_name`
- `ce.get_foreground_process`
- `ce.get_cpu_count`
- `ce.target_is_64bit`
- `ce.get_window_list`
- `ce.get_common_module_list`
- `ce.get_auto_attach_list`
- `ce.set_auto_attach_list`
- `ce.add_auto_attach_target`
- `ce.remove_auto_attach_target`
- `ce.pause_process`
- `ce.unpause_process`
- `ce.get_address`
- `ce.get_address_safe`
- `ce.get_name_from_address`
- `ce.register_symbol`
- `ce.unregister_symbol`
- `ce.reinitialize_symbolhandler`
- `ce.in_module`
- `ce.in_system_module`
- `ce.aob_scan_unique`
- `ce.aob_scan_module_unique`

### Memory tools

Representative tools:

- `ce.read_bytes_table`
- `ce.read_integer`
- `ce.read_qword`
- `ce.read_pointer`
- `ce.read_float`
- `ce.read_double`
- `ce.read_string_ex`
- `ce.write_bytes_values`
- `ce.write_integer`
- `ce.write_qword`
- `ce.write_pointer`
- `ce.write_float`
- `ce.write_double`
- `ce.write_string_ex`
- local-process variants for the same read/write groups
- `ce.allocate_memory`
- `ce.dealloc`
- `ce.full_access`

### Pointer chain tools

- `ce.resolve_pointer_chain`
- `ce.read_pointer_chain_byte`
- `ce.read_pointer_chain_bytes`
- `ce.read_pointer_chain_small_integer`
- `ce.read_pointer_chain_integer`
- `ce.read_pointer_chain_qword`
- `ce.read_pointer_chain_pointer`
- `ce.read_pointer_chain_float`
- `ce.read_pointer_chain_double`
- `ce.read_pointer_chain_string`
- matching `ce.write_pointer_chain_*` tools

### Scan tools

- `ce.scan_list_enums`
- `ce.scan_create_session`
- `ce.scan_destroy_session`
- `ce.scan_destroy_all_sessions`
- `ce.scan_list_sessions`
- `ce.scan_get_state`
- `ce.scan_first`
- `ce.scan_next`
- `ce.scan_wait`
- `ce.scan_get_progress`
- `ce.scan_attach_foundlist`
- `ce.scan_detach_foundlist`
- `ce.scan_get_result_count`
- `ce.scan_get_results`
- `ce.scan_save_results`
- `ce.scan_set_only_one_result`
- `ce.scan_get_only_result`
- `ce.scan_first_ex`
- `ce.scan_next_ex`
- `ce.scan_collect`
- `ce.scan_once`
- `ce.scan_value`
- `ce.scan_string`

## Structured Errors

Invalid MCP operations now return structured guidance instead of only a raw error string.

Typical fields:

- `error`: human-readable summary of what failed
- `error_code`: stable machine-readable code such as `scan_wait_required`
- `error_category`: broad class such as `usage` or `state`
- `hint`: short corrective guidance
- `details`: structured metadata about the bad input or missing state
- `next_steps`: ordered recovery actions
- `required_order`: workflow order when the tool must be used in sequence
- `example`: a valid example call when one is useful
- `risk`: why the invalid operation is unsafe or misleading

Example:

```json
{
  "ok": false,
  "error": "A completed first scan is required before this follow-up scan.",
  "error_code": "scan_first_scan_required",
  "error_category": "state",
  "hint": "ce.scan_next_ex refines an existing result set; it does not create the initial one.",
  "required_order": [
    "ce.scan_create_session",
    "ce.scan_first_ex",
    "ce.scan_wait",
    "ce.scan_next_ex"
  ],
  "example": "ce.scan_first_ex(scan_session_id=\"scan-1\", scan_option=\"exact\", value_type=\"dword\", value=100)"
}
```

This is used for:

- invalid scan sequencing such as calling `ce.scan_next_ex` before a completed first scan
- result collection before `ce.scan_wait`
- unsupported debugger watch or breakpoint operations
- bad enum values, encodings, address expressions, and module scopes

### Cheat table and record tools

- `ce.table_record_count`
- `ce.table_refresh`
- `ce.table_rebuild_description_cache`
- `ce.table_disable_all_without_execute`
- `ce.table_load`
- `ce.table_save`
- `ce.table_create_file`
- `ce.table_find_file`
- `ce.table_export_file`
- `ce.table_get_selected_record`
- `ce.table_set_selected_record`
- `ce.record_list`
- `ce.record_get_by_id`
- `ce.record_get_by_description`
- `ce.record_find_all_by_description`
- `ce.record_create`
- `ce.record_create_many`
- `ce.record_create_group`
- `ce.record_delete`
- `ce.record_set_description`
- `ce.record_set_address`
- `ce.record_set_type`
- `ce.record_set_value`
- `ce.record_set_active`
- `ce.record_get_offsets`
- `ce.record_set_offsets`
- `ce.record_get_script`
- `ce.record_set_script`

### Structure and dissect tools

- `ce.structure_list`
- `ce.structure_get`
- `ce.structure_create`
- `ce.structure_define`
- `ce.structure_add_element`
- `ce.structure_auto_guess`
- `ce.structure_fill_from_dotnet`
- `ce.structure_read`
- `ce.structure_delete`
- `ce.dissect_clear`
- `ce.dissect_module`
- `ce.dissect_region`
- `ce.dissect_get_references`
- `ce.dissect_get_referenced_strings`
- `ce.dissect_get_referenced_functions`
- `ce.dissect_save`
- `ce.dissect_load`

### Debug and watch tools

- `ce.debug_status`
- `ce.debug_start`
- `ce.debug_continue`
- `ce.debug_list_breakpoints`
- `ce.debug_watch_accesses_start`
- `ce.debug_watch_writes_start`
- `ce.debug_watch_execute_start`
- `ce.debug_watch_get_hits`
- `ce.debug_watch_stop`
- `ce.debug_watch_stop_all`

## Example MCP Calls

Attach Cheat Engine to a target by name:

```text
ce.attach_process(process_name="Minecraft.Windows.exe")
```

Read the PE header from the attached module:

```text
ce.read_bytes_table(address="Minecraft.Windows.exe+0", count=8)
```

Resolve a pointer chain:

```text
ce.resolve_pointer_chain(base_address="Minecraft.Windows.exe+0", offsets=[])
```

Inspect the raw copied SDK field for `GetLuaState`:

```text
ce.exported.get(field_name="GetLuaState")
```

Run Lua directly inside Cheat Engine:

```text
ce.lua_exec(script="return {pid=getOpenedProcessID(), target=process, is64=targetIs64Bit()}")
```

Run Lua with temporary globals instead of mutating `_G` yourself:

```text
ce.lua_eval_with_globals(script="player_name .. ':' .. tostring(limit_value)", globals={"player_name": "Alex", "limit_value": 7})
```

Batch-configure external Lua roots and DLL search paths:

```text
ce.lua_configure_environment(
  library_roots=["C:/ce-libs"],
  package_paths=["C:/ce-libs/custom/?.lua"],
  package_cpaths=["C:/ce-libs/bin/?.dll"],
  prepend=True
)
```

Create a scan session and inspect CE scan enums:

```text
ce.scan_list_enums()
ce.scan_create_session()
```

Search for a plain or wide string without hand-building AOB hex:

```text
ce.scan_string(text="inventory", encoding="both", module_name="Minecraft.Windows.exe")
```

Run a libhat-backed signature scan with PE-section scoping and alignment controls:

```text
ce.aob_scan(
  pattern="48 8D 0D ?? ?? ?? ?? E9 ?? ?? ?? ?? CC CC CC CC",
  module_name="Minecraft.Windows.exe",
  section_name=".text",
  scan_alignment="x16",
  scan_hint="x86_64",
  max_results=4
)
```

Run a one-shot typed value scan:

```text
ce.scan_value(value=100, value_type="dword", scan_option="exact")
```

Run a one-shot generic CE memscan with explicit scan semantics:

```text
ce.scan_once(scan_option="exact", value_type="string", value="slot", module_name="Minecraft.Windows.exe")
```

Create a temporary table record:

```text
ce.record_create(options={
  "description": "health",
  "address": "game.exe+123456",
  "type": "dword"
})
```

Resolve and normalize an address expression before using it in a raw-memory workflow:

```text
ce.normalize_address(address="game.exe+123456")
```

Quick-check that the current CE session is attached to the expected target:

```text
ce.verify_target()
```

Create a grouped record layout in one call:

```text
ce.record_create_group(
  description="Player",
  records=[
    {"description": "health", "address": "game.exe+123456", "type": "4 Bytes"},
    {"description": "inventory_ptr", "address": "game.exe+123460", "type": "pointer"}
  ]
)
```

Read a defined structure instance at a live address:

```text
ce.structure_read(name="Player", address="game.exe+123456", max_depth=2, include_raw=True)
```

## One-Time Local Installation

If you want the plain executable entrypoint locally:

```powershell
pip install -e .
ce-mcp-server --help
```

If you want to test the Node launcher locally:

```powershell
npm exec --yes . -- --help
```

## Native Build Layout

### `native/`

- `native/src/loader/`: stable Cheat Engine loader plugin
- `native/src/core/core_exports.cpp`: DLL export shim
- `native/src/core/core_exported_tools.cpp`: `ExportedFunctions` MCP surface
- `native/src/core/core_runtime.cpp`: request dispatch and runtime config
- `native/src/core/core_lua_tools.cpp`: direct Lua bridge through `GetLuaState`
- `native/src/core/core_process_tools.cpp`: process/module/symbol tools
- `native/src/core/core_memory_tools.cpp`: memory map/read/write/AOB tools
- `native/src/core/core_support.cpp`: Win32 and parsing helpers

### `python/`

- `python/src/ce_mcp_server/bridge.py`: persistent CE TCP bridge
- `python/src/ce_mcp_server/context.py`: Lua/runtime/native call helpers
- `python/src/ce_mcp_server/registration.py`: dynamic MCP tool registration
- `python/src/ce_mcp_server/tools/`: MCP tool categories split by domain
- `python/src/ce_mcp_server/runtime/`: CE-side Lua helper modules split by domain

### `tools/`

- `tools/dev/`: local build/hot-reload/restart helpers
- `tools/release/`: release packaging helpers

## Release Assets

Versioned Windows release bundles live under `releases/<version>/` in the tagged repo snapshot.

For `v0.2.8`, use:

- `releases/v0.2.8/ce_mcp_plugin.dll`
- `releases/v0.2.8/ce_mcp_plugin_core.dll`
- `releases/v0.2.8/cheat-engine-mcp-0.2.8-windows-x64.zip`
- `releases/v0.2.8/SHA256SUMS.txt`

Each release ZIP contains:

- `ce_mcp_plugin.dll`
- `ce_mcp_plugin_core.dll`
- `README.md`
- `INSTALL.txt`

The loader DLL is the file you register in Cheat Engine.
The core DLL is the hot-swapped backend module loaded by the loader.

Prebuilt install guide:

- [docs/INSTALL_PREBUILT_WINDOWS.md](docs/INSTALL_PREBUILT_WINDOWS.md)
- [releases/v0.2.8/README.md](releases/v0.2.8/README.md)

## Development

Core-only changes:

```powershell
.\tools\dev\update-core.ps1
```

Loader changes:

```powershell
cmake --build build --target ce_mcp_loader_deploy ce_mcp_core
.\tools\dev\restart-cheat-engine.ps1 -ReloadCore
```

## Testing

Unit tests:

```powershell
py -3.14 -m unittest discover -s tests -v
```

Live Cheat Engine integration suite:

```powershell
$env:CE_MCP_RUN_LIVE = "1"
py -3.14 tools\dev\run-live-tool-suite.py --process-name "Minecraft.Windows.exe"
```

Live benchmark runner:

```powershell
py -3.14 tools\dev\benchmark-live-tools.py --process-name "Minecraft.Windows.exe"
```

The live suite expects:

- Cheat Engine running
- the stable loader plugin enabled
- a live CE bridge session connected to the backend
- an attachable target process for memory, scan, and debugger coverage

Latest Minecraft audit:

- [docs/MINECRAFT_LIVE_AUDIT_2026-03-08.md](docs/MINECRAFT_LIVE_AUDIT_2026-03-08.md)
- [docs/LIBHAT_SIGSCAN_REWRITE_2026-03-08.md](docs/LIBHAT_SIGSCAN_REWRITE_2026-03-08.md)
- [docs/TIMEOUT_AND_PARALLEL_EXECUTION_REWRITE_2026-03-08.md](docs/TIMEOUT_AND_PARALLEL_EXECUTION_REWRITE_2026-03-08.md)

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for:

- Codex MCP startup failures
- wrong DLL / x86-x64 mismatch problems
- no-session / no-bridge cases
- long-scan timeout recovery
- manual bridge smoke tests
- core hot-reload vs loader restart workflows
- bug report checklist

Short version:

- use `ce.aob_scan` for raw byte patterns
- add `module_name`, `section_name`, or explicit `start_address` / `end_address` whenever you can
- use `scan_alignment="x16"` for aligned code/data signatures when the target address is 16-byte aligned
- use `ce.scan_string` for text
- use `ce.scan_value` or `ce.scan_once` for CE memscan-style typed value scans
- for isolated live validation on a machine that already has an interactive stdio backend, move the CE plugin to a separate bridge port instead of stopping the active backend in place

## Notes

- Cheat Engine side transport defaults to `127.0.0.1:5556`.
- The raw exported-function catalog currently reports all copied fields, including undocumented `PVOID` entries.
- Typed, safe wrappers are exposed as dedicated MCP tools. Raw pointer-only fields are exposed for inspection, not generic invocation.
- `ce.list_tools` reports only the native bridge tools advertised by the plugin. Use the README tool-surface section or the Python registry for the full MCP list.
- Runtime-backed structure and Lua helpers are cached per session and reload automatically when the bridge session changes.
- `ce.scan_new` exists but is not part of the recommended quick-start flow yet.
