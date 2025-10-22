#!/bin/bash
set -e

# === CONFIGURATION ===
TIMESTAMP=$(date -u +"%Y-%m-%d_%H-%M-%S")
TMP_DIR=$(mktemp -d)
DB_URL="${DATABASE_URL}"
GITLAB_REPO="${GITLAB_REPO}"
GITLAB_TOKEN="${GITLAB_TOKEN}"

# === VALIDATION ===
if [ -z "$DB_URL" ] || [ -z "$GITLAB_REPO" ] || [ -z "$GITLAB_TOKEN" ]; then
  echo "Error: Missing environment variables."
  echo "Required: DATABASE_URL, GITLAB_REPO, GITLAB_TOKEN"
  exit 1
fi

# === CLONE TARGET REPO ===
echo "Cloning GitLab repo..."
git clone "https://oauth2:${GITLAB_TOKEN}@${GITLAB_REPO}" "$TMP_DIR"
cd "$TMP_DIR"

mkdir -p backup

# === BACKUP DATABASE ===
BACKUP_FILE="backup/pg_backup_${TIMESTAMP}.sql"
echo "Creating database dump: ${BACKUP_FILE}"
pg_dump "$DB_URL" -Fc -f "$BACKUP_FILE"

# === RETENTION POLICY ===
echo "Cleaning up old backups (keeping last 7)..."
cd backup
ls -1t pg_backup_*.sql | tail -n +8 | xargs -r rm --
cd ..

# === COMMIT AND PUSH ===
git config user.email "backup-bot@github.com"
git config user.name "GitHub Backup Bot"

git add backup/
git commit -m "Daily PostgreSQL backup ${TIMESTAMP}" || echo "No changes to commit"
git push origin main

echo "Backup complete and pushed to GitLab."
