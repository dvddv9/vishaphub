# Start the web form and API on this computer: http://127.0.0.1:8787/
# The model comes from the environment of this PowerShell session; the key is never written anywhere.
Set-Location $PSScriptRoot
if (Test-Path .\.venv\Scripts\Activate.ps1) { & .\.venv\Scripts\Activate.ps1 }
$env:PYTHONPATH = "src"

foreach ($name in "CUSTOM_LLM_URL", "CUSTOM_LLM_MODEL", "CUSTOM_LLM_KEY") {
    if (-not (Get-Item "Env:$name" -ErrorAction SilentlyContinue)) {
        Write-Host "[!] $name is not set; the form can still check a spec, but not generate code." -ForegroundColor Yellow
    }
}
Write-Host "[+] Starting vishap-generator..." -ForegroundColor Green
python -m generator serve
Write-Host "`nPress Enter to close this window..."
Read-Host
