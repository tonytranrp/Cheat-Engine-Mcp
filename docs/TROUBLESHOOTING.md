# Troubleshooting

This document covers the manual checks, common failure modes, and recovery steps for Cheat Engine MCP.

## Quick Triage

When something is wrong, check these first:

1. Is Cheat Engine running?
2. Is the stable loader DLL registered and enabled?
3. Did you load `ce_mcp_plugin.dll`, not `ce_mcp_plugin_core.dll`?
4. Is the backend listening on the same bridge port as the plugin? Default: `127.0.0.1:5556`
5. Is Codex using a working MCP server command?

## Manual Smoke Tests

### Confirm the plugin is alive

Use the direct bridge caller:

```powershell
python .\tools\dev\run-mcp-call.py --port 5556 --tool ce.get_attached_process --show-hello
```

Expected result:

- you receive a `hello` payload from the CE plugin
- you receive a `result` payload for `ce.get_attached_process`

If this works, the CE plugin is alive and the problem is on the MCP backend or Codex side.

### Run the repo live suite against a specific game

For development validation, the live suite can target a custom process instead of the default smoke target:

```powershell
py -3 .\tools\dev\run-live-tool-suite.py --process-name "Tic-tak-toe.exe"
```

If the normal backend is already listening on `5556`, let the script stop and restart it for the run:

```powershell
py -3 .\tools\dev\run-live-tool-suite.py --process-name "Minecraft.Windows.exe" --manage-existing-backend
```

You can also set:

```powershell
$env:CE_MCP_PRIMARY_PROCESS = "Tic-tak-toe.exe"
```

Benchmark the same target with timing summaries:

```powershell
py -3 .\tools\dev\benchmark-live-tools.py --process-name "Minecraft.Windows.exe" --manage-existing-backend
```

### List loaded modules from the current target

```powershell
python .\tools\dev\run-mcp-call.py --port 5556 --tool ce.list_modules --field limit=20
```

### Read memory directly

```powershell
python .\tools\dev\run-mcp-call.py --port 5556 --tool ce.read_memory --field address=\"Minecraft.Windows.exe+0\" --field size=16
```

## Common Errors

Structured tool failures now include helper fields such as:

- `error_code`
- `hint`
- `details`
- `next_steps`
- `required_order`
- `example`
- `risk`

When a tool fails, prefer those fields over the raw `error` string. They are the intended recovery path for invalid orderings, unsupported debugger operations, and bad scan parameters.

### `MCP client for cheat-engine failed to start: connection closed: initialize response`

Meaning:

- the Codex MCP process started
- the server process exited before it completed MCP initialization

Most common cause on this project:

- the packaged `npx` launcher did not bootstrap its Python runtime correctly on the local machine

Recommended fix:

Use the direct Python backend in Codex instead of the `npx` launcher.

```toml
[mcp_servers.cheat-engine]
command = 'C:\Path\To\Python\python.exe'
args = ["-m", "ce_mcp_server"]
startup_timeout_sec = 120
```

Then restart Codex or reload MCP servers.

If you prefer the local source tree instead of a global install:

```powershell
pip install -e .
ce-mcp-server --help
```

### `MCP client for cheat-engine timed out after 10 seconds`

Meaning:

- Codex gave up waiting for the MCP server to finish startup

Fix:

- increase `startup_timeout_sec`
- `120` is a safe default on this project

Example:

```toml
[mcp_servers.cheat-engine]
startup_timeout_sec = 120
```

### `MCP startup incomplete (failed: ida-local, cheat-engine)`

Meaning:

- at least one MCP server failed

Important:

- `ida-local` and `cheat-engine` are independent
- a broken `ida-local` server does not mean the Cheat Engine side is broken

Fix:

- debug each MCP server separately
- do not assume one failure explains the other

### `no Cheat Engine session is connected`

Meaning:

- the backend is running, but no CE plugin client has connected to it

Fix:

1. Open Cheat Engine.
2. Ensure the plugin is enabled in `Edit -> Settings -> Plugins`.
3. Ensure the registered DLL is `ce_mcp_plugin.dll`.
4. Confirm the bridge port matches on both sides.
5. Run the direct bridge smoke test from this document.

