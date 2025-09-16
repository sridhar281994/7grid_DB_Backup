#!/usr/bin/env bash
set -euo pipefail

# Ensure backup dir exists
mkdir -p db/backups

# Timestamp for filename
TS=$(date +"%Y%m%d_%H%M%S")

# Run pg_dump using DATABASE_URL
pg_dump "$DATABASE_URL" > "db/backups/backup_$TS.sql"
