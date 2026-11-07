import logging
import os
import time
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger("order-worker")

ADVISORY_LOCK_KEY = 424242


def schema_sql() -> str:
    candidates = []
    env_path = os.getenv("SCHEMA_PATH")
    if env_path:
        candidates.append(Path(env_path))
    here = Path(__file__).resolve().parent
    candidates.append(here / "schema.sql")
    candidates.append(here.parent / "catalog-api" / "app" / "schema.sql")
    for path in candidates:
        if path.is_file():
            return path.read_text()
    raise FileNotFoundError("schema.sql not found")


def _statements(sql: str) -> list[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


class PostgresDatabase:
    def __init__(self, dsn: str, chaos_slow_db: bool = False):
        self.dsn = dsn
        self.chaos_slow_db = chaos_slow_db
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
                    max_size=4,
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
        statements = _statements(schema_sql())
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

    def execute_update(self, conn, sql: str, params: tuple = ()):
        if self.chaos_slow_db:
            conn.execute("SELECT pg_sleep(2)")
        return conn.execute(sql, params)

    def claim_order(self, order_id: int) -> bool:
        with self._pool().connection() as conn:
            row = self.execute_update(
                conn,
                """
                UPDATE orders
                SET status = 'PROCESSING'
                WHERE id = %s AND status = 'PENDING'
                RETURNING id
                """,
                (order_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def finish_order(self, order_id: int) -> str:
        with self._pool().connection() as conn:
            completed = self.execute_update(
                conn,
                """
                UPDATE orders
                SET status = 'COMPLETED', completed_at = NOW()
                WHERE id = %s
                  AND status = 'PROCESSING'
                  AND EXISTS (
                      SELECT 1
                      FROM products
                      WHERE products.id = orders.product_id
                        AND products.stock >= orders.quantity
                  )
                RETURNING id, product_id, quantity
                """,
                (order_id,),
            ).fetchone()
            if completed:
                self.execute_update(
                    conn,
                    """
                    UPDATE products
                    SET stock = stock - %s
                    WHERE id = %s
                    """,
                    (completed["quantity"], completed["product_id"]),
                )
                conn.commit()
                return "COMPLETED"
            self.execute_update(
                conn,
                """
                UPDATE orders
                SET status = 'FAILED'
                WHERE id = %s AND status = 'PROCESSING'
                """,
                (order_id,),
            )
            conn.commit()
            return "FAILED"

    def mark_failed(self, order_id: int) -> None:
        with self._pool().connection() as conn:
            self.execute_update(
                conn,
                """
                UPDATE orders
                SET status = 'FAILED'
                WHERE id = %s AND status IN ('PENDING', 'PROCESSING')
                """,
                (order_id,),
            )
            conn.commit()

    def _pool(self) -> ConnectionPool:
        if self.pool is None:
            raise RuntimeError("database is not connected")
        return self.pool
