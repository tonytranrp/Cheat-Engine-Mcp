param(
    [Parameter(Mandatory = $true)]
    [string]$Tool,
    [string[]]$Field = @(),
    [int]$Port = 5556,
    [string]$BuildDir,
    [string]$PluginRoot,
    [string]$CheatEnginePath = "C:\Program Files\Cheat Engine\cheatengine-x86_64-SSE4-AVX2.exe",
    [int]$StartupTimeoutSeconds = 20,
    [switch]$SkipBuild,
    [switch]$ForceRestart
)

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\\.."))
if ([string]::IsNullOrWhiteSpace($BuildDir)) {
    $BuildDir = Join-Path $repoRoot "build"
}

if ([string]::IsNullOrWhiteSpace($PluginRoot)) {
    $PluginRoot = Join-Path $BuildDir "loader"
}

$buildDir = [System.IO.Path]::GetFullPath($BuildDir)
$pluginRoot = [System.IO.Path]::GetFullPath($PluginRoot)
$cheatEnginePath = [System.IO.Path]::GetFullPath($CheatEnginePath)
$pluginControl = Join-Path $scriptDir "plugin-control.ps1"
$updateCore = Join-Path $scriptDir "update-core.ps1"
$restartCheatEngine = Join-Path $scriptDir "restart-cheat-engine.ps1"
$runMcpCall = Join-Path $scriptDir "run-mcp-call.py"
$loaderArtifact = Join-Path $buildDir "artifacts\\loader\\ce_mcp_plugin.dll"
$processName = [System.IO.Path]::GetFileNameWithoutExtension($cheatEnginePath)
$loaderInputs = @(
    "CMakeLists.txt",
    "native\\vendor\\cheat_engine\\cepluginsdk.h",
    "native\\include\\ce_mcp\\config.hpp",
    "native\\include\\ce_mcp\\core_api.h",
    "native\\include\\ce_mcp\\plugin_loader.hpp",
    "native\\src\\loader\\ce_mcp_plugin.cpp",
    "native\\src\\loader\\plugin_loader.cpp",
    "native\\CMakeLists.txt"
)

$normalizedFields = @()
foreach ($item in $Field) {
    foreach ($part in ([regex]::Split($item, ',(?=[^,=]+=)'))) {
        if (-not [string]::IsNullOrWhiteSpace($part)) {
            $normalizedFields += $part
        }
    }
}
$Field = $normalizedFields

function Test-AnyNewer {
    param(
        [string[]]$RelativePaths,
        [string]$OutputPath
    )

    if (-not (Test-Path $OutputPath)) {
        return $true
    }

    $outputTime = (Get-Item $OutputPath).LastWriteTimeUtc
    foreach ($relativePath in $RelativePaths) {
        $candidate = Join-Path $repoRoot $relativePath
        if ((Test-Path $candidate) -and ((Get-Item $candidate).LastWriteTimeUtc -gt $outputTime)) {
            return $true
        }
    }

    return $false
}

function Test-LoaderReachable {
    try {
        $status = & $pluginControl -PluginRoot $pluginRoot -Command status 2>$null
        return (-not [string]::IsNullOrWhiteSpace($status))
    }
    catch {
        return $false
    }
}

function Invoke-CmakeBuild {
    param(
        [string[]]$Targets
    )

    $nmake = Get-Command nmake -ErrorAction SilentlyContinue
    if ($null -ne $nmake) {
        & cmake --build $buildDir --target $Targets
        if ($LASTEXITCODE -ne 0) {
            throw "Build failed."
        }

        return
    }

    $vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        throw "vswhere.exe not found. Cannot bootstrap the Visual Studio build environment."
    }

    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($installPath)) {
        throw "Unable to locate a Visual Studio installation with C++ tools."
    }

    $vsDevCmd = Join-Path $installPath "Common7\\Tools\\VsDevCmd.bat"
    if (-not (Test-Path $vsDevCmd)) {
        throw "VsDevCmd.bat not found at '$vsDevCmd'."
    }

    $quotedVsDevCmd = '"' + $vsDevCmd + '"'
    $quotedBuildDir = '"' + $buildDir + '"'
    $targetText = $Targets -join ' '
    cmd.exe /c "$quotedVsDevCmd -arch=x64 && cmake --build $quotedBuildDir --target $targetText"
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed."
    }
}

if (-not (Test-Path $cheatEnginePath)) {
    throw "Cheat Engine executable not found at '$cheatEnginePath'."
}

if (-not (Test-Path $runMcpCall)) {
    throw "MCP caller script not found at '$runMcpCall'."
}

$needsLoaderRestart = $ForceRestart.IsPresent
if (-not $SkipBuild) {
    $needsLoaderRestart = $needsLoaderRestart -or (Test-AnyNewer -RelativePaths $loaderInputs -OutputPath $loaderArtifact)
}

if (-not $SkipBuild) {
    if ($needsLoaderRestart) {
        Write-Output "build loader deploy + core"
        Invoke-CmakeBuild -Targets @("ce_mcp_loader_deploy", "ce_mcp_core")
    }
    else {
        Write-Output "build core"
        & $updateCore -BuildDir $buildDir -PluginRoot $pluginRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Core build or hot reload failed."
        }
    }
}

if ($needsLoaderRestart) {
    Write-Output "restart cheat engine"
    & $restartCheatEngine -CheatEnginePath $cheatEnginePath -PluginRoot $pluginRoot -StartupTimeoutSeconds $StartupTimeoutSeconds -ReloadCore
    if ($LASTEXITCODE -ne 0) {
        throw "Cheat Engine restart failed."
    }
}
elseif (-not (Test-LoaderReachable)) {
    Write-Output "start cheat engine"
    & $restartCheatEngine -CheatEnginePath $cheatEnginePath -PluginRoot $pluginRoot -StartupTimeoutSeconds $StartupTimeoutSeconds
    if ($LASTEXITCODE -ne 0) {
        throw "Cheat Engine start failed."
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    throw "python was not found in PATH."
}

$arguments = @($runMcpCall, "--port", [string]$Port, "--tool", $Tool)
foreach ($item in $Field) {
    $arguments += @("--field", $item)
}

Write-Output "call $Tool"
& $python.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw "MCP call failed."
}
