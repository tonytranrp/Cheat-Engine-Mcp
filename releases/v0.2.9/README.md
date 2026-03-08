# Cheat Engine MCP v0.2.9 Assets

This folder contains the prebuilt Windows x64 release files for `v0.2.9`.

Files:

- `ce_mcp_plugin.dll`
- `ce_mcp_plugin_core.dll`
- `cheat-engine-mcp-0.2.9-windows-x64.zip`
- `SHA256SUMS.txt`

Use `ce_mcp_plugin.dll` as the Cheat Engine plugin entry.
Do not load `ce_mcp_plugin_core.dll` directly.

This release also updates the debug/watch payloads so `ce.debug_list_breakpoints` and `ce.debug_status` report the effective active watch set, with raw CE breakpoint visibility preserved separately through `raw_count` and `raw_breakpoints`.
