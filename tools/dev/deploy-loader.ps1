param(
    [Parameter(Mandatory = $true)]
    [string]$BuiltLoaderPath,
    [Parameter(Mandatory = $true)]
    [string]$PluginRoot
)

$builtLoaderPath = [System.IO.Path]::GetFullPath($BuiltLoaderPath)
$pluginRoot = [System.IO.Path]::GetFullPath($PluginRoot)
$liveLoaderPath = Join-Path $pluginRoot 'ce_mcp_plugin.dll'
$stagedDir = Join-Path $pluginRoot 'staged'
$stagedLoaderPath = Join-Path $stagedDir 'ce_mcp_plugin.dll'
$runtimeDir = Join-Path $pluginRoot 'runtime'
$pendingManifestPath = Join-Path $runtimeDir 'next_loader.txt'

if (-not (Test-Path $builtLoaderPath)) {
    throw "Built loader DLL not found at '$builtLoaderPath'."
}

New-Item -ItemType Directory -Force -Path $pluginRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stagedDir | Out-Null
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

Copy-Item -LiteralPath $builtLoaderPath -Destination $stagedLoaderPath -Force

try {
    Copy-Item -LiteralPath $builtLoaderPath -Destination $liveLoaderPath -Force -ErrorAction Stop
    if (Test-Path $pendingManifestPath) {
        Remove-Item -LiteralPath $pendingManifestPath -Force
    }

    Write-Output ("live {0}" -f $liveLoaderPath)
}
catch {
    Set-Content -LiteralPath $pendingManifestPath -Value $stagedLoaderPath -Encoding utf8
    Write-Output ("staged {0}" -f $stagedLoaderPath)
}
