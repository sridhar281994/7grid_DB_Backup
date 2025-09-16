#!/bin/bash
set -e
# Ensure backups folder exists
mkdir -p backups
# Create filename with timestamp
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
FILE="backups/db_backup_$DATE.sql"
# Run pg_dump with DATABASE_URL from GitHub secret
pg_dump "$DATABASE_URL" > "$FILE"
echo ":white_check_mark: Backup saved to $FILE"
