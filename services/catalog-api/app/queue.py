import json
import logging

import redis

logger = logging.getLogger("catalog-api")

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
            socket_timeout=2,
        )
        self.client.ping()

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def ping(self) -> None:
        self._client().ping()

    def enqueue(self, payload: dict) -> None:
        self._client().rpush(ORDERS_QUEUE_KEY, json.dumps(payload))
        logger.info("enqueued order %s", payload.get("order_id"))

    def depth(self) -> int:
        return int(self._client().llen(ORDERS_QUEUE_KEY))

    def _client(self) -> redis.Redis:
        if self.client is None:
            raise RuntimeError("queue is not connected")
        return self.client
