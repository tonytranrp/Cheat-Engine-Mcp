# Cheat Engine MCP v0.2.7

## Highlights

- vendored `libhat` and rewrote the native signature-scan path around it
- `ce.aob_scan`, `ce.aob_scan_unique`, and `ce.aob_scan_module_unique` now share one libhat-backed engine
- added scan controls for `section_name`, `scan_alignment`, `scan_hint`, and per-call `timeout_seconds`
- exact bounded `ce.scan_string(...)` searches now stay on the fast native path
- live validation completed against `Minecraft.Windows.exe`

## Release assets

- `cheat-engine-mcp-0.2.7-windows-x64.zip`
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
