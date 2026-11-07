#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "Starting the ShopLite stack"
docker compose up -d --build

echo "Waiting for ${BASE_URL}/readyz"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL}/readyz" >/dev/null; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "$ready" -ne 1 ]]; then
  echo "readyz did not become available" >&2
  docker compose ps >&2 || true
  docker compose logs --tail 40 catalog-api >&2 || true
  exit 1
fi

echo "Placing an order"
order_json="$(curl -fsS -X POST "${BASE_URL}/orders" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "quantity": 1}')"
order_id="$(printf '%s' "$order_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
echo "Created order ${order_id}"

for _ in $(seq 1 40); do
  status="$(curl -fsS "${BASE_URL}/orders/${order_id}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  echo "order ${order_id} status=${status}"
  if [[ "$status" == "COMPLETED" ]]; then
    echo "Smoke test passed"
    exit 0
  fi
  if [[ "$status" == "FAILED" ]]; then
    echo "order ${order_id} failed" >&2
    exit 1
  fi
  sleep 1
done

echo "order ${order_id} did not become COMPLETED in time" >&2
exit 1
