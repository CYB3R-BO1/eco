#!/usr/bin/env bash
# Phase 6 WP7 — Neo4j database dump.
#
# Uses ``neo4j-admin database dump`` against a stopped database. This
# requires running the script INSIDE the Neo4j container (or with
# direct disk access to the data volume). For the live container
# workflow, prefer ``docker compose exec neo4j neo4j-admin database
# dump neo4j --to-path=/var/lib/neo4j/import``.
#
# CLAUDE.md invariant #6 / WP7 runbook: the GRAPH is rebuilt from
# Postgres event replay as the PRIMARY recovery path. This dump is a
# fast-restore shortcut, not the source of truth.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/lib/neo4j/import}"
DB_NAME="${NEO4J_DATABASE:-neo4j}"

mkdir -p "${BACKUP_DIR}"

echo "[neo4j_backup] dumping ${DB_NAME} to ${BACKUP_DIR}"
neo4j-admin database dump \
  --to-path="${BACKUP_DIR}" \
  --overwrite-destination \
  "${DB_NAME}"

echo "[neo4j_backup] dump complete: $(ls -la "${BACKUP_DIR}/${DB_NAME}.dump" 2>/dev/null || echo missing)"
