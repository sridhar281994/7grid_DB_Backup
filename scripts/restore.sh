#!/bin/bash
set -e

# Find the latest backup file in backups/ folder
BACKUP_FILE=$(ls -t backups/db_backup_*.sql | head -n 1)

if [ -z "$BACKUP_FILE" ]; then
  echo "❌ No backup file found in backups/ folder!"
  exit 1
fi

if [ -z "$DATABASE_URL" ]; then
  echo "❌ DATABASE_URL not set!"
  exit 1
fi

echo "📂 Using backup file: $BACKUP_FILE"
echo "🔄 Restoring into database: $DATABASE_URL"

# Optional: wipe existing schema first (uncomment if needed)
# psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Restore backup
psql "$DATABASE_URL" < "$BACKUP_FILE"

echo "✅ Restore completed successfully!"
