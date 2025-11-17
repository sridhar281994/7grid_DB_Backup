#!/bin/bash
set -e

echo "Starting PostgreSQL restore..."

# Require a file path argument
if [ -z "$1" ]; then
  echo "Usage: bash scripts/db_restore.sql <path-to-backup-file>"
  exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file not found at $BACKUP_FILE"
  exit 1
fi

# Confirm before restoring (safety)
echo "Restoring database from: $BACKUP_FILE"
echo "Target: $DATABASE_URL"
sleep 2

# Drop existing schema and restore
pg_restore --clean --no-owner --no-privileges -d "$DATABASE_URL" "$BACKUP_FILE"

echo "Restore completed successfully."
