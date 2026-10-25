Set-Location "C:\AI\conveyor_app"
$ErrorActionPreference = "Stop"

Write-Host "=== migrate-render-db.ps1 (v2, asyncpg) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Paste Render DATABASE_URL (postgresql://user:pass@host/db)." -ForegroundColor Yellow
Write-Host "It will NOT be printed (password masked)." -ForegroundColor Yellow
$dbUrl = Read-Host "DATABASE_URL"

if (-not $dbUrl) { Write-Host "[!] empty" -ForegroundColor Red; exit 1 }

# Force asyncpg driver
if ($dbUrl -match "^postgresql(\+\w+)?://") {
    $dbUrl = $dbUrl -replace "^postgresql(\+\w+)?://", "postgresql+asyncpg://"
} else {
    Write-Host "[!] URL must start with postgresql://" -ForegroundColor Red; exit 1
}

# Parse
$rx = [regex]"^postgresql\+asyncpg://([^:]+):([^@]+)@([^/]+)/(.+)$"
$m = $rx.Match($dbUrl)
if (-not $m.Success) { Write-Host "[!] cannot parse URL" -ForegroundColor Red; exit 1 }
$user = $m.Groups[1].Value
$pass = $m.Groups[2].Value
$hostPart = $m.Groups[3].Value
$db = $m.Groups[4].Value
$hostOnly = ($hostPart -split ":")[0]
$port = if ($hostPart -match ":(\d+)$") { $Matches[1] } else { "5432" }

Write-Host ""
Write-Host "[*] Host: $hostOnly, Port: $port, User: $user, DB: $db, Pass: **** (len=$($pass.Length))" -ForegroundColor Cyan

$env:DATABASE_URL = $dbUrl
$env:PGPASSWORD = $pass
$env:PGSSLMODE = "require"

Write-Host ""
Write-Host "[*] alembic upgrade head..." -ForegroundColor Cyan
alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Host "[!] alembic upgrade failed" -ForegroundColor Red; exit 1 }
Write-Host "[+] OK" -ForegroundColor Green

Write-Host ""
Write-Host "[*] alembic current:" -ForegroundColor Cyan
alembic current

$psql = "C:\Program Files\PostgreSQL\16\bin\psql.exe"

Write-Host ""
Write-Host "[*] Tables:" -ForegroundColor Cyan
& $psql -h $hostOnly -p $port -U $user -d $db -c "\dt"

Write-Host ""
Write-Host "[*] Create test_tenant_1:" -ForegroundColor Cyan
& $psql -h $hostOnly -p $port -U $user -d $db -c "INSERT INTO tenants (tenant_id, api_key, plan, status, email) VALUES ('test_tenant_1', 'dummy', 'pro', 'active', 'test@example.com') ON CONFLICT (tenant_id) DO NOTHING;"

Write-Host ""
Write-Host "[*] tenants:" -ForegroundColor Cyan
& $psql -h $hostOnly -p $port -U $user -d $db -c "SELECT tenant_id, status, ls_customer_id FROM tenants;"

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan