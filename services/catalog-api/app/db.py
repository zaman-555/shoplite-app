import logging
import time
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger("catalog-api")

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
ADVISORY_LOCK_KEY = 424242


def _statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


class PostgresDatabase:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: ConnectionPool | None = None

    def connect(self) -> None:
        if self.pool is not None:
            return
        last_error: Exception | None = None
        for attempt in range(1, 11):
            pool = None
            try:
                pool = ConnectionPool(
                    conninfo=self.dsn,
                    min_size=1,
                    max_size=10,
                    timeout=10,
                    kwargs={"row_factory": dict_row},
                    open=False,
                )
                pool.open(wait=True, timeout=10)
                self.pool = pool
                return
            except Exception as exc:
                last_error = exc
                if pool is not None:
                    pool.close()
                logger.error("database connection failed (attempt %s): %s", attempt, exc)
                time.sleep(1)
        assert last_error is not None
        raise last_error

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            self.pool = None

    def init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text()
        statements = _statements(sql)
        last_error: Exception | None = None
        for attempt in range(1, 11):
            try:
                with self._pool().connection() as conn:
                    conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_KEY,))
                    for statement in statements:
                        conn.execute(statement)
                    conn.commit()
                logger.info("database schema ready")
                return
            except Exception as exc:
                last_error = exc
                logger.error("database init failed (attempt %s): %s", attempt, exc)
                time.sleep(1)
        assert last_error is not None
        raise last_error

    def ping(self) -> None:
        with self._pool().connection() as conn:
            conn.execute("SELECT 1")
            conn.rollback()

    def list_products(self) -> list[dict]:
        with self._pool().connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, price::float8 AS price, stock
                FROM products
                ORDER BY id
                """
            ).fetchall()
            conn.rollback()
        return list(rows)

    def get_product(self, product_id: int) -> dict | None:
        with self._pool().connection() as conn:
            row = conn.execute(
                """
                SELECT id, name, price::float8 AS price, stock
                FROM products
                WHERE id = %s
                """,
                (product_id,),
            ).fetchone()
            conn.rollback()
        return row

    def create_order(self, product_id: int, quantity: int) -> dict:
        with self._pool().connection() as conn:
            row = conn.execute(
                """
                INSERT INTO orders (product_id, quantity, status)
                VALUES (%s, %s, 'PENDING')
                RETURNING id, product_id, quantity, status, created_at, completed_at
                """,
                (product_id, quantity),
            ).fetchone()
            conn.commit()
        return row

    def get_order(self, order_id: int) -> dict | None:
        with self._pool().connection() as conn:
            row = conn.execute(
                """
                SELECT id, product_id, quantity, status, created_at, completed_at
                FROM orders
                WHERE id = %s
                """,
                (order_id,),
            ).fetchone()
            conn.rollback()
        return row

    def mark_failed(self, order_id: int) -> None:
        with self._pool().connection() as conn:
            conn.execute(
                """
                UPDATE orders
                SET status = 'FAILED'
                WHERE id = %s AND status = 'PENDING'
                """,
                (order_id,),
            )
            conn.commit()

    def _pool(self) -> ConnectionPool:
        if self.pool is None:
            raise RuntimeError("database is not connected")
        return self.pool
