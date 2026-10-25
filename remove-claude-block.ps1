Set-Location "C:\AI\conveyor_app"
$ErrorActionPreference = "Stop"

$readme = ".\README.md"
if (-not (Test-Path $readme)) { Write-Host "[!] README.md not found" -ForegroundColor Red; exit 1 }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item $readme "$readme.bak-$stamp"
Write-Host "[+] Backup: $readme.bak-$stamp" -ForegroundColor Green

$content = Get-Content $readme -Raw -Encoding UTF8

# Remove the Claude Desktop extension block:
# from "## 🧠 Claude Desktop extension" up to (but not including) the next "## " heading
$pattern = "(?s)## 🧠 Claude Desktop extension.*?(?=\r?\n## )"

if ($content -match $pattern) {
    $content = $content -replace $pattern, ""
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Resolve-Path $readme).Path, $content, $utf8NoBom)
    Write-Host "[+] Removed Claude Desktop extension block" -ForegroundColor Green
} else {
    Write-Host "[!] Block not found (already removed?)" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "[*] Remaining mentions of Claude/claude-plugin in README.md:" -ForegroundColor Cyan
$left = Select-String -Path $readme -Pattern "Claude|claude-plugin" -ErrorAction SilentlyContinue
if ($left) {
    $left | ForEach-Object { Write-Host ("    {0}: {1}" -f $_.LineNumber, $_.Line.Trim()) -ForegroundColor Yellow }
} else {
    Write-Host "    (none)" -ForegroundColor Green
}

Write-Host ""
Write-Host "[*] diff:" -ForegroundColor Cyan
git diff --stat -- README.md

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  git add README.md" -ForegroundColor White
Write-Host "  git commit -m ""docs: remove Claude Desktop extension section from README""" -ForegroundColor White
Write-Host "  git push origin remove-stripe-add-lemon" -ForegroundColor White