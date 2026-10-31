#!/usr/bin/env sh
# VishapHub, self-hosted: asks four questions, writes .env, builds and starts it.
#   ./install.sh              interactive
#   ./install.sh --yes        defaults: Anthropic, solo, localhost only (set VISHAP_HUB_LLM_KEY first)
set -eu
cd "$(dirname "$0")"

say() { printf '%s\n' "$*"; }
ask() { # ask "question" default -> $REPLY
  if [ "${YES:-0}" = 1 ]; then REPLY=$2; return; fi
  printf '%s [%s] ' "$1" "$2"; read -r REPLY || REPLY=""; [ -n "$REPLY" ] || REPLY=$2
}
rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

[ "${1:-}" = "--yes" ] && YES=1

command -v docker >/dev/null 2>&1 || { say "Docker is not installed. Install Docker Engine or Docker Desktop and run this again."; exit 1; }
docker compose version >/dev/null 2>&1 || { say "The 'docker compose' plugin is missing."; exit 1; }
docker info >/dev/null 2>&1 || { say "Docker is installed but not running (or you may not use it)."; exit 1; }

if [ -f .env ]; then
  say ".env already exists - keeping it. Delete it to answer the questions again."
else
  say "1/4 Which model? anthropic = Claude, deepseek = DeepSeek, openai = ChatGPT or any OpenAI-compatible server (OpenRouter, Ollama, LM Studio, vLLM), none = rules only"
  ask "provider" anthropic; PROVIDER=$REPLY
  URL=""; MODEL=""; KEY="${VISHAP_HUB_LLM_KEY:-}"
  case "$PROVIDER" in
    openai)
      ask "address of the server" "http://host.docker.internal:11434/v1"; URL=$REPLY
      ask "model name (as the server calls it)" "llama3.1"; MODEL=$REPLY ;;
    anthropic|deepseek|none) ;;
    *) say "unknown provider: $PROVIDER"; exit 1 ;;
  esac
  if [ "$PROVIDER" != none ] && [ -z "$KEY" ] && [ "${YES:-0}" != 1 ]; then
    printf '   key (empty for a local server): '; stty -echo 2>/dev/null || true; read -r KEY || KEY=""; stty echo 2>/dev/null || true; echo
  fi
  say "2/4 Must everything stay on this machine and its private network? (also turns the voice off)"
  ask "offline (y/n)" n; case "$REPLY" in y|Y|yes) OFFLINE=1; VOICE=0 ;; *) OFFLINE=""; VOICE=1 ;; esac
  say "3/4 Submitted code is run inside the hub container, with no extra sandbox, as in 'host' mode."
  say "    That is fine for code you wrote or trust. For code from strangers use the pipx install with a Docker worker."
  ask "ok (y/n)" y; [ "$REPLY" = y ] || [ "$REPLY" = Y ] || { say "Stopped."; exit 1; }
  say "4/4 One person on one machine (solo) or a team with keys and quotas (team, adds Postgres)?"
  ask "mode (solo/team)" solo; MODE=$REPLY
  PGPW=""; APPPW=""; DBURL=""
  if [ "$MODE" = team ]; then PGPW=$(rand); APPPW=$(rand); DBURL="postgresql://vishap_hub_app:$APPPW@db:5432/vishap"; fi
  umask 077
  {
    echo "VISHAP_HUB_LLM_PROVIDER=$PROVIDER"; echo "VISHAP_HUB_LLM_URL=$URL"; echo "VISHAP_HUB_LLM_MODEL=$MODEL"
    echo "VISHAP_HUB_LLM_KEY=$KEY"; echo "VISHAP_HUB_OFFLINE=$OFFLINE"; echo "VISHAP_HUB_VOICE=$VOICE"
    echo "VISHAP_HUB_ISOLATION=host"; echo "VISHAP_HUB_BIND=127.0.0.1"; echo "VISHAP_HUB_PORT=8080"
    echo "POSTGRES_PASSWORD=$PGPW"; echo "VISHAP_HUB_APP_PASSWORD=$APPPW"; echo "VISHAP_HUB_DATABASE_URL=$DBURL"
    echo "COMPOSE_PROFILES=$([ "$MODE" = team ] && echo team)"
  } > .env
  say "Wrote .env (readable by you only)."
fi

say "Building and starting (the first build takes a few minutes)..."
docker compose up -d --build
PORT=$(sed -n 's/^VISHAP_HUB_PORT=//p' .env | head -1); PORT=${PORT:-8080}
i=0; until docker compose exec -T hub python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health').read()" >/dev/null 2>&1; do
  i=$((i+1)); [ $i -lt 60 ] || { say "The hub did not become healthy. See: docker compose logs hub"; exit 1; }; sleep 2
done
say "Up: http://127.0.0.1:$PORT"
say "Manage it with ./vishap.sh (status, logs, backup, restore, upgrade, stop)."
