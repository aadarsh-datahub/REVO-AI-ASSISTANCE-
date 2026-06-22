$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "REVO OS - Windows setup" -ForegroundColor Cyan
python --version | Out-Host
if (-not (Test-Path ".venv")) {
  python -m venv .venv
}
& ".\.venv\Scripts\python.exe" setup.py
Write-Host "Setup complete. Add API keys in config\api_keys.json, then run .\start_revo.bat" -ForegroundColor Green
