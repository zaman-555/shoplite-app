import logging
import random
import signal
import threading
import time

from prometheus_client import start_http_server

from config import Settings
from db import PostgresDatabase
from logging_config import setup_logging, trace_id_var
from metrics import ORDER_PROCESSING_SECONDS, ORDERS_IN_PROGRESS, ORDERS_PROCESSED
from orders_queue import RedisQueue, parse_message

logger = logging.getLogger("order-worker")

# Retained on purpose when CHAOS_MEMORY_LEAK is enabled. Never cleared.
leaked_orders: list[dict] = []


def make_signal_handler(shutdown: threading.Event):
    def handle(signum, frame):
        shutdown.set()

    return handle


def process_message(db, raw: str, settings: Settings, sleeper=time.sleep, uniform=random.uniform):
    try:
        order_id, trace_id = parse_message(raw)
    except (TypeError, ValueError) as exc:
        logger.error("discarding invalid queue message: %s", exc)
        return None

    token = trace_id_var.set(trace_id)
    started = time.perf_counter()
    ORDERS_IN_PROGRESS.inc()
    try:
        claimed = db.claim_order(order_id)
        if not claimed:
            logger.info("skipping order %s because it is not pending", order_id)
            return None

        sleeper(uniform(1.0, 2.0))
        status = db.finish_order(order_id)
        if settings.chaos_memory_leak:
            leaked_orders.append(
                {
                    "order_id": order_id,
                    "trace_id": trace_id,
                    "retained_at": time.time(),
                    "padding": "x" * (64 * 1024),
                }
            )
        ORDERS_PROCESSED.labels(status=status).inc()
        ORDER_PROCESSING_SECONDS.observe(time.perf_counter() - started)
        logger.info("order %s %s", order_id, status)
        return status
    except Exception as exc:
        logger.error("order %s failed: %s", order_id, exc)
        try:
            db.mark_failed(order_id)
        except Exception as mark_exc:
            logger.error("could not mark order %s failed: %s", order_id, mark_exc)
        ORDERS_PROCESSED.labels(status="FAILED").inc()
        return "FAILED"
    finally:
        ORDERS_IN_PROGRESS.dec()
        trace_id_var.reset(token)


def run_loop(queue, handle, shutdown: threading.Event) -> None:
    while not shutdown.is_set():
        try:
            raw = queue.dequeue(timeout=1)
        except Exception as exc:
            if shutdown.is_set():
                break
            logger.error("queue read failed: %s", exc)
            if shutdown.wait(1):
                break
            continue
        if raw is None:
            continue
        if shutdown.is_set():
            queue.requeue(raw)
            break
        handle(raw)


def main() -> None:
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    db = PostgresDatabase(settings.database_url, chaos_slow_db=settings.chaos_slow_db)
    queue = RedisQueue(settings.redis_url)
    db.connect()
    db.init_schema()
    queue.connect()
    start_http_server(settings.metrics_port)

    shutdown = threading.Event()
    handler = make_signal_handler(shutdown)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    logger.info(
        "order worker started memory_leak=%s slow_db=%s",
        settings.chaos_memory_leak,
        settings.chaos_slow_db,
    )
    try:
        run_loop(
            queue,
            lambda raw: process_message(db, raw, settings),
            shutdown,
        )
    finally:
        logger.info("order worker stopped")
        queue.close()
        db.close()


if __name__ == "__main__":
    main()
