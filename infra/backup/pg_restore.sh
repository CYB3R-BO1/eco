#!/usr/bin/env bash
# Phase 6 WP7 — Postgres restore from a custom-format dump.
#
# By default refuses to restore into a non-empty database. Pass --force
# to override (typically because you're restoring into a freshly-created
# instance and want to overwrite the bootstrap schema).
#
# Required env: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_DB,
# POSTGRES_PASSWORD.
# Required arg: path to .dump file.

set -euo pipefail

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
  shift
fi

DUMP="${1:?usage: pg_restore.sh [--force] <dump-file>}"
if [[ ! -f "${DUMP}" ]]; then
  echo "[pg_restore] dump not found: ${DUMP}" >&2
  exit 2
fi

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
COMMON_FLAGS=(
  --host="${POSTGRES_HOST:?}"
  --port="${POSTGRES_PORT:-5432}"
  --username="${POSTGRES_USER:?}"
  --dbname="${POSTGRES_DB:?}"
)

if [[ "${FORCE}" -eq 0 ]]; then
  # Refuse to restore into a populated DB unless --force is set.
  TABLE_COUNT="$(psql "${COMMON_FLAGS[@]}" -At -c "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
  if [[ "${TABLE_COUNT}" -gt 0 ]]; then
    echo "[pg_restore] refusing — target DB has ${TABLE_COUNT} public tables. Re-run with --force." >&2
    exit 3
  fi
fi

echo "[pg_restore] restoring from ${DUMP}"
pg_restore \
  "${COMMON_FLAGS[@]}" \
  --no-owner \
  --no-acl \
  --clean \
  --if-exists \
  --jobs=4 \
  "${DUMP}"

echo "[pg_restore] restore complete"
