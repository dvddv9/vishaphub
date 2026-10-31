# Day-two operations (Windows): status | logs | stop | start | backup | restore <folder> | upgrade
param([string]$Command = "status", [string]$Path = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$img = "vishaphub/hub:local"; $vol = "vishaphub_hub-data"
function Run { param([string[]]$a) & docker @a; if ($LASTEXITCODE -ne 0) { throw "docker $($a -join ' ') failed ($LASTEXITCODE)" } }
switch ($Command) {
  "status"  { Run @("compose","ps") }
  "logs"    { Run @("compose","logs","-f","--tail=200","hub") }
  "stop"    { Run @("compose","stop") }
  "start"   { Run @("compose","up","-d") }
  "backup"  {
    $out = Join-Path "backups" ("vishap-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    New-Item -ItemType Directory -Force $out | Out-Null; $abs = (Resolve-Path $out).Path
    Run @("run","--rm","-u","0","-v","${vol}:/data:ro","-v","${abs}:/out",$img,"sh","-c","tar -C /data -cf /out/data.tar . && chmod a+r /out/data.tar")
    if ((& docker compose ps --services --filter status=running) -contains "db") {
      Run @("compose","exec","-T","db","sh","-c","pg_dump -U vishap_owner -d vishap -Fc -f /tmp/db.dump")
      Run @("compose","cp","db:/tmp/db.dump",(Join-Path $abs "db.dump"))
    }
    Copy-Item .env (Join-Path $abs "env.backup")
    Write-Host "Backup: selfhost\$out  (env.backup holds the model key and passwords; keep it private)"
  }
  "restore" {
    if (-not $Path) { throw "usage: vishap.ps1 restore <backup folder>" }
    $abs = (Resolve-Path $Path).Path
    if (-not (Test-Path (Join-Path $abs "data.tar"))) { throw "no data.tar in $Path" }
    Run @("compose","stop","hub")
    Run @("run","--rm","-u","0","-v","${vol}:/data","-v","${abs}:/in:ro",$img,"sh","-c","find /data -mindepth 1 -delete; tar -C /data -xf /in/data.tar; chown -R 1000 /data")
    if (Test-Path (Join-Path $abs "db.dump")) {
      Run @("compose","up","-d","db")
      Run @("compose","cp",(Join-Path $abs "db.dump"),"db:/tmp/db.dump")
      Run @("compose","exec","-T","db","pg_restore","-U","vishap_owner","-d","vishap","--clean","--if-exists","/tmp/db.dump")
    }
    Run @("compose","up","-d","hub"); Write-Host "Restored from $Path. .env was not touched."
  }
  "upgrade" {
    & $PSCommandPath backup
    & git -C .. pull --ff-only; if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
    Run @("compose","up","-d","--build")
    if (Select-String -Path .env -Pattern '^COMPOSE_PROFILES=.*team' -Quiet) { Run @("compose","run","--rm","migrate") }
    Write-Host "Upgraded."
  }
  default { Write-Host "usage: vishap.ps1 status|logs|stop|start|backup|restore <folder>|upgrade"; exit 2 }
}
