@echo off
REM Rebuild snap.exe from Snap.cs. Native, ~150 ms capture (vs ~490 ms for the old .ps1).
set CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe
"%CSC%" -nologo -optimize+ -target:exe -out:"%~dp0..\snap.exe" -r:System.Windows.Forms.dll -r:System.Drawing.dll "%~dp0Snap.cs"
echo built %~dp0..\snap.exe
