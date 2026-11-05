#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
temporary=$(mktemp -d)
project="ghost-smoke-$$"
compose() {
  docker compose --project-name "$project" --file "$temporary/compose.yml" "$@"
}
cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then
    compose logs --tail=100 >&2 || true
  fi
  compose down --volumes --remove-orphans >/dev/null || true
  rm -rf "$temporary"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cp "$root/compose.yml" "$temporary/"
python3 - "$temporary" "$root/nginx.conf.tftpl" <<'PY'
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit

root = Path(sys.argv[1])
password = secrets.token_hex(32)
(root / '.env').write_text(f'MYSQL_DATABASE=ghost\nMYSQL_USER=ghost\nMYSQL_PASSWORD={password}\nMYSQL_ROOT_PASSWORD={secrets.token_hex(32)}\n')
config = {
    'url': 'https://blog.example.com',
    'admin': {'url': 'https://ghost-admin.example.com'},
    'server': {'host': '0.0.0.0', 'port': 2368},
    'database': {'client': 'mysql', 'connection': {
        'host': 'db', 'user': 'ghost', 'password': password, 'database': 'ghost',
    }},
    'paths': {'contentPath': '/var/lib/ghost/content'},
}
(root / 'config.production.json').write_text(json.dumps(config))
(root / 'config.production.json').chmod(0o644)
template = Path(sys.argv[2]).read_text()
(root / 'nginx.conf').write_text(template.replace('${admin_hostname}', urlsplit(config['admin']['url']).hostname))
(root / 'nginx.conf').chmod(0o644)
PY

compose config --quiet
compose up -d --wait --wait-timeout 300
curl --fail --silent --show-error -H 'Host: blog.example.com' http://127.0.0.1:8080/ >/dev/null
code=$(curl --silent --show-error -o /dev/null -w '%{http_code}' -H 'Host: blog.example.com' -H 'X-Forwarded-Proto: http' http://127.0.0.1:8080/)
[[ "$code" == 308 ]] || { echo 'HTTP visitors must be redirected to HTTPS.' >&2; exit 1; }
for path in /ghost /ghost/ /Ghost/ /%67host/ /ghost%2fapi/admin/authentication/setup/ /x/../ghost/ /ghost/api/content/../../admin/; do
  code=$(curl --path-as-is --silent --show-error -o /dev/null -w '%{http_code}' -H 'Host: blog.example.com' "http://127.0.0.1:8080$path")
  [[ "$code" == 404 ]] || { echo "Admin route escaped the public proxy: $path ($code)" >&2; exit 1; }
done
code=$(curl --silent --show-error -o /dev/null -w '%{http_code}' -H 'Host: blog.example.com' 'http://127.0.0.1:8080/ghost/api/content/posts/?key=invalid')
[[ "$code" == 401 ]] || { echo "Content API should require its key, got HTTP $code." >&2; exit 1; }
curl --fail --silent --show-error -H 'Host: ghost-admin.example.com' http://127.0.0.1:8081/ghost/ >/dev/null
compose exec -T db sh <<'SH'
export MYSQL_PWD="$MYSQL_PASSWORD"
exec mysql -u ghost ghost -e 'CREATE TABLE deployment_smoke (value INT); INSERT INTO deployment_smoke VALUES (42);'
SH
compose exec -T --user node ghost sh -c 'printf persistence > /var/lib/ghost/content/deployment-smoke'
compose down
compose up -d --wait --wait-timeout 300
result=$(compose exec -T db sh <<'SH'
export MYSQL_PWD="$MYSQL_PASSWORD"
exec mysql -u ghost -N ghost -e 'SELECT value FROM deployment_smoke'
SH
)
[[ "$result" == 42 ]]
[[ "$(compose exec -T ghost cat /var/lib/ghost/content/deployment-smoke)" == persistence ]]
echo 'Ghost, proxy access boundaries, and persistence across container recreation passed.'
