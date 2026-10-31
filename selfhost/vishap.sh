#!/usr/bin/env sh
# Day-two operations for the bundle: status | logs | stop | start | backup | restore <folder> | upgrade
# A backup is a folder: data.tar (the runs), db.dump (team mode only), env.backup (your .env, with secrets).
set -eu
cd "$(dirname "$0")"
IMG=vishaphub/hub:local
VOL=vishaphub_hub-data
cmd=${1:-status}
case "$cmd" in
  status)  docker compose ps ;;
  logs)    docker compose logs -f --tail=200 hub ;;
  stop)    docker compose stop ;;
  start)   docker compose up -d ;;
  backup)
    out="backups/vishap-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$out"; abs=$(cd "$out" && pwd)
    docker run --rm -u 0 -v $VOL:/data:ro -v "$abs":/out $IMG sh -c 'tar -C /data -cf /out/data.tar . && chmod a+r /out/data.tar'
    if docker compose ps --services --filter status=running | grep -qx db; then
      docker compose exec -T db sh -c 'pg_dump -U vishap_owner -d vishap -Fc -f /tmp/db.dump'
      docker compose cp db:/tmp/db.dump "$out/db.dump"
    fi
    cp .env "$out/env.backup"; chmod 600 "$out/env.backup"
    echo "Backup: selfhost/$out  (env.backup holds the model key and passwords; keep it private)" ;;
  restore)
    src=${2:?usage: vishap.sh restore <backup folder>}; abs=$(cd "$src" && pwd)
    [ -f "$abs/data.tar" ] || { echo "no data.tar in $src"; exit 1; }
    docker compose stop hub
    docker run --rm -u 0 -v $VOL:/data -v "$abs":/in:ro $IMG sh -c 'find /data -mindepth 1 -delete; tar -C /data -xf /in/data.tar; chown -R 1000 /data'
    if [ -f "$abs/db.dump" ]; then
      docker compose up -d db
      docker compose cp "$abs/db.dump" db:/tmp/db.dump
      docker compose exec -T db pg_restore -U vishap_owner -d vishap --clean --if-exists /tmp/db.dump
    fi
    docker compose up -d hub; echo "Restored from $src. .env was not touched." ;;
  upgrade)
    "$0" backup
    git -C .. pull --ff-only
    docker compose up -d --build
    if grep -q '^COMPOSE_PROFILES=.*team' .env; then docker compose run --rm migrate; fi
    echo "Upgraded." ;;
  *) echo "usage: $0 status|logs|stop|start|backup|restore <folder>|upgrade"; exit 2 ;;
esac
