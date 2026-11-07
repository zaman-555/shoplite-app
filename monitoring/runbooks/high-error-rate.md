# HighErrorRate

HTTP 5xx responses are more than 5 percent of ShopLite traffic for 5 minutes.

1. Open Grafana → **ShopLite — Golden Signals** → **HTTP 5xx error rate**.
2. In the latency panel, enable exemplars and open the trace for a 5xx sample. Tempo shows the API span.
3. In Loki, query `{namespace="shoplite"} | json | level="ERROR"` and use the `trace_id` field. The derived field opens the same Tempo trace.
4. Check `CHAOS_ERROR_RATE` on the catalog-api ConfigMap. A value above 0 injects HTTP 500 on `POST /orders`.
5. If the errors are real, read the API log `message` for the failing route and fix that handler. The order is not saved when the injected fault runs before the insert.
