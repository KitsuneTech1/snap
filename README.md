# FocusSnap

Fast, focus-safe screen and window capture for Windows with optional OCR text extraction. Captures in under 200ms without stealing focus, with metadata and optional Tesseract OCR integration.

FocusSnap is designed for automation, accessibility tools, and agents that need to take screenshots without interrupting the user's work or focus context.

## Quick Start

Build the native executable:

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

Then capture the active screen:

```bash
snap.exe -List                    # List all visible windows
snap.exe                          # Capture active screen
snap.exe -App firefox             # Capture by window name
snap.exe -Region "0,0,800,600"    # Capture a specific region
snap.exe -Mode window             # Capture active window only
```

## Installation

1. Clone this repository.
2. Run `build.ps1` to compile the C# source to snap.exe using the .NET Framework compiler (csc.exe).

### Build Requirements

- Windows 7 or later
- .NET Framework 4.0+ (for csc.exe, included with Windows)
- For OCR: Tesseract 4.0+ on PATH (optional; install from https://github.com/UB-Mannheim/tesseract)

### Runtime Requirements

- Windows 7 or later
- .NET Framework 4.0+ (already installed on most Windows systems)
- Optional: tesseract.exe for OCR

## Usage

### snap.exe

The native executable for fast capture without PowerShell overhead.

```bash
snap.exe [options]
```

Options:
- `-List`: Print JSON list of all visible windows with title, process name, coordinates and size. Exits with code 0.
- `-App <name>`: Capture the window whose title or process name matches the substring (case-insensitive).
- `-Mode monitor|window|all|auto` (default: auto): What to capture.
  - `monitor`: Capture the primary monitor.
  - `window`: Capture the active foreground window.
  - `all`: Capture all monitors.
  - `auto`: If a foreground window is fullscreen, capture it; otherwise capture the monitor.
- `-Region "x,y,w,h"`: Capture a specific rectangular region (in pixels).
- `-MaxWidth n`: If the output image exceeds this width, scale it down. Default: no scaling. Does not crop, only scales proportionally.

Output: JSON with keys:
- `path`: Full path to the PNG file (in %LOCALAPPDATA%\Temp\claude-snaps).
- `width`, `height`: Image dimensions.
- `monitor`: Display string (e.g., "2560x1440@0,0").
- `error`: If something went wrong, the error message instead of a path.

Exit codes:
- 0: Success.
- 1: No window found matching the filter, or region out of bounds.
- 2: I/O error writing the image.

### snap.ps1

A PowerShell wrapper that adds OCR support via Tesseract. The executable snap.exe is preferred when you don't need text.

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File snap.ps1 [options] [-Ocr]
```

Options are the same as snap.exe. Add `-Ocr` to extract text with Tesseract. When `-Ocr` is used, the JSON output includes:
- `ocr`: The extracted text (keys and tokens are masked).
- `secrets`: Boolean, true if potential secrets were detected and masked.
- `text`: Plain text without masking, for direct use if needed.

### snapedit.py

Python utility for annotating, cropping, and composing screenshots into GIFs.

```bash
python snapedit.py info IMG                         # Print dimensions
python snapedit.py grid IMG -o OUT [--step 100]     # Add a pixel grid
python snapedit.py edit IMG -o OUT --ops JSON       # Annotate or redact
python snapedit.py gif IMG [IMG ...] -o OUT.gif     # Compose multiple images into an animated GIF
python snapedit.py ocr IMG                          # Extract text
python snapedit.py find IMG "phrase"                # Find text locations
```

## Security and Privacy

- **No focus stealing**: snap.exe never clicks, focuses, minimizes, maximizes, or restores any window. It only reads pixel data and metadata.
- **Local only**: All snapshots are stored in %LOCALAPPDATA%\Temp\claude-snaps and never leave your machine.
- **No dependencies on external services**: No cloud calls, no tracking, no telemetry.
- **Headless**: Runs without a visible window or console.
- **Key masking** (when using OCR): Keys, tokens, and passwords are detected and masked in the OCR output.

## Examples

Capture the active window and save it:

```bash
snap.exe -Mode window -MaxWidth 1200
```

List all visible windows (e.g., to find the right name for -App):

```bash
snap.exe -List
```

Capture a specific region for 5 seconds:

```bash
snap.exe -Region "100,100,800,600"
```

Capture Firefox with OCR (PowerShell):

```bash
powershell -ExecutionPolicy Bypass -File snap.ps1 -App firefox -Ocr
```

Annotate a screenshot:

```bash
python snapedit.py edit screenshot.png -o annotated.png --ops '[
  {"box": [100, 100, 200, 50], "label": "click here"},
  {"arrow": [150, 150, 250, 250], "color": "#f59e0b"}
]'
```

Create an animated GIF from multiple screenshots:

```bash
python snapedit.py gif screen1.png screen2.png screen3.png -o demo.gif --ms 1500
```

## Performance

- Capture: 100-200ms (native snap.exe), 400-600ms with PowerShell startup overhead (snap.ps1).
- OCR: 300-800ms depending on image size and Tesseract availability.
- Editing/scaling: 50-200ms per image.

## Troubleshooting

**snap.exe not found**: Run `build.ps1` to compile Snap.cs.

**csc.exe not found**: Ensure .NET Framework 4.0+ is installed. On modern Windows, this is included by default. If using a minimal installation, install the .NET Framework from Windows Update.

**OCR not working**: Install Tesseract 4.0+. Add the installation directory to your PATH or place tesseract.exe in the current directory.

**Region capture returns empty or wrong size**: Verify the region coordinates with `snap.exe -List` first to find the correct window dimensions and monitor origin.

## License

MIT

## Author

KitsuneTech1
