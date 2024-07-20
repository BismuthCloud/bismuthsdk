from typing import Iterator, Optional
import polars
import psycopg

from .base import DataConnector

class PostgresConnector(DataConnector):
    """
    A PostgreSQL backed connector.
    """
    def __init__(self, pg_uri: str, table: str):
        self.conn = psycopg.connect(pg_uri)
        self.table = table

    @property
    def columns(self) -> list[str]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (self.table,))
            return [row[0] for row in cur.fetchall()]
    
    def approx_count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT reltuples FROM pg_class WHERE relname = %s", (self.table,))
            val = cur.fetchone()[0]
            if val > 0:
                return val
            # fall back to COUNT(*) if ANALYZE hasn't been run
            cur.execute(f"SELECT COUNT(*) FROM {self.table}")
            return cur.fetchone()[0]
    
    def approx_cardinality(self, column: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(DISTINCT {column}) FROM {self.table}")
            return cur.fetchone()[0]
    
    def sample(self, n: int, seed: Optional[int] = None) -> Iterator[polars.DataFrame]:
        with self.conn.cursor() as cur:
            if seed is not None:
                seed = (seed % 2**32) / 2**32
                cur.execute(f"SELECT setseed({seed})")
            cur.execute(f"SELECT * FROM {self.table} ORDER BY RANDOM() LIMIT {n}")
            while True:
                batch = cur.fetchmany(10000)
                if not batch:
                    break
                yield polars.DataFrame(batch, schema=self.columns)
