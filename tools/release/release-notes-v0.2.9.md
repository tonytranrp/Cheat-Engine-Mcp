# Cheat Engine MCP v0.2.9

## Highlights

- fixed `ce.debug_list_breakpoints` so it reports the effective active watch set instead of only the raw Cheat Engine breakpoint list
- added `raw_count` and `raw_breakpoints` so the original CE debugger output is still available when needed
- added `active_watch_count` and `watch_breakpoints` so hardware access/write watches are visible even when CE does not surface them in `debug_getBreakpointList()`
- kept the `0.2.8` watch teardown fix and validated that `ce.debug_watch_stop` and `ce.debug_watch_stop_all` clear both effective and raw breakpoint state

## Release assets

- `cheat-engine-mcp-0.2.9-windows-x64.zip`
- `SHA256SUMS.txt`

ZIP contents:

- `ce_mcp_plugin.dll`
- `ce_mcp_plugin_core.dll`
- `README.md`
- `INSTALL.txt`

## Install summary

- extract the ZIP to a stable folder
- register `ce_mcp_plugin.dll` in `Edit -> Settings -> Plugins`
- leave the loader enabled
- do not load `ce_mcp_plugin_core.dll` directly
- install the backend from Codex with:

```powershell
codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
```

## Notes

- target platform: Windows x64
- intended Cheat Engine build: x64
- default bridge port: `127.0.0.1:5556`
- loader changes still require a Cheat Engine restart
- core-only development changes can still hot-reload
- the live validation details for this release are recorded in `docs/DEBUG_BREAKPOINT_VISIBILITY_FIX_2026-03-08.md`
