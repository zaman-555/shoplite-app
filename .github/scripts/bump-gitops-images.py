#!/usr/bin/env python3
"""Rewrite image references in the GitOps values files. Does not deploy."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def image_lines(registry: str, tag: str, style: str) -> dict[str, str]:
    registry = registry.rstrip("/")
    if style == "ecr":
        names = {
            "web": "shoplite/web",
            "catalogApi": "shoplite/catalog-api",
            "orderWorker": "shoplite/order-worker",
        }
    else:
        names = {
            "web": "shoplite-web",
            "catalogApi": "shoplite-catalog-api",
            "orderWorker": "shoplite-order-worker",
        }
    return {key: f"{registry}/{value}:{tag}" for key, value in names.items()}


def rewrite(path: Path, images: dict[str, str]) -> None:
    lines = path.read_text().splitlines()
    updated = []
    for line in lines:
        key = line.split(":", 1)[0].strip()
        if key in images and line.startswith("  "):
            updated.append(f"  {key}: {images[key]}")
        else:
            updated.append(line)
    path.write_text("\n".join(updated) + "\n")


def main() -> None:
    root = Path(sys.argv[1])
    tag = os.environ["IMAGE_TAG"]
    registry = os.environ["registry"]
    style = os.environ.get("image_style", "ghcr")
    images = image_lines(registry, tag, style)
    for env_name in ("dev", "prod"):
        rewrite(root / "envs" / env_name / "values.yaml", images)
        print(f"updated envs/{env_name}/values.yaml")


if __name__ == "__main__":
    main()
