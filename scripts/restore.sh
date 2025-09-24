#!/bin/bash
set -e
BACKUP_FILE="backup/db_backup.sql"
if [ ! -f "$BACKUP_FILE" ]; then
  echo ":x: Backup file not found at $BACKUP_FILE"
  exit 1
fi
if [ -z "$DATABASE_URL" ]; then
  echo ":x: DATABASE_URL not set!"
  exit 1
fi
echo ":open_file_folder: Using backup file: $BACKUP_FILE"
echo ":arrows_counterclockwise: Wiping schema and restoring into database: $DATABASE_URL"
# Wipe the schema before restore
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
# Ignore ownership commands and role errors
sed '/OWNER TO/d;/GRANT/d' "$BACKUP_FILE" | psql "$DATABASE_URL"
echo ":white_check_mark: Restore completed successfully!"
