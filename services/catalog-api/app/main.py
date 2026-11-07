import asyncio
import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from app.chaos import should_inject_error, should_inject_latency
from app.config import Settings
from app.db import PostgresDatabase
from app.logging_config import setup_logging, trace_id_var
from app.metrics import ORDER_QUEUE_DEPTH, ORDERS_CREATED
from app.middleware import ObservabilityMiddleware
from app.queue import RedisQueue
from app.tracing import inject_traceparent, setup_tracing, tracer

logger = logging.getLogger("catalog-api")


class OrderRequest(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class Product(BaseModel):
    id: int
    name: str
    price: float
    stock: int


class Order(BaseModel):
    id: int
    product_id: int
    quantity: int
    status: str
    created_at: datetime
    completed_at: datetime | None = None


def create_app(
    settings: Settings | None = None,
    db: PostgresDatabase | None = None,
    queue: RedisQueue | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    db = db or PostgresDatabase(settings.database_url)
    queue = queue or RedisQueue(settings.redis_url)
    setup_logging(settings.log_level)
    setup_tracing(settings.service_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.connect()
        db.init_schema()
        queue.connect()
        logger.info(
            "catalog-api started latency_ms=%s error_rate=%s",
            settings.chaos_latency_ms,
            settings.chaos_error_rate,
        )
        yield
        queue.close()
        db.close()
        logger.info("catalog-api stopped")

    app = FastAPI(title="ShopLite Catalog API", lifespan=lifespan)
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.db = db
    app.state.queue = queue

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        database = "ok"
        queue_status = "ok"
        try:
            await asyncio.to_thread(db.ping)
        except Exception as exc:
            database = "unavailable"
            logger.error("readiness database check failed: %s", exc)
        try:
            await asyncio.to_thread(queue.ping)
        except Exception as exc:
            queue_status = "unavailable"
            logger.error("readiness queue check failed: %s", exc)

        body = {"status": "ready", "database": database, "queue": queue_status}
        if database == "ok" and queue_status == "ok":
            return body
        body["status"] = "not_ready"
        return JSONResponse(status_code=503, content=body)

    @app.get("/metrics")
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/products", response_model=list[Product])
    async def list_products():
        return await asyncio.to_thread(db.list_products)

    @app.get("/products/{product_id}", response_model=Product)
    async def get_product(product_id: int):
        if should_inject_latency(settings.chaos_latency_ms, random.random()):
            logger.info("injecting chaos latency of %sms", settings.chaos_latency_ms)
            await asyncio.sleep(settings.chaos_latency_ms / 1000)
        product = await asyncio.to_thread(db.get_product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return product

    @app.post("/orders", status_code=201, response_model=Order)
    async def create_order(body: OrderRequest, request: Request):
        if should_inject_error(settings.chaos_error_rate, random.random()):
            logger.error("injecting chaos error on POST /orders")
            raise HTTPException(status_code=500, detail="injected fault")

        product = await asyncio.to_thread(db.get_product, body.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        with tracer().start_as_current_span("postgres create_order"):
            order = await asyncio.to_thread(db.create_order, body.product_id, body.quantity)
        trace_id = getattr(request.state, "trace_id", None) or trace_id_var.get()
        payload = {"order_id": order["id"], "trace_id": trace_id}
        try:
            with tracer().start_as_current_span("redis enqueue") as span:
                span.set_attribute("order.id", order["id"])
                traceparent = inject_traceparent()
                if traceparent:
                    payload["traceparent"] = traceparent
                await asyncio.to_thread(queue.enqueue, payload)
                if hasattr(queue, "depth"):
                    ORDER_QUEUE_DEPTH.set(queue.depth())
        except Exception as exc:
            logger.error("failed to enqueue order %s: %s", order["id"], exc)
            await asyncio.to_thread(db.mark_failed, order["id"])
            raise HTTPException(status_code=503, detail="queue unavailable") from exc

        ORDERS_CREATED.inc()
        logger.info("created order %s", order["id"])
        return order

    @app.get("/orders/{order_id}", response_model=Order)
    async def get_order(order_id: int):
        order = await asyncio.to_thread(db.get_order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return order

    return app


app = create_app()
