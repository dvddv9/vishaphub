<#
.SYNOPSIS
    Build (or run) the Vishap desktop app.

.DESCRIPTION
    Runs on the host: it needs Rust, the Tauri CLI, Node and Python on PATH.
    The DSH sandbox cannot do this - it has no network to fetch crates.

    Steps: check toolchain -> export the Next.js site -> cargo tauri build.
    With -Dev it starts `cargo tauri dev` instead (Next dev server on :3000 and
    the Python backend spawned by the shell).

.EXAMPLE
    .\scripts\build_desktop.ps1
    .\scripts\build_desktop.ps1 -Dev
    .\scripts\build_desktop.ps1 -PythonExe .\.venv\Scripts\python.exe
#>
[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$SkipFrontend,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Require-Tool {
    param([string]$Name, [string]$Hint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' not found on PATH. $Hint"
    }
}

Write-Host "==> Checking toolchain" -ForegroundColor Cyan
Require-Tool -Name "cargo" -Hint "Install Rust: https://rustup.rs"
Require-Tool -Name "npm" -Hint "Install Node.js 20+."

# `cargo tauri` is a cargo subcommand; missing cargo-tauri is the usual failure.
& cargo tauri --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The Tauri CLI is missing. Run: cargo install tauri-cli --version '^2' --locked"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not $PythonExe) {
    Write-Warning "No 'python' on PATH. The shell will show its error card; set VISHAP_PYTHON or pass -PythonExe."
}

if ($PythonExe) {
    $resolved = (Resolve-Path $PythonExe).Path
    Write-Host "==> VISHAP_PYTHON=$resolved" -ForegroundColor Cyan
    $env:VISHAP_PYTHON = $resolved
}
$env:VISHAP_HOME = $Root

if ($Dev) {
    Write-Host "==> cargo tauri dev (Next on :3000, backend on :5001)" -ForegroundColor Cyan
    & cargo tauri dev
    exit $LASTEXITCODE
}

if (-not $SkipFrontend) {
    Write-Host "==> Exporting the Next.js site to ui-next/out" -ForegroundColor Cyan
    Push-Location ui-next
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)." }
    }
    finally {
        Pop-Location
    }
}

Write-Host "==> cargo tauri build" -ForegroundColor Cyan
& cargo tauri build
if ($LASTEXITCODE -ne 0) { throw "cargo tauri build failed (exit $LASTEXITCODE)." }

$bundle = Join-Path $Root "src-tauri\target\release\bundle"
Write-Host "`n==> Artifacts" -ForegroundColor Green
Get-ChildItem -Path $bundle -Recurse -File -Include *.exe, *.msi -ErrorAction SilentlyContinue |
    Select-Object FullName, @{N = "MB"; E = { [math]::Round($_.Length / 1MB, 1) } } |
    Format-Table -AutoSize
