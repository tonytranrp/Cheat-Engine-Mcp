# Cheat Engine MCP v0.2.8

## Highlights

- rewrote the native bridge transport so tool calls execute on a bounded worker pool instead of the socket thread
- added internal timeout enforcement for `ce.query_memory_map` and native AOB scans
- rewrote `ce.dissect_module` into a chunked executable-region workflow to avoid monolithic freeze-prone passes
- hardened timeout recovery by closing poisoned CE sessions instead of letting later calls queue behind them
- added a bridge-only backend mode for detached validation workflows and guarded against tearing down stdio-backed live backends

## Release assets

- `cheat-engine-mcp-0.2.8-windows-x64.zip`
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
- the live validation and benchmark details for this release are recorded in `docs/TIMEOUT_AND_PARALLEL_EXECUTION_REWRITE_2026-03-08.md`
