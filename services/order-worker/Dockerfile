FROM python:3.12-alpine AS runtime-deps

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY services/order-worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM runtime-deps AS lean-venv

RUN rm -rf /opt/venv/lib/python3.12/site-packages/pip \
        /opt/venv/lib/python3.12/site-packages/pip-*.dist-info \
        /opt/venv/bin/pip \
        /opt/venv/bin/pip3 \
        /opt/venv/bin/pip3.12

FROM runtime-deps AS test

WORKDIR /app
COPY services/order-worker/requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
COPY services/order-worker/config.py /app/config.py
COPY services/order-worker/logging_config.py /app/logging_config.py
COPY services/order-worker/metrics.py /app/metrics.py
COPY services/order-worker/tracing.py /app/tracing.py
COPY services/order-worker/orders_queue.py /app/orders_queue.py
COPY services/order-worker/db.py /app/db.py
COPY services/order-worker/worker.py /app/worker.py
COPY services/order-worker/tests /app/tests
COPY services/order-worker/pytest.ini /app/pytest.ini
CMD ["pytest", "-q"]

FROM python:3.12-alpine AS runtime

RUN addgroup -g 10001 -S app \
    && adduser -S -D -H -u 10001 -G app app

COPY --from=lean-venv /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICE_NAME=order-worker \
    SCHEMA_PATH=/app/schema.sql

WORKDIR /app
COPY --chown=app:app services/order-worker/config.py /app/config.py
COPY --chown=app:app services/order-worker/logging_config.py /app/logging_config.py
COPY --chown=app:app services/order-worker/metrics.py /app/metrics.py
COPY --chown=app:app services/order-worker/tracing.py /app/tracing.py
COPY --chown=app:app services/order-worker/orders_queue.py /app/orders_queue.py
COPY --chown=app:app services/order-worker/db.py /app/db.py
COPY --chown=app:app services/order-worker/worker.py /app/worker.py
COPY --chown=app:app services/catalog-api/app/schema.sql /app/schema.sql

USER app
EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=10s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/metrics')"

CMD ["python", "-m", "worker"]
