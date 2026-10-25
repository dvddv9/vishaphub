Set-Location "C:\AI\conveyor_app"
$ErrorActionPreference = "Stop"

Write-Host "=== check-render-db.ps1 ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Paste Render DATABASE_URL (postgresql://user:pass@host/db)." -ForegroundColor Yellow
Write-Host "It will NOT be saved or printed (password masked)." -ForegroundColor Yellow
$dbUrl = Read-Host "DATABASE_URL"

if (-not $dbUrl) { Write-Host "[!] empty" -ForegroundColor Red; exit 1 }

# Parse URL: postgresql://user:pass@host/db
$rx = [regex]"^postgres(ql)?://([^:]+):([^@]+)@([^/]+)/(.+)$"
$m = $rx.Match($dbUrl)
if (-not $m.Success) { Write-Host "[!] cannot parse DATABASE_URL" -ForegroundColor Red; exit 1 }
$user = $m.Groups[2].Value
$pass = $m.Groups[3].Value
$hostPart = $m.Groups[4].Value   # host:port
$db = $m.Groups[5].Value
$hostOnly = ($hostPart -split ":")[0]
$port = if ($hostPart -match ":(\d+)$") { $Matches[1] } else { "5432" }

Write-Host ""
Write-Host "[*] Host: $hostOnly" -ForegroundColor Cyan
Write-Host "[*] Port: $port" -ForegroundColor Cyan
Write-Host "[*] User: $user" -ForegroundColor Cyan
Write-Host "[*] DB:   $db" -ForegroundColor Cyan
Write-Host "[*] Pass: **** (len=$($pass.Length))" -ForegroundColor Cyan

$env:PGPASSWORD = $pass
$env:PGSSLMODE = "require"
$psql = "C:\Program Files\PostgreSQL\16\bin\psql.exe"

Write-Host ""
Write-Host "[*] Checking tables..." -ForegroundColor Cyan
& $psql -h $hostOnly -p $port -U $user -d $db -c "\dt"

Write-Host ""
Write-Host "[*] Checking alembic_version..." -ForegroundColor Cyan
& $psql -h $hostOnly -p $port -U $user -d $db -c "SELECT version_num FROM alembic_version;"

Write-Host ""
Write-Host "[*] processed_webhook_events (last 5)..." -ForegroundColor Cyan
& $psql -h $hostOnly -p $port -U $user -d $db -c "SELECT event_id, event_name, processed_at FROM processed_webhook_events ORDER BY processed_at DESC LIMIT 5;"

Write-Host ""
Write-Host "[*] tenants (last 5)..." -ForegroundColor Cyan
& $psql -h $hostOnly -p $port -U $user -d $db -c "SELECT tenant_id, status, ls_customer_id FROM tenants ORDER BY created_at DESC LIMIT 5;"

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan