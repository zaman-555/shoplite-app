import json
import logging
import logging.config
import os
from contextvars import ContextVar
from datetime import datetime, timezone

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "service": os.getenv("SERVICE_NAME", "order-worker"),
            "message": record.getMessage(),
            "trace_id": trace_id_var.get(),
        }
        return json.dumps(payload, ensure_ascii=False)


def build_log_config(level: str = "INFO") -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "logging_config.JsonFormatter"},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
            }
        },
        "root": {"handlers": ["stdout"], "level": level},
    }


def setup_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(build_log_config(level))
