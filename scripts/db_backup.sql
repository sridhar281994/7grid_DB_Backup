#!/bin/bash
set -e

echo "Starting PostgreSQL backup using Docker container..."

mkdir -p backup/pgdump

BACKUP_FILE="backup/pgdump/backup_$(date +%Y%m%d_%H%M).sql"

# Use the pg_dump inside the container (version 18)
pg_dump "$DATABASE_URL" -Fc -f "$BACKUP_FILE"

echo "Backup completed successfully: $BACKUP_FILE"
