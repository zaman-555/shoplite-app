import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders

from app.logging_config import trace_id_var
from app.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS

logger = logging.getLogger("catalog-api")


class ObservabilityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        trace_id = headers.get("x-request-id") or str(uuid.uuid4())
        scope.setdefault("state", {})["trace_id"] = trace_id
        token = trace_id_var.set(trace_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Trace-Id"] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - started
            route = scope.get("route")
            endpoint = getattr(route, "path", scope.get("path", ""))
            method = scope.get("method", "")
            HTTP_REQUESTS.labels(method, endpoint, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method, endpoint).observe(duration)
            logger.info("%s %s -> %s", method, scope.get("path", ""), status_code)
            trace_id_var.reset(token)
