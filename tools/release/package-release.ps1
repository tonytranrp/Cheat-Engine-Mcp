param(
    [string]$BuildDir,
    [string]$OutputDir,
    [string]$Version
)

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $PSCommandPath) '..\..'))
if ([string]::IsNullOrWhiteSpace($BuildDir)) {
    $BuildDir = Join-Path $repoRoot 'build'
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $repoRoot 'dist'
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    $packageJson = Get-Content (Join-Path $repoRoot 'package.json') -Raw | ConvertFrom-Json
    $Version = [string]$packageJson.version
}

$buildDir = [System.IO.Path]::GetFullPath($BuildDir)
$outputDir = [System.IO.Path]::GetFullPath($OutputDir)
$stageDir = Join-Path $outputDir ("cheat-engine-mcp-$Version-windows-x64")
$zipPath = Join-Path $outputDir ("cheat-engine-mcp-$Version-windows-x64.zip")

$loaderDll = Join-Path $buildDir 'loader\ce_mcp_plugin.dll'
$coreDll = Join-Path $buildDir 'core\ce_mcp_plugin_core.dll'
if (-not (Test-Path $loaderDll)) { throw "Loader DLL not found at '$loaderDll'." }
if (-not (Test-Path $coreDll)) { throw "Core DLL not found at '$coreDll'." }

Remove-Item $stageDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stageDir | Out-Null

Copy-Item $loaderDll (Join-Path $stageDir 'ce_mcp_plugin.dll')
Copy-Item $coreDll (Join-Path $stageDir 'ce_mcp_plugin_core.dll')
Copy-Item (Join-Path $repoRoot 'README.md') (Join-Path $stageDir 'README.md')

@"
Cheat Engine MCP $Version

Package contents:
- ce_mcp_plugin.dll: stable loader DLL to register in Cheat Engine
- ce_mcp_plugin_core.dll: core runtime loaded by the loader

Requirements:
- Windows 10/11 x64
- Cheat Engine 7.x x64
- Node.js 20+ for the packaged npx backend path
- or Python 3.11+ for the direct ce_mcp_server backend path

Important:
- Load ce_mcp_plugin.dll in Cheat Engine
- Do NOT load ce_mcp_plugin_core.dll directly
- Keep both DLL files in the same extracted folder
- Use the x64 Cheat Engine build with this x64 plugin build
- Default bridge: 127.0.0.1:5556

Codex setup:
- codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
- or configure a direct Python backend with -m ce_mcp_server

Cheat Engine setup:
- Open Edit -> Settings -> Plugins
- Register ce_mcp_plugin.dll from this extracted folder
- Leave the loader enabled

More docs:
- README.md
- docs/INSTALL_PREBUILT_WINDOWS.md in the repo
- docs/TROUBLESHOOTING.md in the repo
"@ | Set-Content (Join-Path $stageDir 'INSTALL.txt')

Compress-Archive -Path $stageDir -DestinationPath $zipPath -Force
Write-Output "staged $stageDir"
Write-Output "zip $zipPath"
