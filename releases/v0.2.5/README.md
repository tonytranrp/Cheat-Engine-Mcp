# Cheat Engine MCP v0.2.5 Assets

This folder contains the prebuilt Windows x64 release files for `v0.2.5`.

## Downloads

- `ce_mcp_plugin.dll`
- `ce_mcp_plugin_core.dll`
- `cheat-engine-mcp-0.2.5-windows-x64.zip`
- `SHA256SUMS.txt`

Recommended:

- download the ZIP if you want the normal packaged install
- use the raw DLL files only if you know you want the files individually

## Install Summary

1. Keep `ce_mcp_plugin.dll` and `ce_mcp_plugin_core.dll` together in one folder.
2. In Cheat Engine, load `ce_mcp_plugin.dll` from `Edit -> Settings -> Plugins`.
3. Do not load `ce_mcp_plugin_core.dll` directly.
4. Start the MCP backend from Codex with either:

```powershell
codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
```

or a direct Python backend using `-m ce_mcp_server`.

## Requirements

- Windows x64
- Cheat Engine x64
- Node.js 20+ for the packaged `npx` backend path, or Python 3.11+ for the direct backend path

## Full Docs

- [README.md](../../README.md)
- [docs/INSTALL_PREBUILT_WINDOWS.md](../../docs/INSTALL_PREBUILT_WINDOWS.md)
- [docs/TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md)
