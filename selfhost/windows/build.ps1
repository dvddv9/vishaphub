# Builds VishapHub-Setup.exe: a per-user Windows installer that carries its own Python.
#   .\build.ps1                (needs internet for Python, pip and the packages; Inno Setup for the last step)
#   .\build.ps1 -Iscc "C:\path\ISCC.exe"
# The installer carries its own Python with every package installed into it, because the validator runs a
# deliverable's tests with `sys.executable -m pytest`: a single frozen .exe has no Python to do that.
param([string]$Iscc = "", [string]$PythonVersion = "3.12.7")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$build = Join-Path $PSScriptRoot "build"; $app = Join-Path $build "app"; $py = Join-Path $app "python"
function Step($m) { Write-Host "==> $m" }
function Run { & $args[0] @($args | Select-Object -Skip 1); if ($LASTEXITCODE -ne 0) { throw "failed: $($args -join ' ')" } }

if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force $py | Out-Null

Step "Python $PythonVersion (the NuGet package: a normal, relocatable layout)"
# Not the "embeddable" zip: its ._pth file makes Python ignore PYTHONPATH and the current directory, and the
# validator relies on both (the network guard is loaded from PYTHONPATH; the deliverable is imported from its folder).
$zip = Join-Path $build "python.nupkg.zip"
Invoke-WebRequest "https://www.nuget.org/api/v2/package/python/$PythonVersion" -OutFile $zip -UseBasicParsing
$unz = Join-Path $build "nupkg"; Expand-Archive $zip -DestinationPath $unz -Force
Copy-Item (Join-Path $unz "tools\*") $py -Recurse -Force
Remove-Item $unz -Recurse -Force; Remove-Item $zip -Force
Get-ChildItem $py -Recurse -Directory -Include "__pycache__","test","tests","idlelib","turtledemo" -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch "site-packages" } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Step "pip"
Run "$py\python.exe" -m ensurepip --upgrade

Step "packages (copied into the installer's Python, not linked to this checkout)"
Run "$py\python.exe" -m pip install --no-warn-script-location "$root\packages\core" "$root\apps\validator" "pytest==9.1.1" "edge-tts==7.3.1"
Run "$py\python.exe" -m pip install --no-warn-script-location --no-deps "$root\apps\analyzer"
Run "$py\python.exe" -m pip install --no-warn-script-location "$root\apps\hub"

Step "launchers"
Copy-Item (Join-Path $PSScriptRoot "launchers\*") $app
Copy-Item (Join-Path $root "docs\self-hosted.md") (Join-Path $app "README.md")
Copy-Item (Join-Path $root "apps\hub\LICENSE*") $app -ErrorAction SilentlyContinue

Step "self-check"
Run "$py\python.exe" -m hub.cli --version
$probe = Join-Path $build "probe"; New-Item -ItemType Directory $probe | Out-Null
"MARK = 7" | Set-Content (Join-Path $probe "sitecustomize.py"); "VALUE = 3" | Set-Content (Join-Path $probe "probe_mod.py")
$env:PYTHONPATH = $probe
Push-Location $probe
$out = & "$py\python.exe" -c "import sys, sitecustomize, probe_mod, validator, pytest, hub.selfhost; foreign=[p for p in sys.path if p and not p.lower().startswith((r'$py'.lower(), r'$probe'.lower()))]; print('foreign' if foreign else 'self-contained', sitecustomize.MARK, probe_mod.VALUE)"
Pop-Location; Remove-Item Env:PYTHONPATH
if ($out -notmatch "^self-contained 7 3") { throw "the bundled Python is not self-contained or ignores PYTHONPATH/cwd: $out" }
Write-Host "self-check: $out"

if (-not $Iscc) {
  $Iscc = @("C:\Program Files (x86)\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "C:\AI\tools\InnoSetup\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc) { Write-Host "Inno Setup not found: the folder $app is ready, the .exe was not built. Install Inno Setup 6 and run again."; exit 3 }
Step "installer"
$version = (Select-String -Path (Join-Path $root "apps\hub\pyproject.toml") -Pattern '^version = "(.*)"').Matches.Groups[1].Value
Run $Iscc "/DAppVersion=$version" "/DSourceDir=$app" "/O$build" (Join-Path $PSScriptRoot "vishaphub.iss")
Write-Host "Built: $(Join-Path $build 'VishapHub-Setup.exe')"
