#!/bin/bash
set -euo pipefail
mkdir -p db/backups
# Add sslmode=require to enforce SSL
pg_dump "$DATABASE_URL?sslmode=require" > "db/backups/backup_$(date +%Y%m%d_%H%M%S).sql"
