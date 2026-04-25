#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apps/schedule-sync}"
CONTAINER="${POSTGRES_CONTAINER:-schedule-sync-postgres}"
TARGET_USER="${POSTGRES_USER:-autsky6666@gmail.com}"
POSTGRES_DB="${POSTGRES_DB:-schedule_sync}"

if [ -d "${APP_DIR}" ]; then
  cd "${APP_DIR}"
fi

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

TARGET_USER="${POSTGRES_USER:-autsky6666@gmail.com}"
POSTGRES_DB="${POSTGRES_DB:-schedule_sync}"

if [ -z "${POSTGRES_PASSWORD:-}" ] || [[ "${POSTGRES_PASSWORD}" == *"replace-with"* ]]; then
  echo "[schedule-sync] ERROR: POSTGRES_PASSWORD is empty or still a placeholder in .env"
  exit 1
fi

echo "[schedule-sync] target postgres user: ${TARGET_USER}"
echo "[schedule-sync] target postgres database: ${POSTGRES_DB}"

ADMIN_USER=""
for candidate in "${TARGET_USER}" "schedule_sync" "postgres"; do
  if docker exec "${CONTAINER}" psql -U "${candidate}" -d postgres -tAc "select 1" >/dev/null 2>&1; then
    ADMIN_USER="${candidate}"
    break
  fi
done

if [ -z "${ADMIN_USER}" ]; then
  echo "[schedule-sync] ERROR: cannot connect to postgres as ${TARGET_USER}, schedule_sync, or postgres"
  echo "[schedule-sync] Check docker compose logs postgres --tail=200"
  exit 1
fi

echo "[schedule-sync] using admin role: ${ADMIN_USER}"

docker exec -i "${CONTAINER}" psql \
  -U "${ADMIN_USER}" \
  -d postgres \
  -v ON_ERROR_STOP=1 \
  -v target_user="${TARGET_USER}" \
  -v target_password="${POSTGRES_PASSWORD}" \
  -v target_db="${POSTGRES_DB}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'target_user', :'target_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'target_user') \gexec

SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'target_user', :'target_password') \gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'target_db', :'target_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'target_db') \gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'target_db', :'target_user') \gexec
SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'target_db', :'target_user') \gexec
SQL

docker exec -i "${CONTAINER}" psql \
  -U "${ADMIN_USER}" \
  -d "${POSTGRES_DB}" \
  -v ON_ERROR_STOP=1 \
  -v target_user="${TARGET_USER}" <<'SQL'
SELECT format('ALTER SCHEMA public OWNER TO %I', :'target_user') \gexec
SELECT format('GRANT ALL PRIVILEGES ON SCHEMA public TO %I', :'target_user') \gexec
SELECT format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO %I', :'target_user') \gexec
SELECT format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO %I', :'target_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO %I', :'target_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO %I', :'target_user') \gexec

SELECT format('ALTER TABLE %I.%I OWNER TO %I', schemaname, tablename, :'target_user')
FROM pg_tables
WHERE schemaname = 'public' \gexec

SELECT format('ALTER SEQUENCE %I.%I OWNER TO %I', sequence_schema, sequence_name, :'target_user')
FROM information_schema.sequences
WHERE sequence_schema = 'public' \gexec

SELECT format('ALTER VIEW %I.%I OWNER TO %I', table_schema, table_name, :'target_user')
FROM information_schema.views
WHERE table_schema = 'public' \gexec
SQL

ENCODED_USER="${TARGET_USER//@/%40}"

echo
echo "[schedule-sync] role/database ensured."
echo "[schedule-sync] Make sure .env uses this DATABASE_URL form:"
echo "DATABASE_URL=postgresql+psycopg://${ENCODED_USER}:<URL_ENCODED_POSTGRES_PASSWORD>@postgres:5432/${POSTGRES_DB}"
echo
echo "[schedule-sync] If your password contains special URL characters such as @ # : / ? &, URL-encode it in DATABASE_URL."
echo "[schedule-sync] Then restart API:"
echo "docker compose up -d api"
