# Prebuilt Windows Install

This guide is for users who want the prebuilt Cheat Engine plugin DLLs instead of building from source.

## What To Download

For `v0.2.7`, download:

- `releases/v0.2.7/ce_mcp_plugin.dll`
- `releases/v0.2.7/ce_mcp_plugin_core.dll`
- `releases/v0.2.7/cheat-engine-mcp-0.2.7-windows-x64.zip`

Recommended:

- download the ZIP unless you have a reason to fetch the DLL files individually

Inside the ZIP:

- `ce_mcp_plugin.dll`
- `ce_mcp_plugin_core.dll`
- `README.md`
- `INSTALL.txt`

## Requirements

- Windows 10 or Windows 11 x64
- Cheat Engine 7.x x64
- One backend option:
  - Node.js 20+ for the packaged `npx` Codex install path
  - Python 3.11+ for the direct `ce_mcp_server` backend path
- Codex or another MCP client

## Important Warnings

- Load `ce_mcp_plugin.dll` in Cheat Engine. Do not load `ce_mcp_plugin_core.dll` directly.
- Keep `ce_mcp_plugin.dll` and `ce_mcp_plugin_core.dll` in the same extracted folder.
- Use x64 Cheat Engine with the x64 plugin build.
- The DLLs are unsigned. Windows or antivirus tooling may warn before first load.
- The bridge defaults to `127.0.0.1:5556`.

## Install Steps

1. Download `releases/v0.2.7/cheat-engine-mcp-0.2.7-windows-x64.zip`.
2. Extract the ZIP to a stable folder.
3. Open Cheat Engine.
4. Go to `Edit -> Settings -> Plugins`.
5. Add or load `ce_mcp_plugin.dll` from the extracted folder.
6. Leave the loader enabled.
7. Start the MCP backend from Codex:

```powershell
codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
```

If the packaged `npx` launcher is unstable on the machine, use the direct Python backend instead:

```toml
[mcp_servers.cheat-engine]
command = 'C:\Path\To\Python\python.exe'
args = ["-m", "ce_mcp_server"]
startup_timeout_sec = 120
```

## Updating

- If only the core DLL changed during development, the loader can hot-reload the core.
- If the loader DLL changed, restart Cheat Engine after replacing the files.
- When installing a new tagged bundle, replace both DLLs together.

## Troubleshooting

If the plugin fails to load or Codex cannot connect:

- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
