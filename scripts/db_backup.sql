#!/bin/bash
set -e

echo "Starting PostgreSQL backup..."

mkdir -p backup/pgdump

BACKUP_FILE="backup/pgdump/backup_$(date +%Y%m%d_%H%M).sql"

pg_dump "$DATABASE_URL" -Fc -f "$BACKUP_FILE"

echo "Backup saved to $BACKUP_FILE"
