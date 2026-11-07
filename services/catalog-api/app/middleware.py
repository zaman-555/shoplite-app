import logging
import time

from opentelemetry import trace
from opentelemetry.propagate import extract
from starlette.datastructures import Headers, MutableHeaders

from app.logging_config import trace_id_var
from app.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS
from app.tracing import exemplar

logger = logging.getLogger("catalog-api")


class ObservabilityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        parent = extract({key.lower(): value for key, value in headers.items()})
        method = scope.get("method", "")
        path = scope.get("path", "")
        tracer = trace.get_tracer("shoplite")
        with tracer.start_as_current_span(f"{method} {path}", context=parent) as span:
            span.set_attribute("http.request.method", method)
            span.set_attribute("url.path", path)
            trace_id = format(span.get_span_context().trace_id, "032x")
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
                route_path = getattr(route, "path", path)
                span.set_attribute("http.route", route_path)
                span.set_attribute("http.response.status_code", status_code)
                sample = exemplar()
                HTTP_REQUESTS.labels(method, route_path, str(status_code)).inc()
                if sample:
                    HTTP_REQUEST_DURATION.labels(method, route_path).observe(duration, exemplar=sample)
                else:
                    HTTP_REQUEST_DURATION.labels(method, route_path).observe(duration)
                logger.info("%s %s -> %s", method, path, status_code)
                trace_id_var.reset(token)
