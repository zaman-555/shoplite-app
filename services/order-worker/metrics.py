from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled by the catalog API.",
    labelnames=("method", "route", "status"),
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

ORDERS_CREATED = Counter(
    "orders_created_total",
    "Orders accepted and enqueued by the catalog API.",
)

ORDERS_PROCESSED = Counter(
    "orders_processed_total",
    "Orders finished by the worker.",
    labelnames=("result",),
)

ORDER_QUEUE_DEPTH = Gauge(
    "order_queue_depth",
    "Orders waiting in the Redis list orders:pending.",
)

ORDERS_IN_PROGRESS = Gauge(
    "orders_in_progress",
    "Orders currently being processed.",
)

ORDER_PROCESSING_SECONDS = Histogram(
    "order_processing_seconds",
    "Time spent processing one order.",
    buckets=(0.5, 1, 1.5, 2, 3, 5, 8, 13),
)
