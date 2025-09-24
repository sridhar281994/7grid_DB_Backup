#!/bin/bash
set -e

# Path to your backup file
BACKUP_FILE="backup/db_backup.sql"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "❌ Backup file not found at $BACKUP_FILE"
  exit 1
fi

if [ -z "$DATABASE_URL" ]; then
  echo "❌ DATABASE_URL not set!"
  exit 1
fi

echo "📂 Using backup file: $BACKUP_FILE"
echo "🔄 Restoring into database: $DATABASE_URL"

# Optional: wipe schema first (uncomment if you want a clean restore)
# psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

psql "$DATABASE_URL" < "$BACKUP_FILE"

echo "✅ Restore completed successfully!"
