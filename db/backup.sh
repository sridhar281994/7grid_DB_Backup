#!/bin/bash
set -e
# File name with timestamp
DATE=$(date +%Y-%m-%d_%H-%M)
BACKUP_FILE="db_backup_$DATE.sql"
# Dump database (structure + data)
pg_dump --no-owner --no-privileges "$DATABASE_URL" > "db/$BACKUP_FILE"
echo "Backup created: db/$BACKUP_FILE"
