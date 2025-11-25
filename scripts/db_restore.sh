#!/bin/bash
set -e

BACKUP_FILE="$1"

if [ -z "$DATABASE_URL" ]; then
  echo "DATABASE_URL not set"
  exit 1
fi

if [ -z "$BACKUP_FILE" ]; then
  echo "No backup file provided"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file not found at $BACKUP_FILE"
  exit 1
fi

echo "Starting PostgreSQL restore from $BACKUP_FILE..."

# Drop existing schema & restore cleanly
pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname="$DATABASE_URL" "$BACKUP_FILE"

echo "Restore completed successfully."
