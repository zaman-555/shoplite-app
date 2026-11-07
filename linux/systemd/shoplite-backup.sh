#!/bin/bash
# Nightly logical backup of the ShopLite database.
# On the Kubernetes control plane this dumps the postgres Deployment in the
# shoplite namespace. On a single Compose host it dumps shoplite-postgres-1.
set -euo pipefail

umask 027
mkdir -p /var/backups/shoplite

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dest="/var/backups/shoplite/shoplite-${stamp}.sql"

if command -v k3s >/dev/null 2>&1 && k3s kubectl -n shoplite get deploy/postgres >/dev/null 2>&1; then
  k3s kubectl -n shoplite exec deploy/postgres -- pg_dump -U shoplite shoplite > "${dest}"
elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx 'shoplite-postgres-1'; then
  docker exec shoplite-postgres-1 pg_dump -U shoplite -d shoplite --no-owner --no-acl > "${dest}"
else
  echo "ShopLite Postgres is not deployed yet; nothing to back up"
  exit 0
fi

chmod 640 "${dest}"
echo "wrote ${dest}"
