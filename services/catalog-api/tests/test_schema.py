import re
from pathlib import Path

SCHEMA = (Path(__file__).parents[1] / "app" / "schema.sql").read_text()


def test_schema_defines_product_and_order_columns():
    normalized = " ".join(SCHEMA.split())
    assert "CREATE TABLE IF NOT EXISTS products" in normalized
    for column in ("id", "name", "price", "stock"):
        assert column in normalized
    assert "CREATE TABLE IF NOT EXISTS orders" in normalized
    for column in ("product_id", "quantity", "status", "created_at", "completed_at"):
        assert column in normalized
    for status in ("PENDING", "PROCESSING", "COMPLETED", "FAILED"):
        assert status in SCHEMA


def test_schema_seeds_at_least_ten_products():
    names = re.findall(r"\('([^']+)'", SCHEMA)
    assert len(names) >= 10
    assert len(names) == len(set(names))
