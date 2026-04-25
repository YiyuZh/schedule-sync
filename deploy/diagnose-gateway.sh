#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-schedule-sync.zenithy.art}"
APP_DIR="${APP_DIR:-/opt/apps/schedule-sync}"
CADDY_CONTAINER="${CADDY_CONTAINER:-hiremate-caddy}"
CADDYFILE_HOST_PATH="${CADDYFILE_HOST_PATH:-/opt/apps/hiremate/Caddyfile}"
SHARED_NETWORK="${SHARED_CADDY_NETWORK:-shared_gateway}"

echo "[schedule-sync] gateway diagnosis for ${DOMAIN}"
echo

echo "== DNS =="
getent ahosts "${DOMAIN}" || true
echo

echo "== schedule-sync compose status =="
if [ -d "${APP_DIR}" ]; then
  cd "${APP_DIR}"
  docker compose ps || true
else
  echo "WARN: ${APP_DIR} not found"
fi
echo

echo "== local API health =="
curl -fsS http://127.0.0.1:18130/api/health || echo "WARN: local API health failed"
echo
echo

echo "== Caddyfile site block =="
if [ -f "${CADDYFILE_HOST_PATH}" ]; then
  grep -n "${DOMAIN}" "${CADDYFILE_HOST_PATH}" || echo "WARN: ${DOMAIN} not found in ${CADDYFILE_HOST_PATH}"
else
  echo "WARN: ${CADDYFILE_HOST_PATH} not found"
fi
echo

echo "== shared Docker network =="
docker network inspect "${SHARED_NETWORK}" --format '{{range $id,$c := .Containers}}{{println $c.Name}}{{end}}' \
  | grep -E "${CADDY_CONTAINER}|schedule-sync-api" || true
echo

echo "== Caddy validate =="
docker exec "${CADDY_CONTAINER}" caddy validate --config /etc/caddy/Caddyfile || true
echo

echo "== Caddy schedule-sync certificate files =="
docker exec "${CADDY_CONTAINER}" sh -lc "find /data/caddy/certificates -iname '*schedule-sync*' -print 2>/dev/null" || true
echo

echo "== HTTPS from server =="
curl -vkI "https://${DOMAIN}/api/health" || true
echo

echo "== recent Caddy logs =="
docker logs "${CADDY_CONTAINER}" --tail=200 2>&1 | grep -Ei "${DOMAIN}|certificate|acme|tls|error|schedule-sync" || true

cat <<'EOF'

If HTTPS fails with tlsv1 alert internal error:
1. Confirm the domain block exists in /opt/apps/hiremate/Caddyfile.
2. Confirm hiremate-caddy and schedule-sync-api are both in shared_gateway.
3. Reload Caddy:
   docker exec hiremate-caddy caddy validate --config /etc/caddy/Caddyfile
   docker exec hiremate-caddy caddy reload --config /etc/caddy/Caddyfile
4. Watch Caddy logs for ACME/certificate errors.
5. Re-test:
   curl -vkI https://schedule-sync.zenithy.art/api/health

If HTTPS works but returns 502 Bad Gateway:
1. Caddy has loaded the site and the certificate is OK.
2. The backend container is not reachable from Caddy.
3. Check:
   cd /opt/apps/schedule-sync
   docker compose ps
   docker compose logs api --tail=200
   curl http://127.0.0.1:18130/api/health
   docker network inspect shared_gateway | grep -E "hiremate-caddy|schedule-sync-api"
4. Fix most common network issue:
   docker network connect shared_gateway schedule-sync-api || true
   docker exec hiremate-caddy caddy reload --config /etc/caddy/Caddyfile
5. Re-test:
   curl -vk https://schedule-sync.zenithy.art/api/health
EOF
