# Build snap.exe from Snap.cs using the .NET Framework csc.exe
param([string]$OutputPath)

$ErrorActionPreference = 'Stop'

$csc = @(
    'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe',
    'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $csc) {
    Write-Error 'csc.exe not found under C:\Windows\Microsoft.NET\Framework or Framework64\v4.0.30319'
    exit 1
}

$snapCs = Join-Path $PSScriptRoot 'snapsrc\Snap.cs'
$output = if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    Join-Path $PSScriptRoot 'snap.exe'
} else {
    try { [System.IO.Path]::GetFullPath($OutputPath) } catch { Write-Error 'OutputPath is invalid'; exit 1 }
}

if (-not (Test-Path $snapCs)) {
    Write-Error "Snap.cs not found at $snapCs"
    exit 1
}

$outputParent = Split-Path -Parent $output
if ($outputParent -and -not (Test-Path $outputParent)) {
    New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
}

Write-Host "Building $output from $snapCs..."
& $csc -nologo -optimize+ -target:exe -out:$output -r:System.Windows.Forms.dll -r:System.Drawing.dll $snapCs

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete: $output"
} else {
    Write-Error "Build failed with exit code $LASTEXITCODE"
    exit 1
}
