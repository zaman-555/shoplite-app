# HighLatency

p95 `http_request_duration_seconds` is above 1 second for 5 minutes.

1. Open **ShopLite — Golden Signals** → **Request latency by route**. Compare p95 with p50 for the slow route.
2. Click an exemplar on the latency series. The Tempo trace shows whether time is in `postgres create_order`, `redis enqueue`, or the HTTP span.
3. In Loki, open a log line from `catalog-api` with that `trace_id`. `injecting chaos latency` means `CHAOS_LATENCY_MS` is on.
4. If the database span is the slow one, check Postgres CPU and that the volume is not full (see NodeDiskFilling).
