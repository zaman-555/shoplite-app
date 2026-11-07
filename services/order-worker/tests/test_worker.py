import json
import logging
import signal
import threading

import pytest

from config import Settings
from db import PostgresDatabase
from logging_config import JsonFormatter, trace_id_var
from orders_queue import ORDERS_QUEUE_KEY, RedisQueue, parse_message
from worker import leaked_orders, make_signal_handler, process_message, run_loop


class FakeDB:
    def __init__(self):
        self.orders = {}

    def add(self, order_id, stock=5, quantity=1, status="PENDING"):
        self.orders[order_id] = {
            "status": status,
            "stock": stock,
            "quantity": quantity,
        }

    def claim_order(self, order_id):
        order = self.orders.get(order_id)
        if order is None or order["status"] != "PENDING":
            return False
        order["status"] = "PROCESSING"
        return True

    def finish_order(self, order_id):
        order = self.orders[order_id]
        if order["stock"] < order["quantity"]:
            order["status"] = "FAILED"
            return "FAILED"
        order["stock"] -= order["quantity"]
        order["status"] = "COMPLETED"
        return "COMPLETED"

    def mark_failed(self, order_id):
        self.orders[order_id]["status"] = "FAILED"


class BoomDB(FakeDB):
    def finish_order(self, order_id):
        raise RuntimeError("database update failed")


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, rows):
        self.rows = list(rows)
        self.statements = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.statements.append(normalized)
        if "pg_sleep" in normalized:
            return FakeCursor(None)
        row = self.rows.pop(0) if self.rows else None
        return FakeCursor(row)

    def commit(self):
        self.statements.append("COMMIT")


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def connection(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRedis:
    def __init__(self):
        self.ops = []

    def lpush(self, key, value):
        self.ops.append(("lpush", key, value))

    def blpop(self, key, timeout=0):
        self.ops.append(("blpop", key, timeout))
        return None


class ScriptedQueue:
    def __init__(self, messages):
        self.messages = list(messages)
        self.requeued = []

    def dequeue(self, timeout):
        if not self.messages:
            return None
        return self.messages.pop(0)

    def requeue(self, raw):
        self.requeued.append(raw)


def test_process_message_completes_pending_order_after_simulated_delay():
    db = FakeDB()
    db.add(4, stock=5, quantity=2)
    delays = []
    status = process_message(
        db,
        '{"order_id": 4, "trace_id": "trace-4"}',
        Settings(),
        sleeper=delays.append,
        uniform=lambda low, high: 1.25,
    )
    assert status == "COMPLETED"
    assert delays == [1.25]
    assert db.orders[4]["status"] == "COMPLETED"
    assert db.orders[4]["stock"] == 3


def test_simulated_delay_is_between_one_and_two_seconds():
    db = FakeDB()
    db.add(1)
    delays = []
    process_message(db, '{"order_id": 1, "trace_id": "t"}', Settings(), sleeper=delays.append)
    assert len(delays) == 1
    assert 1.0 <= delays[0] <= 2.0


def test_insufficient_stock_marks_order_failed():
    db = FakeDB()
    db.add(1, stock=0, quantity=2)
    status = process_message(
        db,
        "1",
        Settings(),
        sleeper=lambda seconds: None,
        uniform=lambda low, high: 1,
    )
    assert status == "FAILED"
    assert db.orders[1]["status"] == "FAILED"


def test_processing_exception_marks_order_failed():
    db = BoomDB()
    db.add(8)
    status = process_message(
        db,
        '{"order_id": 8, "trace_id": "t"}',
        Settings(),
        sleeper=lambda seconds: None,
    )
    assert status == "FAILED"
    assert db.orders[8]["status"] == "FAILED"


def test_invalid_message_is_discarded():
    db = FakeDB()
    status = process_message(db, "not-an-order", Settings(), sleeper=lambda seconds: None)
    assert status is None
    assert db.orders == {}


def test_memory_leak_retains_every_processed_order():
    leaked_orders.clear()
    db = FakeDB()
    db.add(1)
    db.add(2)
    settings = Settings(chaos_memory_leak=True)
    raw_messages = [
        '{"order_id": 1, "trace_id": "a"}',
        '{"order_id": 2, "trace_id": "b"}',
    ]
    for raw in raw_messages:
        process_message(db, raw, settings, sleeper=lambda seconds: None)
    assert [item["order_id"] for item in leaked_orders] == [1, 2]
    assert all(len(item["padding"]) == 64 * 1024 for item in leaked_orders)


def test_memory_leak_disabled_by_default():
    leaked_orders.clear()
    db = FakeDB()
    db.add(1)
    process_message(
        db,
        '{"order_id": 1, "trace_id": "a"}',
        Settings(),
        sleeper=lambda seconds: None,
    )
    assert leaked_orders == []


def test_slow_db_runs_pg_sleep_before_each_update():
    conn = FakeConn(rows=[{"id": 3, "product_id": 9, "quantity": 2}])
    db = PostgresDatabase("postgresql://example", chaos_slow_db=True)
    db.pool = FakePool(conn)

    status = db.finish_order(3)

    assert status == "COMPLETED"
    assert conn.statements[0] == "SELECT pg_sleep(2)"
    assert "COMPLETED" in conn.statements[1]
    assert "products.stock >= orders.quantity" in conn.statements[1]
    assert conn.statements[2] == "SELECT pg_sleep(2)"
    assert conn.statements[3].startswith("UPDATE products")
    assert "pg_sleep" not in conn.statements[1]


def test_slow_db_runs_pg_sleep_before_failure_update():
    conn = FakeConn(rows=[None])
    db = PostgresDatabase("postgresql://example", chaos_slow_db=True)
    db.pool = FakePool(conn)

    status = db.finish_order(3)

    assert status == "FAILED"
    assert conn.statements[0] == "SELECT pg_sleep(2)"
    assert "COMPLETED" in conn.statements[1]
    assert conn.statements[2] == "SELECT pg_sleep(2)"
    assert "FAILED" in conn.statements[3]


def test_slow_db_disabled_does_not_sleep():
    conn = FakeConn(rows=[{"id": 1}])
    db = PostgresDatabase("postgresql://example", chaos_slow_db=False)
    db.pool = FakePool(conn)

    assert db.claim_order(1) is True
    assert len(conn.statements) == 2
    assert "pg_sleep" not in conn.statements[0]
    assert "PROCESSING" in conn.statements[0]
    assert conn.statements[1] == "COMMIT"


def test_chaos_flags_default_off(monkeypatch):
    monkeypatch.delenv("CHAOS_MEMORY_LEAK", raising=False)
    monkeypatch.delenv("CHAOS_SLOW_DB", raising=False)
    settings = Settings.from_env()
    assert settings.chaos_memory_leak is False
    assert settings.chaos_slow_db is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_chaos_flags_accept_truthy_values(monkeypatch, value):
    monkeypatch.setenv("CHAOS_MEMORY_LEAK", value)
    monkeypatch.setenv("CHAOS_SLOW_DB", value)
    settings = Settings.from_env()
    assert settings.chaos_memory_leak is True
    assert settings.chaos_slow_db is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_chaos_flags_reject_falsy_values(monkeypatch, value):
    monkeypatch.setenv("CHAOS_MEMORY_LEAK", value)
    monkeypatch.setenv("CHAOS_SLOW_DB", value)
    settings = Settings.from_env()
    assert settings.chaos_memory_leak is False
    assert settings.chaos_slow_db is False


def test_sigterm_requests_shutdown():
    shutdown = threading.Event()
    make_signal_handler(shutdown)(signal.SIGTERM, None)
    assert shutdown.is_set()


def test_run_loop_stops_when_shutdown_is_already_set():
    handled = []
    shutdown = threading.Event()
    shutdown.set()
    run_loop(ScriptedQueue(["msg"]), handled.append, shutdown)
    assert handled == []


def test_run_loop_requeues_message_popped_during_shutdown():
    shutdown = threading.Event()
    queue = ScriptedQueue(["msg"])
    original_dequeue = queue.dequeue

    def dequeue(timeout):
        shutdown.set()
        return original_dequeue(timeout)

    queue.dequeue = dequeue
    handled = []
    run_loop(queue, handled.append, shutdown)
    assert handled == []
    assert queue.requeued == ["msg"]


def test_requeue_uses_orders_pending_list():
    queue = RedisQueue("redis://localhost:6379/0")
    fake = FakeRedis()
    queue.client = fake
    queue.requeue('{"order_id": 1}')
    assert fake.ops == [("lpush", ORDERS_QUEUE_KEY, '{"order_id": 1}')]
    assert ORDERS_QUEUE_KEY == "orders:pending"


def test_parse_message_accepts_json_and_plain_ids():
    assert parse_message('{"order_id": 5, "trace_id": "abc"}') == (5, "abc")
    assert parse_message("5") == (5, "-")
    assert parse_message("15") == (15, "-")


def test_json_log_fields(monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "order-worker")
    token = trace_id_var.set("trace-worker")
    try:
        record = logging.LogRecord(
            name="order-worker",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="processed",
            args=(),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        trace_id_var.reset(token)

    assert list(payload) == ["timestamp", "level", "service", "message", "trace_id"]
    assert payload["service"] == "order-worker"
    assert payload["message"] == "processed"
    assert payload["trace_id"] == "trace-worker"
