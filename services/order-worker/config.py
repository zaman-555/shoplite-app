import os
from dataclasses import dataclass

_TRUE_VALUES = {"1", "true", "yes", "on"}


def env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    service_name: str = "order-worker"
    database_url: str = "postgresql://shoplite:shoplite@localhost:5432/shoplite"
    redis_url: str = "redis://localhost:6379/0"
    chaos_memory_leak: bool = False
    chaos_slow_db: bool = False
    metrics_port: int = 8001
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            service_name=os.getenv("SERVICE_NAME", "order-worker"),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://shoplite:shoplite@localhost:5432/shoplite",
            ),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            chaos_memory_leak=env_bool("CHAOS_MEMORY_LEAK"),
            chaos_slow_db=env_bool("CHAOS_SLOW_DB"),
            metrics_port=env_int("METRICS_PORT", 8001),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
