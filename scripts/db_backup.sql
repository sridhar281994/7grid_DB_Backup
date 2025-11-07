#!/bin/bash
set -e

echo "Starting PostgreSQL backup..."

mkdir -p backup/pgdump

# Timestamped backup filename
BACKUP_FILE="backup/pgdump/backup_$(date +%Y%m%d_%H%M).sql"

# Run pg_dump using PostgreSQL 17 client
pg_dump "$DATABASE_URL" -Fc -f "$BACKUP_FILE"

echo "Backup saved to $BACKUP_FILE"
