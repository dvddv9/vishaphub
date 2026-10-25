Set-Location "C:\AI\conveyor_app"
$ErrorActionPreference = "Stop"

Write-Host "=== check-deploy.ps1 ===" -ForegroundColor Cyan

# --- 1. render.yaml ---
Write-Host ""
Write-Host "[*] render.yaml:" -ForegroundColor Cyan
if (Test-Path ".\render.yaml") {
    Get-Content .\render.yaml
    Write-Host ""
    $hasAlembic = Select-String -Path .\render.yaml -Pattern "alembic upgrade head" -Quiet
    if ($hasAlembic) { Write-Host "[+] alembic upgrade head found in render.yaml" -ForegroundColor Green }
    else { Write-Host "[!] alembic upgrade head NOT in render.yaml" -ForegroundColor Red }
} else {
    Write-Host "[!] render.yaml not found" -ForegroundColor Yellow
}

# --- 2. Dockerfile ---
Write-Host ""
Write-Host "[*] Dockerfile (last 20 lines):" -ForegroundColor Cyan
if (Test-Path ".\Dockerfile") {
    Get-Content .\Dockerfile | Select-Object -Last 20
    Write-Host ""
    $hasAlembicDf = Select-String -Path .\Dockerfile -Pattern "alembic upgrade head" -Quiet
    if ($hasAlembicDf) { Write-Host "[+] alembic upgrade head found in Dockerfile" -ForegroundColor Green }
    else { Write-Host "[!] alembic upgrade head NOT in Dockerfile" -ForegroundColor Red }
} else {
    Write-Host "[!] Dockerfile not found" -ForegroundColor Yellow
}

# --- 3. docker-compose.yml (для локальной инфы) ---
Write-Host ""
Write-Host "[*] docker-compose.yml (grep command):" -ForegroundColor Cyan
if (Test-Path ".\docker-compose.yml") {
    Select-String -Path .\docker-compose.yml -Pattern "command:|alembic|uvicorn" -Context 0,1
} else {
    Write-Host "[!] docker-compose.yml not found" -ForegroundColor Yellow
}

# --- 4. start_all.ps1 / run_local.ps1 ---
Write-Host ""
Write-Host "[*] start_all.ps1 / run_local.ps1 (grep alembic/uvicorn):" -ForegroundColor Cyan
Get-ChildItem .\*.ps1, .\*.bat -ErrorAction SilentlyContinue | ForEach-Object {
    $hits = Select-String -Path $_.FullName -Pattern "alembic|uvicorn" -ErrorAction SilentlyContinue
    if ($hits) {
        Write-Host "  --- $($_.Name) ---" -ForegroundColor Yellow
        $hits | ForEach-Object { Write-Host ("    {0}: {1}" -f $_.LineNumber, $_.Line.Trim()) -ForegroundColor White }
    }
}

# --- 5. где вообще упоминается alembic upgrade ---
Write-Host ""
Write-Host "[*] Where alembic upgrade head is referenced (repo-wide):" -ForegroundColor Cyan
Get-ChildItem -Recurse -File -Include *.yaml,*.yml,*.ps1,*.bat,*.sh,Dockerfile* -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\node_modules\\|\\.git\\|\\_backup_" } |
    ForEach-Object {
        $hits = Select-String -Path $_.FullName -Pattern "alembic upgrade head" -ErrorAction SilentlyContinue
        if ($hits) { $hits | ForEach-Object { Write-Host ("    {0}:{1}" -f $_.Path, $_.LineNumber) -ForegroundColor Green } }
    }

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan
Write-Host "Next: if alembic upgrade head missing -> add to render.yaml startCommand or Dockerfile CMD" -ForegroundColor Yellow