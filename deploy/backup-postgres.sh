#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/opt/apps/backups/schedule-sync/postgres}"
POSTGRES_USER="${POSTGRES_USER:-autsky6666@gmail.com}"
POSTGRES_DB="${POSTGRES_DB:-schedule_sync}"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

mkdir -p "${BACKUP_ROOT}"
BACKUP_FILE="${BACKUP_ROOT}/schedule_sync_$(date +%F_%H%M%S).sql"

echo "[schedule-sync] dumping ${POSTGRES_DB} to ${BACKUP_FILE}"
docker exec schedule-sync-postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" > "${BACKUP_FILE}"
echo "[schedule-sync] backup complete"
