param(
    [string]$CheatEnginePath = "C:\Program Files\Cheat Engine\cheatengine-x86_64-SSE4-AVX2.exe",
    [string]$PluginRoot,
    [int]$StartupTimeoutSeconds = 20,
    [switch]$ReloadCore
)

$scriptDir = Split-Path -Parent $PSCommandPath
if ([string]::IsNullOrWhiteSpace($PluginRoot)) {
    $PluginRoot = Join-Path $scriptDir "..\\..\\build\\loader"
}

$pluginRoot = [System.IO.Path]::GetFullPath($PluginRoot)
$cheatEnginePath = [System.IO.Path]::GetFullPath($CheatEnginePath)
$pluginControl = Join-Path $scriptDir "plugin-control.ps1"
$updateCore = Join-Path $scriptDir "update-core.ps1"
$controlInfoPath = Join-Path $pluginRoot "runtime\\control.txt"
$pendingLoaderManifestPath = Join-Path $pluginRoot "runtime\\next_loader.txt"
$liveLoaderPath = Join-Path $pluginRoot "ce_mcp_plugin.dll"

if (-not (Test-Path $cheatEnginePath)) {
    throw "Cheat Engine executable not found at '$cheatEnginePath'."
}

$processName = [System.IO.Path]::GetFileNameWithoutExtension($cheatEnginePath)
$existingProcesses = @(Get-Process -Name $processName -ErrorAction SilentlyContinue)
if ($existingProcesses.Count -gt 0) {
    $existingProcesses | Stop-Process -Force
    $existingProcesses | Wait-Process -Timeout $StartupTimeoutSeconds -ErrorAction Stop
}

if (Test-Path $controlInfoPath) {
    Remove-Item -LiteralPath $controlInfoPath -Force
}

if (Test-Path $pendingLoaderManifestPath) {
    $stagedLoaderPath = (Get-Content -LiteralPath $pendingLoaderManifestPath -TotalCount 1).Trim()
    if ([string]::IsNullOrWhiteSpace($stagedLoaderPath)) {
        throw "Pending loader manifest '$pendingLoaderManifestPath' is empty."
    }

    $stagedLoaderPath = [System.IO.Path]::GetFullPath($stagedLoaderPath)
    if (-not (Test-Path $stagedLoaderPath)) {
        throw "Pending staged loader DLL not found at '$stagedLoaderPath'."
    }

    Copy-Item -LiteralPath $stagedLoaderPath -Destination $liveLoaderPath -Force
    Remove-Item -LiteralPath $pendingLoaderManifestPath -Force
    Write-Output ("loader deployed {0}" -f $liveLoaderPath)
}

Start-Process -FilePath $cheatEnginePath | Out-Null

$deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
$status = $null
do {
    Start-Sleep -Milliseconds 500

    if (-not (Test-Path $controlInfoPath)) {
        continue
    }

    try {
        $status = & $pluginControl -PluginRoot $pluginRoot -Command status 2>$null
    }
    catch {
        $status = $null
    }
} while (([string]::IsNullOrWhiteSpace($status)) -and (Get-Date) -lt $deadline)

if ([string]::IsNullOrWhiteSpace($status)) {
    throw "Cheat Engine started, but the CE MCP loader control pipe did not become ready within $StartupTimeoutSeconds seconds."
}

Write-Output $status

if ($ReloadCore) {
    & $updateCore -PluginRoot $pluginRoot -SkipBuild
    if ($LASTEXITCODE -ne 0) {
        throw "Core reload failed."
    }
}
