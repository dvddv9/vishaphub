# VishapHub without Docker (Windows): installs the `vishap-hub` command with pipx. Python 3.11+ required.
#   $env:PYTHON = "py -3.12"   (optional)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = if ($env:PYTHON) { $env:PYTHON } else { "python" }
function Py { & $py @args; if ($LASTEXITCODE -ne 0) { throw "python $($args -join ' ') failed ($LASTEXITCODE)" } }
& $py -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }
& $py -m pipx --version *> $null
if ($LASTEXITCODE -ne 0) { Py -m pip install --user pipx }
Py -m pipx install --force ./apps/hub
Py -m pipx inject vishap-hub ./packages/core ./apps/validator "pytest==9.1.1" "edge-tts==7.3.1"
Py -m pipx runpip vishap-hub install --no-deps ./apps/analyzer
& $py -m pipx ensurepath *> $null
Write-Host "`nInstalled. Open a new terminal if 'vishap-hub' is not found, then:"
Write-Host "  vishap-hub init      # model, privacy, how code is run"
Write-Host "  vishap-hub doctor    # what this installation will do"
Write-Host "  vishap-hub serve     # http://127.0.0.1:8080"
