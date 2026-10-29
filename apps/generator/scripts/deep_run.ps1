# One real run at deep effort on two example specs. Writes nothing into the project except reports\.
# The model key is asked for here, kept only in this PowerShell session, and never written anywhere.
# Usage (from the project folder):  powershell -ExecutionPolicy Bypass -File scripts\deep_run.ps1
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONPATH = "src"
if (-not $env:CUSTOM_LLM_URL)   { $env:CUSTOM_LLM_URL = "https://api.anthropic.com/v1" }
if (-not $env:CUSTOM_LLM_MODEL) { $env:CUSTOM_LLM_MODEL = "claude-sonnet-5-5" }
if (-not $env:CUSTOM_LLM_KEY) {
    $secure = Read-Host "Model API key (not shown, not saved)" -AsSecureString
    $env:CUSTOM_LLM_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
}
New-Item -ItemType Directory -Force -Path reports | Out-Null
$out = Join-Path $env:TEMP "vg-deep-out"

foreach ($name in "spec-clean", "spec-create-user") {
    Write-Host "`n=== $name (deep, dry run) ===" -ForegroundColor Cyan
    python -m generator generate "examples\$name.yaml" --out $out --dry-run --effort deep `
        --report "reports\$name.md" --json "reports\$name.json" 2>&1 | Tee-Object -FilePath "reports\$name.log"
}
Write-Host "`nDone. Send these files back: reports\*.md and reports\*.log" -ForegroundColor Green
Remove-Item Env:CUSTOM_LLM_KEY
