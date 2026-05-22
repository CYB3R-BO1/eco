#!/usr/bin/env bash
# Phase 6 WP7 — Neo4j restore from a dump file.
#
# Must run inside a container with the Neo4j service stopped. The
# operator runbook ``docs/runbooks/backup-restore.md`` walks through
# the docker-compose-based variant.

set -euo pipefail

DUMP="${1:?usage: neo4j_restore.sh <dump-file>}"
DB_NAME="${NEO4J_DATABASE:-neo4j}"

if [[ ! -f "${DUMP}" ]]; then
  echo "[neo4j_restore] dump not found: ${DUMP}" >&2
  exit 2
fi

echo "[neo4j_restore] restoring ${DB_NAME} from ${DUMP}"
neo4j-admin database load \
  --from-path="$(dirname "${DUMP}")" \
  --overwrite-destination=true \
  "${DB_NAME}"

echo "[neo4j_restore] restore complete — start the database to verify"
