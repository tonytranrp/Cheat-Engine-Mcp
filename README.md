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
  - 151 MCP tools currently registered
  - process, modules, symbols, memory, scans, pointer chains, tables, records, exported SDK fields
- Raw SDK visibility
  - full copied `ExportedFunctions` block exposed through MCP metadata tools

## Quick Start

### Codex install command

GitHub-backed `npx` command:

```powershell
codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
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

Current MCP tool count: `151`

### Native bridge and session tools

- `ce.bridge_status`
- `ce.list_sessions`
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
- `ce.auto_assemble`
- `ce.lua_call`
- `ce.lua_get_global`
- `ce.lua_set_global`
- `ce.run_script_file`

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

Create a scan session and inspect CE scan enums:

```text
ce.scan_list_enums()
ce.scan_create_session()
```

Create a temporary table record:

```text
ce.record_create(options={
  "description": "health",
  "address": "game.exe+123456",
  "type": "dword"
})
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

Expected Windows release assets:

- `ce_mcp_plugin.dll`
- `ce_mcp_plugin_core.dll`
- `cheat-engine-mcp-windows-x64.zip`

The loader DLL is the file you register in Cheat Engine.
The core DLL is the hot-swapped backend module loaded by the loader.

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

## Notes

- Cheat Engine side transport defaults to `127.0.0.1:5556`.
- The raw exported-function catalog currently reports all copied fields, including undocumented `PVOID` entries.
- Typed, safe wrappers are exposed as dedicated MCP tools. Raw pointer-only fields are exposed for inspection, not generic invocation.
- `ce.scan_new` exists but is not part of the recommended quick-start flow yet.
