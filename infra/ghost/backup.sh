#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
cd /opt/ghost
exec 9>/run/ghost-backup.lock
flock -n 9 || { echo 'A Ghost backup is already running.' >&2; exit 1; }
destination=/var/backups/ghost
install -d -m 0700 "$destination"
temporary=$(mktemp -d "$destination/.backup-XXXXXX")
stopped=false
cleanup() {
  status=$?
  if "$stopped"; then
    docker compose start --wait --wait-timeout 180 ghost >/dev/null || status=1
  fi
  rm -rf "$temporary"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

stopped=true
docker compose stop ghost
docker compose exec -T db sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysqldump --user=root --single-transaction --routines --triggers --events --no-tablespaces ghost' > "$temporary/ghost.sql"
docker compose cp ghost:/var/lib/ghost/content "$temporary/content"
cp .env config.production.json compose.yml nginx.conf "$temporary/"
archive="$destination/ghost-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar -C "$temporary" -czf "$archive.tmp" .
mv "$archive.tmp" "$archive"
echo "Backup saved to $archive. Copy it to encrypted off-server storage."
