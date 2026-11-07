import json
import logging

import redis

logger = logging.getLogger("order-worker")

ORDERS_QUEUE_KEY = "orders:pending"


class RedisQueue:
    def __init__(self, url: str):
        self.url = url
        self.client: redis.Redis | None = None

    def connect(self) -> None:
        if self.client is not None:
            return
        self.client = redis.Redis.from_url(
            self.url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )
        self.client.ping()

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def dequeue(self, timeout: int) -> str | None:
        item = self._client().blpop(ORDERS_QUEUE_KEY, timeout=timeout)
        if item is None:
            return None
        return item[1]

    def requeue(self, raw: str) -> None:
        self._client().lpush(ORDERS_QUEUE_KEY, raw)
        logger.info("requeued order message")

    def depth(self) -> int:
        return int(self._client().llen(ORDERS_QUEUE_KEY))

    def _client(self) -> redis.Redis:
        if self.client is None:
            raise RuntimeError("queue is not connected")
        return self.client


def trace_carrier(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict) and data.get("traceparent"):
        return {"traceparent": str(data["traceparent"])}
    return {}


def parse_message(raw: str) -> tuple[int, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return int(raw), "-"
    if isinstance(data, int):
        return data, "-"
    if isinstance(data, dict) and "order_id" in data:
        return int(data["order_id"]), str(data.get("trace_id") or "-")
    raise ValueError(f"unrecognized queue message: {raw}")
