#!/bin/bash
# Nightly logical backup of the ShopLite database.
# Postgres is not published to the host. The dump runs inside the Compose container.
set -euo pipefail

umask 027
mkdir -p /var/backups/shoplite

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="/var/backups/shoplite/shoplite-${stamp}.sql"

docker exec shoplite-postgres-1 pg_dump -U shoplite -d shoplite --no-owner --no-acl > "${dest}"
chmod 640 "${dest}"
echo "wrote ${dest}"
