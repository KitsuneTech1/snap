<#
snap.ps1 - thin wrapper over snap.exe that adds -Ocr. The heavy lifting is the native exe
(snap.exe next to this script, source in snapsrc\Snap.cs, ~150 ms capture). Prefer calling
snap.exe directly when you don't need text; use this only for -Ocr, or if the exe is missing.

  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\snap.ps1" [same flags as snap.exe] [-Ocr]

Flags pass straight through to snap.exe: -App <name>, -List, -Mode monitor|window|all|auto,
-Region "x,y,w,h", -MaxWidth n. -Ocr additionally reads the text (Windows OCR, keys masked) and
merges { ocr, secrets, text } into the JSON. Read-only, hidden, no window. Snaps live in
%LOCALAPPDATA%\Temp\snaps and never leave the machine.
#>
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$exe = Join-Path $PSScriptRoot 'snap.exe'
$ocr = $false
$pass = @()
foreach ($a in $args) { if ("$a".ToLower() -eq '-ocr') { $ocr = $true } else { $pass += $a } }

if (-not (Test-Path $exe)) {
  Write-Output ('{"error":"snap.exe missing; build it: build.ps1"}')
  exit 1
}
$json = & $exe @pass
$nativeExit = $LASTEXITCODE
$obj = $null
try { $obj = $json | ConvertFrom-Json } catch { }
if (-not $ocr -or -not $obj -or -not $obj.path) { Write-Output $json; exit $nativeExit }

$o = & (Join-Path $PSScriptRoot 'ocr.ps1') -Path $obj.path -MaxChars 2000 | ConvertFrom-Json
$obj | Add-Member -NotePropertyName ocr -NotePropertyValue $o.ocr -Force
$obj | Add-Member -NotePropertyName secrets -NotePropertyValue $o.secrets -Force
$obj | Add-Member -NotePropertyName text -NotePropertyValue $o.text -Force
$obj | ConvertTo-Json -Compress
