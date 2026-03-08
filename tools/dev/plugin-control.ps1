param(
    [string]$PluginRoot,
    [Parameter(Mandatory = $true)]
    [string]$Command
)

if ([string]::IsNullOrWhiteSpace($PluginRoot)) {
    $scriptDir = Split-Path -Parent $PSCommandPath
    $PluginRoot = Join-Path $scriptDir "..\\..\\build\\loader"
}

$controlInfoPath = Join-Path $PluginRoot "runtime\\control.txt"
if (-not (Test-Path $controlInfoPath)) {
    throw "Control file not found at '$controlInfoPath'. Load the new loader DLL in Cheat Engine first."
}

$controlInfo = @{}
foreach ($line in Get-Content $controlInfoPath) {
    if ($line -match '^\s*([^=]+)=(.*)$') {
        $controlInfo[$matches[1]] = $matches[2]
    }
}

$pipeName = $controlInfo["pipe_name"]
if ([string]::IsNullOrWhiteSpace($pipeName)) {
    throw "pipe_name is missing from '$controlInfoPath'."
}

$encoding = [System.Text.UTF8Encoding]::new($false)
$client = [System.IO.Pipes.NamedPipeClientStream]::new(
    ".",
    $pipeName,
    [System.IO.Pipes.PipeDirection]::InOut
)

try {
    $client.Connect(2000)

    $writer = [System.IO.StreamWriter]::new($client, $encoding, 1024, $true)
    $writer.NewLine = "`n"
    $writer.AutoFlush = $true

    $reader = [System.IO.StreamReader]::new($client, $encoding, $true, 1024, $true)

    $writer.WriteLine($Command)
    $response = $reader.ReadToEnd().Trim()
    if (-not [string]::IsNullOrWhiteSpace($response)) {
        Write-Output $response
    }
}
finally {
    if ($null -ne $client) {
        $client.Dispose()
    }
}
