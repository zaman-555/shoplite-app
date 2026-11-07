import json
import logging
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.chaos import should_inject_error, should_inject_latency
from app.config import Settings
from app.logging_config import JsonFormatter, trace_id_var
from app.main import create_app
from app.queue import ORDERS_QUEUE_KEY, RedisQueue


class FakeDB:
    def __init__(self):
        self.products = {
            1: {"id": 1, "name": "Wireless Mouse", "price": 24.99, "stock": 100},
            2: {"id": 2, "name": "Notebook", "price": 4.99, "stock": 3},
        }
        self.orders = {}
        self.next_order_id = 1
        self.initialized = False
        self.healthy = True
        self.now = datetime(2026, 11, 6, tzinfo=timezone.utc)

    def connect(self):
        return None

    def close(self):
        return None

    def init_schema(self):
        self.initialized = True

    def ping(self):
        if not self.healthy:
            raise ConnectionError("database unavailable")

    def list_products(self):
        return [dict(product) for product in self.products.values()]

    def get_product(self, product_id):
        product = self.products.get(product_id)
        return dict(product) if product else None

    def create_order(self, product_id, quantity):
        order_id = self.next_order_id
        self.next_order_id += 1
        order = {
            "id": order_id,
            "product_id": product_id,
            "quantity": quantity,
            "status": "PENDING",
            "created_at": self.now,
            "completed_at": None,
        }
        self.orders[order_id] = order
        return dict(order)

    def get_order(self, order_id):
        order = self.orders.get(order_id)
        return dict(order) if order else None

    def mark_failed(self, order_id):
        self.orders[order_id]["status"] = "FAILED"


class FakeQueue:
    def __init__(self):
        self.items = []
        self.healthy = True
        self.fail_enqueue = False

    def connect(self):
        return None

    def close(self):
        return None

    def ping(self):
        if not self.healthy:
            raise ConnectionError("queue unavailable")

    def enqueue(self, payload):
        if self.fail_enqueue:
            raise ConnectionError("redis down")
        self.items.append(payload)


class FakeRedis:
    def __init__(self):
        self.ops = []

    def rpush(self, key, value):
        self.ops.append(("rpush", key, value))


def make_settings(**overrides):
    values = {
        "service_name": "catalog-api",
        "database_url": "postgresql://test",
        "redis_url": "redis://test",
        "chaos_latency_ms": 0,
        "chaos_error_rate": 0.0,
        "log_level": "INFO",
        "port": 8000,
    }
    values.update(overrides)
    return Settings(**values)


def build_app(db, queue, **setting_overrides):
    return create_app(make_settings(**setting_overrides), db, queue)


@pytest.fixture()
def fake_db():
    return FakeDB()


@pytest.fixture()
def fake_queue():
    return FakeQueue()


@pytest.fixture()
def client(fake_db, fake_queue):
    with TestClient(build_app(fake_db, fake_queue)) as test_client:
        yield test_client


def metric_value(text, name):
    for line in text.splitlines():
        if line.startswith(f"{name} "):
            return float(line.split()[-1])
    raise AssertionError(f"{name} not found in metrics")


def test_startup_initializes_database(fake_db, client):
    assert fake_db.initialized is True
    assert client.get("/healthz").status_code == 200


def test_get_products(client):
    response = client.get("/products")
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [1, 2]
    assert body[0]["name"] == "Wireless Mouse"
    assert body[0]["price"] == 24.99
    assert body[0]["stock"] == 100


def test_get_product_by_id(client):
    response = client.get("/products/1")
    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "Wireless Mouse",
        "price": 24.99,
        "stock": 100,
    }


def test_get_product_not_found(client):
    response = client.get("/products/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


def test_post_order_creates_pending_order_and_enqueues(client, fake_queue):
    before = metric_value(client.get("/metrics").text, "orders_created_total")
    response = client.post("/orders", json={"product_id": 1, "quantity": 2})
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["product_id"] == 1
    assert body["quantity"] == 2
    assert body["status"] == "PENDING"
    assert body["completed_at"] is None
    assert fake_queue.items == [{"order_id": 1, "trace_id": response.headers["x-trace-id"]}]
    after = metric_value(client.get("/metrics").text, "orders_created_total")
    assert after == before + 1


def test_get_order_status(client):
    created = client.post("/orders", json={"product_id": 1, "quantity": 2})
    order_id = created.json()["id"]
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"


def test_get_order_not_found(client):
    response = client.get("/orders/404")
    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


def test_post_order_unknown_product(client, fake_queue):
    response = client.post("/orders", json={"product_id": 999, "quantity": 1})
    assert response.status_code == 404
    assert fake_queue.items == []


def test_post_order_rejects_invalid_quantity(client):
    response = client.post("/orders", json={"product_id": 1, "quantity": 0})
    assert response.status_code == 422


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_success(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "queue": "ok"}


def test_readyz_when_database_is_down(client, fake_db):
    fake_db.healthy = False
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "database": "unavailable",
        "queue": "ok",
    }


