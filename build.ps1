# Build snap.exe from Snap.cs using the .NET Framework csc.exe
$ErrorActionPreference = 'Stop'

$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) {
    Write-Error "csc.exe not found at $csc"
    exit 1
}

$snapCs = Join-Path $PSScriptRoot 'snapsrc\Snap.cs'
$output = Join-Path $PSScriptRoot 'snap.exe'

if (-not (Test-Path $snapCs)) {
    Write-Error "Snap.cs not found at $snapCs"
    exit 1
}

Write-Host "Building $output from $snapCs..."
& $csc -nologo -optimize+ -target:exe -out:$output -r:System.Windows.Forms.dll -r:System.Drawing.dll $snapCs

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete: $output"
} else {
    Write-Error "Build failed with exit code $LASTEXITCODE"
    exit 1
}
