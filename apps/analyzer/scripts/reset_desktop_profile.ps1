<#
.SYNOPSIS
    Repair a Vishap desktop install that opens a black window or exits at once.

.DESCRIPTION
    The WebView2 profile lives in %LOCALAPPDATA%\com.vishap.desktop\webview2.
    If a previous run died while the webview was starting, a leftover
    msedgewebview2.exe can keep that folder locked; every later start then fails
    with

        failed to create webview: WebView2 error: HRESULT(0x800700AA)
        "The requested resource is in use."

    which shows up as a black window followed by a silent crash (WER 0xc0000409).

    This script kills the leftover WebView2 processes that belong to Vishap,
    moves the wedged profile aside, and can relaunch the app. Run it, then start
    Vishap again.

.PARAMETER Exe
    Path to vishap-desktop.exe. Defaults to the release build next to this repo.

.PARAMETER Launch
    Start the app after the repair.

.PARAMETER WhatIfProfileOnly
    Only move the profile aside; do not touch any process.

.EXAMPLE
    .\scripts\reset_desktop_profile.ps1 -Launch
#>
[CmdletBinding()]
param(
    [string]$Exe = "",
    [switch]$Launch,
    [switch]$WhatIfProfileOnly
)

$ErrorActionPreference = "Stop"

$Identifier = "com.vishap.desktop"
$AppRoot = Join-Path $env:LOCALAPPDATA $Identifier
$Profile = Join-Path $AppRoot "webview2"
$Broken = Join-Path $AppRoot "webview2.broken"
$LogDir = Join-Path $AppRoot "logs"

# The pre-7.0 builds kept the profile in "EBWebView" next to it. They ran
# elevated, so that folder may be admin-owned; this script leaves it alone on
# purpose - the current app never opens it.
$LegacyProfile = Join-Path $AppRoot "EBWebView"

Write-Host "==> Vishap desktop repair" -ForegroundColor Cyan
Write-Host "    app data : $AppRoot"
Write-Host "    profile  : $Profile"

if (-not (Test-Path $Profile)) {
    Write-Host "    (no profile yet - nothing to move)" -ForegroundColor Yellow
}

# --- 1. report what is running -------------------------------------------------
$app = Get-Process -Name "vishap-desktop" -ErrorAction SilentlyContinue
if ($app) {
    Write-Host "`n==> Closing running Vishap processes" -ForegroundColor Cyan
    $app | ForEach-Object { "    stopping pid $($_.Id)"; Stop-Process -Id $_.Id -Force }
    Start-Sleep -Seconds 2
}

# --- 2. find WebView2 processes that belong to Vishap --------------------------
if (-not $WhatIfProfileOnly) {
    Write-Host "`n==> Looking for leftover WebView2 processes of this app" -ForegroundColor Cyan
    $ours = @()
    try {
        $ours = Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Identifier*" }
    }
    catch {
        Write-Warning "Cannot inspect process command lines ($($_.Exception.Message))."
        Write-Warning "If the profile stays locked, reboot and run this script again."
    }

    if ($ours) {
        $ours | ForEach-Object { "    killing pid $($_.ProcessId) (holds $Identifier)"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
    }
    else {
        Write-Host "    none found"
    }
}

# --- 3. move the profile aside -------------------------------------------------
if (Test-Path $Profile) {
    Write-Host "`n==> Moving the wedged profile aside" -ForegroundColor Cyan
    if (Test-Path $Broken) { Remove-Item $Broken -Recurse -Force -ErrorAction SilentlyContinue }
    try {
        Rename-Item -Path $Profile -NewName (Split-Path $Broken -Leaf) -ErrorAction Stop
        Write-Host "    moved to $Broken" -ForegroundColor Green
    }
    catch {
        Write-Warning "Could not move the profile: $($_.Exception.Message)"
        Write-Warning "Something still holds it. Reboot, then run this script again."
    }
}

# --- 4. show the last startup error, if any -----------------------------------
$startupLog = Join-Path $LogDir "startup-error.log"
if (Test-Path $startupLog) {
    Write-Host "`n==> Last startup error" -ForegroundColor Cyan
    Get-Content $startupLog -Tail 12 | ForEach-Object { "    $_" }
}

$backendLog = Join-Path $LogDir "backend.log"
if (Test-Path $backendLog) {
    Write-Host "`n==> Backend log (tail)" -ForegroundColor Cyan
    Get-Content $backendLog -Tail 6 | ForEach-Object { "    $_" }
}

# --- 5. optional relaunch ------------------------------------------------------
if ($Launch) {
    if (-not $Exe) {
        $Exe = Join-Path (Split-Path -Parent $PSScriptRoot) "src-tauri\target\release\vishap-desktop.exe"
    }
    if (-not (Test-Path $Exe)) { throw "Executable not found: $Exe" }
    Write-Host "`n==> Launching $Exe" -ForegroundColor Cyan
    Start-Process -FilePath $Exe
}

Write-Host "`nDone. If the window is still blank, check $LogDir" -ForegroundColor Green