def test_readyz_when_queue_is_down(client, fake_queue):
    fake_queue.healthy = False
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["queue"] == "unavailable"


def test_metrics_exposes_prometheus_text(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text
    assert "http_request_duration_seconds" in response.text
    assert "orders_created_total" in response.text


def test_trace_id_comes_from_request_header(client):
    response = client.get("/healthz", headers={"X-Request-ID": "trace-123"})
    assert response.headers["x-trace-id"] == "trace-123"


def test_queue_failure_marks_order_failed(fake_db, fake_queue):
    fake_queue.fail_enqueue = True
    with TestClient(build_app(fake_db, fake_queue)) as client:
        response = client.post("/orders", json={"product_id": 1, "quantity": 2})
    assert response.status_code == 503
    assert fake_db.orders[1]["status"] == "FAILED"
    assert fake_queue.items == []


def test_chaos_error_rate_returns_500(monkeypatch, fake_db, fake_queue):
    monkeypatch.setattr("app.main.random.random", lambda: 0.0)
    with TestClient(build_app(fake_db, fake_queue, chaos_error_rate=0.1)) as client:
        response = client.post("/orders", json={"product_id": 1, "quantity": 2})
    assert response.status_code == 500
    assert response.json()["detail"] == "injected fault"
    assert fake_db.orders == {}
    assert fake_queue.items == []


def test_chaos_error_rate_disabled_by_default(monkeypatch, client, fake_queue):
    monkeypatch.setattr("app.main.random.random", lambda: 0.0)
    response = client.post("/orders", json={"product_id": 1, "quantity": 1})
    assert response.status_code == 201
    assert len(fake_queue.items) == 1


def test_chaos_latency_delays_about_thirty_percent(monkeypatch, fake_db, fake_queue):
    monkeypatch.setattr("app.main.random.random", lambda: 0.29)
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("app.main.asyncio.sleep", fake_sleep)
    with TestClient(build_app(fake_db, fake_queue, chaos_latency_ms=250)) as client:
        response = client.get("/products/1")
    assert response.status_code == 200
    assert slept == [0.25]


def test_chaos_latency_skips_the_other_seventy_percent(monkeypatch, fake_db, fake_queue):
    monkeypatch.setattr("app.main.random.random", lambda: 0.30)
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("app.main.asyncio.sleep", fake_sleep)
    with TestClient(build_app(fake_db, fake_queue, chaos_latency_ms=250)) as client:
        response = client.get("/products/1")
    assert response.status_code == 200
    assert slept == []


def test_chaos_flags_default_off(monkeypatch):
    monkeypatch.delenv("CHAOS_LATENCY_MS", raising=False)
    monkeypatch.delenv("CHAOS_ERROR_RATE", raising=False)
    settings = Settings.from_env()
    assert settings.chaos_latency_ms == 0
    assert settings.chaos_error_rate == 0.0
    assert should_inject_latency(0, 0.0) is False
    assert should_inject_error(0.0, 0.0) is False
    assert should_inject_latency(100, 0.29) is True
    assert should_inject_latency(100, 0.30) is False
    assert should_inject_error(0.1, 0.09) is True
    assert should_inject_error(0.1, 0.1) is False


def test_json_log_fields(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "catalog-api")
    token = trace_id_var.set("trace-abc")
    try:
        record = logging.LogRecord(
            name="catalog-api",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        trace_id_var.reset(token)

    assert list(payload) == ["timestamp", "level", "service", "message", "trace_id"]
    assert payload["level"] == "INFO"
    assert payload["service"] == "catalog-api"
    assert payload["message"] == "hello"
    assert payload["trace_id"] == "trace-abc"
    assert payload["timestamp"].endswith("Z")


def test_enqueue_uses_orders_pending_list():
    queue = RedisQueue("redis://localhost:6379/0")
    fake = FakeRedis()
    queue.client = fake
    queue.enqueue({"order_id": 7, "trace_id": "abc"})
    command, key, raw = fake.ops[0]
    assert command == "rpush"
    assert key == ORDERS_QUEUE_KEY == "orders:pending"
    assert json.loads(raw) == {"order_id": 7, "trace_id": "abc"}
