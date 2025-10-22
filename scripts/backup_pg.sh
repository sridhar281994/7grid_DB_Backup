#!/bin/bash
set -e

BACKUP_DIR="7grid_DB_Backup/backup"
TIMESTAMP=$(date -u +"%Y-%m-%d_%H-%M-%S")
DUMP_FILE="${BACKUP_DIR}/pg_backup_${TIMESTAMP}.sql"

if [ -z "$DATABASE_URL" ]; then
  echo "DATABASE_URL not set"
  exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "Backing up database..."
pg_dump "$DATABASE_URL" -Fc -f "$DUMP_FILE"
echo "Created: $DUMP_FILE"

# keep last 7
cd "$BACKUP_DIR"
ls -1t pg_backup_*.sql | tail -n +8 | xargs -r rm --
cd ../..

git config user.name "github-backup-bot"
git config user.email "bot@github.com"

git add "$BACKUP_DIR"
git commit -m "Daily backup $(date -u +"%Y-%m-%d %H:%M:%S")" || echo "No changes"
git push || echo "Nothing to push"
