# Cheat Engine MCP v0.2.0

## Highlights

- one-line Codex registration through an `npx` launcher
- hot-reloadable Cheat Engine loader/core plugin architecture
- packaged MCP backend with 151 registered tools
- direct Cheat Engine Lua and Auto Assemble execution
- raw `ExportedFunctions` field introspection over MCP
- process, module, symbol, memory, pointer-chain, scan, table, and record tools

## Codex setup

```powershell
codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
```

## Release assets

- `ce_mcp_plugin.dll`
- `ce_mcp_plugin_core.dll`
- `cheat-engine-mcp-0.2.0-windows-x64.zip`

## Cheat Engine setup

- register `ce_mcp_plugin.dll` in `Edit -> Settings -> Plugins`
- leave the loader enabled
- start the MCP backend from Codex

## Notes

- default bridge port: `127.0.0.1:5556`
- loader DLL stays stable inside Cheat Engine
- core DLL can be hot-reloaded during development
