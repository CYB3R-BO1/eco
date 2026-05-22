#!/usr/bin/env bash
# Phase 6 WP7 — Postgres logical backup.
#
# Writes a custom-format dump to ${BACKUP_DIR}/postgres-${timestamp}.dump.
# Custom format because it supports pg_restore --jobs N for parallel
# restore and selective table restore — both useful in incident response.
#
# Required env: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_DB,
# POSTGRES_PASSWORD. BACKUP_DIR defaults to ./backups.
#
# Per CLAUDE.md invariant #14: the dump contains the live data tier
# verbatim. Treat the dump file like the database itself — same
# encryption-at-rest, same access controls.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/postgres-${TIMESTAMP}.dump"

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

echo "[pg_backup] dumping to ${TARGET}"
pg_dump \
  --host="${POSTGRES_HOST:?}" \
  --port="${POSTGRES_PORT:-5432}" \
  --username="${POSTGRES_USER:?}" \
  --dbname="${POSTGRES_DB:?}" \
  --format=custom \
  --compress=6 \
  --no-owner \
  --no-acl \
  --file="${TARGET}"

echo "[pg_backup] dump complete: $(du -h "${TARGET}" | cut -f1)"
