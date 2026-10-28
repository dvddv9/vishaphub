<#
.SYNOPSIS
    Verify that the Vishap desktop app actually starts.

.DESCRIPTION
    Starts vishap-desktop.exe, waits for the bundled Python backend to answer on
    127.0.0.1:5001, and prints a PASS/FAIL verdict with the evidence:

      - whether the process stayed alive,
      - its window title,
      - the boot trace written by the app (pid + timestamp),
      - the WebView2 profile location it chose,
      - the tail of logs\startup-error.log and logs\backend.log when something
        went wrong.

    Run it after a build, or when someone reports "the window does not open".

.PARAMETER Exe
    Path to vishap-desktop.exe. Defaults to the release build in this repo.

.PARAMETER TimeoutSeconds
    How long to wait for the backend. The first start is slower: WebView2
    creates its profile and Python imports FastAPI.

.EXAMPLE
    .\scripts\verify_desktop.ps1
#>
[CmdletBinding()]
param(
    [string]$Exe = "",
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"

if (-not $Exe) {
    $Exe = Join-Path (Split-Path -Parent $PSScriptRoot) "src-tauri\target\release\vishap-desktop.exe"
}
if (-not (Test-Path $Exe)) { throw "Executable not found: $Exe" }

$AppRoot = Join-Path $env:LOCALAPPDATA "com.vishap.desktop"
$Boot = Join-Path $AppRoot "logs\boot.txt"
$StartupLog = Join-Path $AppRoot "logs\startup-error.log"
$BackendLog = Join-Path $AppRoot "logs\backend.log"

Remove-Item $Boot -ErrorAction SilentlyContinue

$version = (Get-Item $Exe).VersionInfo.FileVersion
Write-Host "==> Vishap desktop verification" -ForegroundColor Cyan
Write-Host "    exe     : $Exe"
Write-Host "    version : $version"
Write-Host ""

$proc = Start-Process -FilePath $Exe -PassThru

function Test-Backend {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        return $client.ConnectAsync("127.0.0.1", 5001).Wait(700)
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$backendUp = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 700
    if ($proc.HasExited) { break }
    if (Test-Backend) { $backendUp = $true; break }
}

$alive = -not $proc.HasExited
$title = ""
if ($alive) {
    $proc.Refresh()
    $title = $proc.MainWindowTitle
}

$bootText = if (Test-Path $Boot) { (Get-Content $Boot -Raw).Trim() } else { "(missing)" }

Write-Host "    process alive : $alive"
Write-Host "    window title  : $($title -replace '^$','(none yet)')"
Write-Host "    backend :5001 : $backendUp"
Write-Host "    boot trace    : $bootText"
Write-Host ""

$pass = $alive -and $backendUp

if (-not $pass) {
    Write-Host "==> FAIL" -ForegroundColor Red
    if ($proc.HasExited) {
        Write-Host "    exit code: $($proc.ExitCode) (0x$('{0:X8}' -f $proc.ExitCode))"
    }
    foreach ($log in @($StartupLog, $BackendLog)) {
        if (Test-Path $log) {
            Write-Host ""
            Write-Host "--- $log (tail) ---" -ForegroundColor Yellow
            Get-Content $log -Tail 15 | ForEach-Object { "    $_" }
        }
    }
    Write-Host ""
    Write-Host "    If the log says 'Access denied', the app could not create its" -ForegroundColor Yellow
    Write-Host "    WebView2 profile. Run .\scripts\reset_desktop_profile.ps1 and retry." -ForegroundColor Yellow
}
else {
    Write-Host "==> PASS - the window is up and the backend answers" -ForegroundColor Green
}

# Close what we started; the app stops its Python child on close.
if (-not $proc.HasExited) {
    Write-Host ""
    Write-Host "==> closing the app" -ForegroundColor Cyan
    $proc.CloseMainWindow() | Out-Null
    Start-Sleep -Seconds 5
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}

if ($pass) { exit 0 } else { exit 1 }
