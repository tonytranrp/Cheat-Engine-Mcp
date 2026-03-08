param(
    [string]$BuildDir,
    [string]$PluginRoot,
    [switch]$SkipBuild
)

$scriptDir = Split-Path -Parent $PSCommandPath
if ([string]::IsNullOrWhiteSpace($BuildDir)) {
    $BuildDir = Join-Path $scriptDir "..\\..\\build"
}

if ([string]::IsNullOrWhiteSpace($PluginRoot)) {
    $PluginRoot = Join-Path $scriptDir "..\\..\\build\\loader"
}

$buildDir = [System.IO.Path]::GetFullPath($BuildDir)
$pluginRoot = [System.IO.Path]::GetFullPath($PluginRoot)
$coreBuildPath = Join-Path $buildDir "core\\ce_mcp_plugin_core.dll"
$runtimeDir = Join-Path $pluginRoot "runtime"
$versionsDir = Join-Path $runtimeDir "versions"
$currentManifestPath = Join-Path $runtimeDir "current.txt"

if (-not $SkipBuild) {
    $nmake = Get-Command nmake -ErrorAction SilentlyContinue
    if ($null -ne $nmake) {
        & cmake --build $buildDir --target ce_mcp_core
        if ($LASTEXITCODE -ne 0) {
            throw "Core build failed."
        }
    }
    else {
        $vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
        if (-not (Test-Path $vswhere)) {
            throw "vswhere.exe not found. Cannot bootstrap the Visual Studio build environment."
        }

        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($installPath)) {
            throw "Unable to locate a Visual Studio installation with C++ tools."
        }

        $vcvars64 = Join-Path $installPath "VC\Auxiliary\Build\vcvars64.bat"
        if (-not (Test-Path $vcvars64)) {
            throw "vcvars64.bat not found at '$vcvars64'."
        }

        $quotedVcvars = '"' + $vcvars64 + '"'
        $quotedBuildDir = '"' + $buildDir + '"'
        cmd.exe /c "$quotedVcvars && cmake --build $quotedBuildDir --target ce_mcp_core"
        if ($LASTEXITCODE -ne 0) {
            throw "Core build failed."
        }
    }
}

if (-not (Test-Path $coreBuildPath)) {
    throw "Built core DLL not found at '$coreBuildPath'."
}

New-Item -ItemType Directory -Force -Path $versionsDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stagedCorePath = Join-Path $versionsDir ("ce_mcp_plugin_core_{0}.dll" -f $timestamp)
Copy-Item -LiteralPath $coreBuildPath -Destination $stagedCorePath -Force
Set-Content -LiteralPath $currentManifestPath -Value $stagedCorePath -Encoding utf8

try {
    $response = & (Join-Path $PSScriptRoot "plugin-control.ps1") -PluginRoot $pluginRoot -Command ("reload {0}" -f $stagedCorePath)
    if ($LASTEXITCODE -ne 0) {
        throw "Hot reload command failed."
    }

    Write-Output $response
}
catch {
    Write-Warning "Staged '$stagedCorePath', but the live loader control pipe was not reachable."
    Write-Warning "Load the new loader DLL once in Cheat Engine, then rerun this script."
    Write-Output ("staged {0}" -f $stagedCorePath)
}