### `plugin dll could not be loaded` / error `192` / `193`

Meaning:

- Windows rejected the DLL

Common causes:

- x86/x64 mismatch between Cheat Engine and the plugin
- missing runtime dependency
- wrong DLL selected

Fix:

- use x64 CE with the x64 plugin build
- load `ce_mcp_plugin.dll`
- do not load `ce_mcp_plugin_core.dll` directly

### Cheat Engine opens, but Codex cannot call any tools

Check:

1. `ce.verify_target`
2. `ce.get_attached_process`
3. `ce.list_tools`
4. `ce.bridge_status`

Important:

- `ce.list_tools` only shows the native plugin tool subset
- it does not include runtime-backed tools such as scans, pointers, tables, structures, or debug helpers registered by the Python MCP server

If direct bridge calls work but Codex MCP calls fail:

- the problem is in the MCP backend or Codex registration
- the CE plugin is not the problem
- from Codex or any MCP client, use `ce.verify_target` as the fastest full-stack sanity check

### `ce.structure_read` returns empty fields or obvious nulls

Meaning:

- the structure definition exists, but the address is wrong
- or the field layout does not match the live target object

Checks:

1. Confirm the target is attached with `ce.verify_target`
2. Resolve the base expression first with `ce.normalize_address`
3. Verify the structure definition with `ce.structure_get`
4. If needed, rebuild the structure from a live address with `ce.structure_auto_guess`

Recommended pattern:

```text
ce.verify_target()
ce.normalize_address(address="Tic-tak-toe.exe+1202E0")
ce.structure_read(name="Field", address="Tic-tak-toe.exe+1202E0", max_depth=2, include_raw=True)
```

Important:

- `ce.structure_read` does not guess offsets on its own
- it reads a live instance using the current CE structure definition
- if a child element is declared as a pointer-to-structure, the tool will dereference it and recurse until `max_depth`

### Lua `require` still cannot find my external library

Meaning:

- the Lua package environment inside Cheat Engine does not include the directory or DLL search path you expect

Checks:

1. Inspect the active search environment with `ce.lua_get_environment`
2. Add or replace search paths with `ce.lua_configure_environment`
3. For one-off source modules, preload them with `ce.lua_preload_module` or `ce.lua_preload_file`

Recommended pattern:

```text
ce.lua_configure_environment(
  library_roots=["C:/ce-libs"],
  package_paths=["C:/ce-libs/?.lua", "C:/ce-libs/?/init.lua"],
  package_cpaths=["C:/ce-libs/?.dll"],
  prepend=True,
)
```

Important:

- `ce.lua_add_library_root` expands to Lua `package.path` and `package.cpath` conventions, but it does not remove stale entries
- use `ce.lua_remove_library_root`, `ce.lua_remove_package_path`, and `ce.lua_remove_package_cpath` when cleaning up a polluted session
- use `ce.lua_reset_environment` to remove paths previously added through `ce.lua_configure_environment`
- `ce.lua_preload_module` and `ce.lua_preload_file` bypass path lookup entirely and are the fastest option for controlled module injection

### Repeated Lua/runtime calls feel slower than expected after editing the backend

Meaning:

- the running MCP backend is still using an older Python process or older cached runtime module

Fixes:

- restart the `ce_mcp_server` process after pulling new backend code
- reconnect Cheat Engine if you changed runtime module versions and want a clean session
- run `ce.verify_target` once after reconnecting to confirm the bridge is stable

Important:

- `0.2.5` caches a CE-side dispatcher per session for lower steady-state latency
- if you are still seeing pre-`0.2.5` behavior, the most likely issue is a stale backend process

### AOB scans time out

Meaning:

- the scan is too broad for the current timeout budget

Important:

- `ce.aob_scan` is the right tool for raw byte patterns
- it is not the best tool for normal text search
- for strings, prefer `ce.scan_string`
- for typed CE memscan workflows, prefer `ce.scan_value` or `ce.scan_once`

Fixes:

