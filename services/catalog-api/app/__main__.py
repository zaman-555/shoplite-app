import uvicorn

from app.config import Settings
from app.logging_config import build_log_config


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_config=build_log_config(settings.log_level),
        access_log=False,
    )


if __name__ == "__main__":
    main()
