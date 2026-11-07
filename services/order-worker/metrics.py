from prometheus_client import Counter, Gauge, Histogram

ORDERS_PROCESSED = Counter(
    "orders_processed_total",
    "Orders finished by the worker.",
    labelnames=("status",),
)

ORDER_PROCESSING_SECONDS = Histogram(
    "order_processing_duration_seconds",
    "Time spent processing one order, including the simulated delay.",
    buckets=(0.5, 1, 1.5, 2, 3, 5, 8, 13),
)

ORDERS_IN_PROGRESS = Gauge(
    "orders_in_progress",
    "Orders currently being processed.",
)
