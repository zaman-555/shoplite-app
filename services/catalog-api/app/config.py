import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if raw == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    service_name: str
    database_url: str
    redis_url: str
    chaos_latency_ms: int
    chaos_error_rate: float
    log_level: str
    port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            service_name=os.getenv("SERVICE_NAME", "catalog-api"),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://shoplite:shoplite@localhost:5432/shoplite",
            ),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            chaos_latency_ms=_env_int("CHAOS_LATENCY_MS", 0),
            chaos_error_rate=_env_float("CHAOS_ERROR_RATE", 0.0),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            port=_env_int("PORT", 8000),
        )
