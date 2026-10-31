@echo off
REM One-word screenshot for agents. `snap` = whole active screen; `snap -app firefox`;
REM `snap -list`. For text reading use: powershell ... snap.ps1 -App firefox -Ocr
"%~dp0snap.exe" %*
