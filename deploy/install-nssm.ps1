# Alternative wrapper: NSSM (https://nssm.cc) runs main.py as a service. No pywin32 needed.
# Run as Administrator from the project root: powershell -ExecutionPolicy Bypass -File deploy\install-nssm.ps1
param([string]$Name = "DiacritizerAPI")
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null
nssm install $Name "$root\.venv\Scripts\python.exe" "$root\main.py"
nssm set $Name AppDirectory $root
nssm set $Name DisplayName "Arabic Diacritizer API"
nssm set $Name Description "HTTP API that adds diacritics to Arabic text via routed LLM providers with strict validation."
nssm set $Name Start SERVICE_AUTO_START
nssm set $Name AppStdout "$root\logs\service.out.log"
nssm set $Name AppStderr "$root\logs\service.err.log"
nssm set $Name AppRotateFiles 1
nssm set $Name AppRotateBytes 5000000
nssm set $Name AppExit Default Restart
nssm set $Name AppRestartDelay 5000
nssm set $Name AppStopMethodSkip 0
nssm start $Name
nssm status $Name