- add `module_name`
- add `start_address` / `end_address`
- lower `max_results`
- use the persistent scan tools instead of a single full-process AOB scan:
  - `ce.scan_create_session`
  - `ce.scan_first`
  - `ce.scan_wait`
  - `ce.scan_get_results`

Preferred pattern:

```text
ce.aob_scan(pattern="69 6E 76 65 6E 74 6F 72 79", module_name="Minecraft.Windows.exe", max_results=20)
```

Preferred text-search pattern:

```text
ce.scan_string(text="inventory", encoding="both", module_name="Minecraft.Windows.exe")
```

### `list_modules` or `resolve_symbol` times out after a previous long scan

Meaning:

- the CE bridge processes one request at a time per session
- a long-running scan can block later requests behind it

Fixes:

- wait for the long scan to finish
- narrow the scan scope
- restart the MCP backend if the session is wedged
- prefer scan-session tools for heavier search workflows

### Loader changes do not appear after rebuild

Meaning:

- the stable loader DLL is still mapped inside Cheat Engine

Important:

- core changes can hot-reload
- loader changes require a CE restart

Fix:

```powershell
cmake --build build --target ce_mcp_loader_deploy ce_mcp_core
.\tools\dev\restart-cheat-engine.ps1 -ReloadCore
```

### Core changes do not appear after rebuild

Fix:

```powershell
.\tools\dev\update-core.ps1
```

If that fails:

```powershell
.\tools\dev\plugin-control.ps1 -Command status
```

Then restart Cheat Engine if needed.

### Port `5556` is already in use

Meaning:

- another process is already bound to the CE bridge port

Fixes:

- stop the conflicting process
- or run the backend on a different port and configure the CE side to match

To find the conflicting process:

```powershell
Get-NetTCPConnection -LocalPort 5556 | Select-Object LocalAddress,LocalPort,State,OwningProcess
```

### `No module named mcp`

Meaning:

- you are launching the backend from a Python environment that does not have the MCP SDK installed

Fix:

```powershell
pip install -e .
```

Or use a Python installation where `ce_mcp_server` and `mcp` are already installed.

## Manual Development Workflows

### Build native targets

```powershell
cmake --fresh -S . -B build -G "NMake Makefiles"
cmake --build build --target ce_mcp_loader_deploy ce_mcp_core
```

### Hot-reload the core DLL

```powershell
.\tools\dev\update-core.ps1
```

### Restart Cheat Engine and promote any staged loader update

```powershell
.\tools\dev\restart-cheat-engine.ps1 -ReloadCore
```

### Run a single direct bridge call

```powershell
python .\tools\dev\run-mcp-call.py --port 5556 --tool ce.list_tools
```

## Example: Searching for Inventory Strings in Minecraft

Direct bridge example:

```powershell
python .\tools\dev\run-mcp-call.py --port 5556 --tool ce.aob_scan --field pattern='\"69 6E 76 65 6E 74 6F 72 79\"' --field module_name='\"Minecraft.Windows.exe\"' --field max_results=20
```

If you want a narrower string:

```powershell
python .\tools\dev\run-mcp-call.py --port 5556 --tool ce.aob_scan --field pattern='\"69 6E 76 65 6E 74 6F 72 79 5F 69 74 65 6D 73\"' --field module_name='\"Minecraft.Windows.exe\"' --field max_results=10
```

## Reporting Bugs

When filing an issue, include:

1. Cheat Engine version
2. Windows version
3. whether you loaded `ce_mcp_plugin.dll` or the wrong DLL
4. the exact Codex MCP config for `cheat-engine`
5. the exact error text
6. whether the direct bridge smoke test succeeds
7. whether the problem is startup, attach, scan, memory IO, Lua, or table-related

Good bug report example:

```text
Cheat Engine 7.x x64
Windows 11 x64
Loaded build/loader/ce_mcp_plugin.dll
Codex cheat-engine server uses python.exe -m ce_mcp_server
Error: tool 'ce.aob_scan' timed out after 10.0s
Direct bridge test: ce.get_attached_process works
Problem category: long scan timeout
```
