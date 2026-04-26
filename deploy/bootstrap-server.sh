#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apps/schedule-sync}"
SHARED_NETWORK="${SHARED_CADDY_NETWORK:-shared_gateway}"

echo "[schedule-sync] app dir: ${APP_DIR}"
cd "${APP_DIR}"

if [ ! -f ".env" ]; then
  echo "[schedule-sync] .env not found, copying .env.example"
  cp .env.example .env
  echo "[schedule-sync] please edit ${APP_DIR}/.env before production use"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a
SHARED_NETWORK="${SHARED_CADDY_NETWORK:-$SHARED_NETWORK}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[schedule-sync] missing command: $1" >&2
    exit 1
  }
}

require_not_placeholder() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "${value}" ] || [[ "${value}" == *"replace-with"* ]] || [[ "${value}" == *"sync.example.com"* ]] || [[ "${value}" == *"dev-only-change-me"* ]]; then
    echo "[schedule-sync] ${name} is empty or still uses a placeholder: ${value}" >&2
    exit 1
  fi
}

require_command docker
require_command curl
require_not_placeholder APP_BASE_URL
require_not_placeholder SCHEDULE_SYNC_DOMAIN
require_not_placeholder POSTGRES_PASSWORD
require_not_placeholder DATABASE_URL
require_not_placeholder JWT_SECRET
require_not_placeholder ADMIN_EMAIL
require_not_placeholder ADMIN_PASSWORD_HASH

EXPECTED_POSTGRES_USER="autsky"
LEGACY_POSTGRES_USER="autsky6666@gmail.com"

if [ "${POSTGRES_USER:-}" != "${EXPECTED_POSTGRES_USER}" ]; then
  echo "[schedule-sync] POSTGRES_USER must be ${EXPECTED_POSTGRES_USER}; current value: ${POSTGRES_USER:-<empty>}" >&2
  exit 1
fi

if [[ "${DATABASE_URL}" == *"schedule_sync:"* ]]; then
  echo "[schedule-sync] DATABASE_URL still uses old user schedule_sync; use ${EXPECTED_POSTGRES_USER} instead" >&2
  exit 1
fi

if [[ "${DATABASE_URL}" == *"${LEGACY_POSTGRES_USER}"* ]] || [[ "${DATABASE_URL}" == *"autsky6666%40gmail.com"* ]]; then
  echo "[schedule-sync] DATABASE_URL still uses old email user ${LEGACY_POSTGRES_USER}; use ${EXPECTED_POSTGRES_USER} instead" >&2
  exit 1
fi

if [[ "${DATABASE_URL}" != *"://${EXPECTED_POSTGRES_USER}:"* ]]; then
  echo "[schedule-sync] DATABASE_URL must use user ${EXPECTED_POSTGRES_USER}" >&2
  exit 1
fi

echo "[schedule-sync] ensuring shared Docker network: ${SHARED_NETWORK}"
docker network inspect "${SHARED_NETWORK}" >/dev/null 2>&1 || docker network create "${SHARED_NETWORK}"

echo "[schedule-sync] validating compose config"
docker compose config >/dev/null

echo "[schedule-sync] building and starting containers"
docker compose up -d --build

echo "[schedule-sync] compose status"
docker compose ps

echo "[schedule-sync] preview health check"
curl -fsS "http://127.0.0.1:${SCHEDULE_SYNC_PREVIEW_PORT:-18130}/api/health"
echo

echo "[schedule-sync] next: add deploy/caddy.schedule-sync.example block for schedule-sync.zenithy.art to /opt/apps/hiremate/Caddyfile and reload hiremate-caddy"
