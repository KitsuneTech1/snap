<#
ocr.ps1 - read the text in an image with Windows' built-in OCR (no install, no network).

  powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ".\ocr.ps1" -Path <png>

Writes <png>.ocr.json next to the image: every line and word with its box in that image's
pixels, plus a "secrets" count. Prints one compact JSON summary with the text, where anything
that looks like a key, token or private key is masked, so an agent never echoes a secret.
Used by snap.ps1 -Ocr and by snapedit.py (box_text, redact_text, redact_secrets).
#>
param([Parameter(Mandatory = $true)][string]$Path, [int]$MaxChars = 2500)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Path = (Resolve-Path -LiteralPath $Path).Path
# OCR can return control characters (a BEL showed up on a real snap); PowerShell 5.1 JSON does not escape them.
function Clean([string]$s) { $s -replace '[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '' }

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [type]$t) {
  $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op))
  [void]$task.Wait(-1)
  $task.Result
}

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$stream.Dispose()

# Patterns that look like credentials. Matching words are counted and masked, never printed.
$secretRx = '(sk-[A-Za-z0-9_\-]{16,}|sk_(live|test)_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abpr]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|eyJ[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{10,}|PRIVATE KEY)'

$lines = @(); $secrets = 0; $text = New-Object System.Text.StringBuilder
foreach ($line in $result.Lines) {
  $words = @()
  foreach ($w in $line.Words) {
    $r = $w.BoundingRect
    $wt = Clean $w.Text
    $isSecret = $wt -match $secretRx
    if ($isSecret) { $secrets++ }
    $words += [ordered]@{ t = $wt; x = [int]$r.X; y = [int]$r.Y; w = [int]$r.Width; h = [int]$r.Height; secret = $isSecret }
  }
  $xs = $words | ForEach-Object { $_.x }; $ys = $words | ForEach-Object { $_.y }
  $x2 = $words | ForEach-Object { $_.x + $_.w }; $y2 = $words | ForEach-Object { $_.y + $_.h }
  $lines += [ordered]@{
    text = (Clean $line.Text)
    x = [int]($xs | Measure-Object -Minimum).Minimum; y = [int]($ys | Measure-Object -Minimum).Minimum
    w = [int](($x2 | Measure-Object -Maximum).Maximum - ($xs | Measure-Object -Minimum).Minimum)
    h = [int](($y2 | Measure-Object -Maximum).Maximum - ($ys | Measure-Object -Minimum).Minimum)
    words = $words
  }
  $safe = ($line.Words | ForEach-Object { $c = Clean $_.Text; if ($c -match $secretRx) { '[SECRET HIDDEN]' } else { $c } }) -join ' '
  [void]$text.AppendLine($safe)
}

$side = "$Path.ocr.json"
[ordered]@{ image = $Path; width = $bitmap.PixelWidth; height = $bitmap.PixelHeight; secrets = $secrets; lines = $lines } |
  ConvertTo-Json -Depth 6 -Compress | Set-Content -LiteralPath $side -Encoding UTF8
$t = $text.ToString()
if ($t.Length -gt $MaxChars) { $t = $t.Substring(0, $MaxChars) + ' ...' }
[ordered]@{ ocr = $side; lines = $lines.Count; secrets = $secrets; text = $t } | ConvertTo-Json -Compress
