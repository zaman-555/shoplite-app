FROM python:3.12-alpine AS runtime-deps

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY services/catalog-api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM runtime-deps AS lean-venv

RUN rm -rf /opt/venv/lib/python3.12/site-packages/pip \
        /opt/venv/lib/python3.12/site-packages/pip-*.dist-info \
        /opt/venv/bin/pip \
        /opt/venv/bin/pip3 \
        /opt/venv/bin/pip3.12

FROM runtime-deps AS test

WORKDIR /app
COPY services/catalog-api/requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
COPY services/catalog-api/app ./app
COPY services/catalog-api/tests ./tests
COPY services/catalog-api/pytest.ini .
CMD ["pytest", "-q"]

FROM python:3.12-alpine AS runtime

RUN addgroup -g 10001 -S app \
    && adduser -S -D -H -u 10001 -G app app

COPY --from=lean-venv /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SERVICE_NAME=catalog-api

WORKDIR /app
COPY --chown=app:app services/catalog-api/app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=10s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

CMD ["python", "-m", "app"]
