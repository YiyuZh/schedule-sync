#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apps/schedule-sync}"

cd "${APP_DIR}"

if [ ! -f ".env" ]; then
  echo "[schedule-sync] .env not found; copy .env.example and edit production values first" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

require_not_placeholder() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "${value}" ] || [[ "${value}" == *"replace-with"* ]] || [[ "${value}" == *"sync.example.com"* ]] || [[ "${value}" == *"dev-only-change-me"* ]]; then
    echo "[schedule-sync] ${name} is empty or still uses a placeholder: ${value}" >&2
    exit 1
  fi
}

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

echo "[schedule-sync] pulling latest code"
git pull --rebase

echo "[schedule-sync] validating compose config"
docker compose config >/dev/null

echo "[schedule-sync] rebuilding containers"
docker compose up -d --build
docker compose ps

echo "[schedule-sync] health check"
curl -fsS "http://127.0.0.1:${SCHEDULE_SYNC_PREVIEW_PORT:-18130}/api/health"
echo
