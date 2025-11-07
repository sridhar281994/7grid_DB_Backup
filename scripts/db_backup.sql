#!/bin/bash
set -e

echo "Starting PostgreSQL backup..."

# Create directory if not exists
mkdir -p backup/pgdump

# File name format: backup_YYYYMMDD_HHMM.sql
BACKUP_FILE="backup/pgdump/backup_$(date +%Y%m%d_%H%M).sql"

# Run pg_dump
pg_dump "$DATABASE_URL" -Fc -f "$BACKUP_FILE"

echo "Backup saved to $BACKUP_FILE"
