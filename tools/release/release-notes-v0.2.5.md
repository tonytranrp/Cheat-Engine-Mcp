# Cheat Engine MCP v0.2.5

## Highlights

- `208` MCP tools registered in the Python backend
- new `ce.structure_read` workflow for dumping live structure instances as named fields
- expanded Lua environment helpers for package path management, preloaded modules, and temporary globals
- lower steady-state latency through a cached CE-side dispatcher for runtime and Lua calls
- live integration coverage validated against `Tic-tak-toe.exe`

## Release assets

- `cheat-engine-mcp-0.2.5-windows-x64.zip`
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
