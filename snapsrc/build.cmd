@echo off
REM Rebuild snap.exe from Snap.cs. Native, ~150 ms capture (vs ~490 ms for the old .ps1).
if exist "%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" (
  set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
) else (
  set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
)
if not exist "%CSC%" (
  echo csc.exe not found under %WINDIR%\Microsoft.NET\Framework or Framework64\v4.0.30319 1>&2
  exit /b 1
)
"%CSC%" -nologo -optimize+ -target:exe -out:"%~dp0..\snap.exe" -r:System.Windows.Forms.dll -r:System.Drawing.dll "%~dp0Snap.cs"
echo built %~dp0..\snap.exe
