@echo off
chcp 65001 >nul
title NEIS EduFine Widget Setup
echo.
echo  Downloading... please wait about 1 minute. Do not close this window.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $d=Join-Path $env:LOCALAPPDATA 'neis-automation-kit'; $z=Join-Path $env:TEMP 'neis-kit.zip'; $t=Join-Path $env:TEMP 'neis-kit-x'; try { Invoke-WebRequest 'https://github.com/workcalmkite-hue/neis-automation-kit/archive/refs/heads/main.zip' -OutFile $z -UseBasicParsing } catch { Write-Host ('Download failed: ' + $_.Exception.Message) -ForegroundColor Red; Read-Host 'Enter'; exit 1 }; if (Test-Path $t) { Remove-Item $t -Recurse -Force }; Expand-Archive $z $t -Force; $src=(Get-ChildItem $t -Directory | Select-Object -First 1).FullName; robocopy $src $d /E /XD .venv chrome_profile* /NFL /NDL /NJH /NJS /NP | Out-Null; Get-ChildItem $d -Recurse -File | Unblock-File; & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $d 'widget\install.ps1')"
