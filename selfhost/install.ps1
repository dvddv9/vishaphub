# VishapHub, self-hosted (Windows): asks four questions, writes .env, builds and starts it.
#   .\install.ps1          interactive
#   .\install.ps1 -Yes     defaults: Anthropic, solo, localhost only (set $env:VISHAP_HUB_LLM_KEY first)
param([switch]$Yes)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Ask($q, $d) { if ($Yes) { return $d }; $r = Read-Host "$q [$d]"; if ([string]::IsNullOrWhiteSpace($r)) { $d } else { $r.Trim() } }
function Rand { -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) }) }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is not installed. Install Docker Desktop and run this again." }
& docker compose version *> $null; if ($LASTEXITCODE -ne 0) { throw "The 'docker compose' plugin is missing." }
& docker info *> $null; if ($LASTEXITCODE -ne 0) { throw "Docker is installed but not running. Start Docker Desktop." }

if (Test-Path .env) { Write-Host ".env already exists - keeping it. Delete it to answer the questions again." }
else {
  Write-Host "1/4 Which model? anthropic = Claude, deepseek = DeepSeek, openai = ChatGPT or any OpenAI-compatible server (OpenRouter, Ollama, LM Studio, vLLM), none = rules only"
  $provider = Ask "provider" "anthropic"
  $url = ""; $model = ""; $key = $env:VISHAP_HUB_LLM_KEY
  switch ($provider) {
    "openai" { $url = Ask "address of the server" "http://host.docker.internal:11434/v1"; $model = Ask "model name (as the server calls it)" "llama3.1" }
    { $_ -in "anthropic","deepseek","none" } { }
    default { throw "unknown provider: $provider" }
  }
  if ($provider -ne "none" -and -not $key -and -not $Yes) {
    $s = Read-Host "   key (empty for a local server)" -AsSecureString
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
  }
  Write-Host "2/4 Must everything stay on this machine and its private network? (also turns the voice off)"
  $off = Ask "offline (y/n)" "n"; if ($off -match '^(y|yes)$') { $offline = "1"; $voice = "0" } else { $offline = ""; $voice = "1" }
  Write-Host "3/4 Submitted code is run inside the hub container with no extra sandbox ('host' mode)."
  Write-Host "    Fine for code you wrote or trust. For code from strangers use the pipx install with a Docker worker."
  if ((Ask "ok (y/n)" "y") -notmatch '^(y|yes)$') { Write-Host "Stopped."; exit 1 }
  Write-Host "4/4 One person on one machine (solo) or a team with keys and quotas (team, adds Postgres)?"
  $mode = Ask "mode (solo/team)" "solo"
  $pg = ""; $app = ""; $db = ""; $prof = ""
  if ($mode -eq "team") { $pg = Rand; $app = Rand; $db = "postgresql://vishap_hub_app:$app@db:5432/vishap"; $prof = "team" }
  $lines = @("VISHAP_HUB_LLM_PROVIDER=$provider","VISHAP_HUB_LLM_URL=$url","VISHAP_HUB_LLM_MODEL=$model","VISHAP_HUB_LLM_KEY=$key",
    "VISHAP_HUB_OFFLINE=$offline","VISHAP_HUB_VOICE=$voice","VISHAP_HUB_ISOLATION=host","VISHAP_HUB_BIND=127.0.0.1","VISHAP_HUB_PORT=8080",
    "POSTGRES_PASSWORD=$pg","VISHAP_HUB_APP_PASSWORD=$app","VISHAP_HUB_DATABASE_URL=$db","COMPOSE_PROFILES=$prof")
  [IO.File]::WriteAllLines((Join-Path $PSScriptRoot ".env"), $lines, (New-Object Text.UTF8Encoding $false))
  Write-Host "Wrote .env."
}

Write-Host "Building and starting (the first build takes a few minutes)..."
& docker compose up -d --build; if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
$port = ((Select-String -Path .env -Pattern '^VISHAP_HUB_PORT=(.*)$').Matches.Groups[1].Value); if (-not $port) { $port = "8080" }
$ok = $false
for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
  & docker compose exec -T hub python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health').read()" *> $null
  if ($LASTEXITCODE -eq 0) { $ok = $true } else { Start-Sleep -Seconds 2 }
}
if (-not $ok) { throw "The hub did not become healthy. See: docker compose logs hub" }
Write-Host "Up: http://127.0.0.1:$port"
Write-Host "Manage it with .\vishap.ps1 (status, logs, backup, restore, upgrade, stop)."
