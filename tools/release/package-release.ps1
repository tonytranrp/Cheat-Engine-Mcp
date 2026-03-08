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

Files:
- ce_mcp_plugin.dll: load this in Cheat Engine
- ce_mcp_plugin_core.dll: hot-swappable core loaded by the loader

Codex setup:
- codex mcp add cheat-engine npx -y github:tonytranrp/Cheat-Engine-Mcp
- or codex mcp add cheat-engine -- ce-mcp-server

Cheat Engine setup:
- Register ce_mcp_plugin.dll in Edit -> Settings -> Plugins
- Leave the loader enabled

Bridge default:
- 127.0.0.1:5556
"@ | Set-Content (Join-Path $stageDir 'INSTALL.txt')

Compress-Archive -Path $stageDir -DestinationPath $zipPath -Force
Write-Output "staged $stageDir"
Write-Output "zip $zipPath"
