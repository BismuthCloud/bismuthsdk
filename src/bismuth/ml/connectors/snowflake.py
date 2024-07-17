from typing import Optional
import snowflake.connector
import pandas

from .base import DataConnector

class SnowflakeConnector(DataConnector):
    """
    A connector to Snowflake.
    """
    def __init__(self, connection_kwargs: dict, table: str):
        self.conn = snowflake.connector.connect(**connection_kwargs)
        self.table = table

    @property
    def columns(self) -> list[str]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position ASC", (self.table,))
            return [row[0] for row in cur.fetchall()]
    
    def approx_count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT row_count FROM information_schema.tables WHERE table_name = %s", (self.table,))
            return cur.fetchone()[0]
    
    def approx_cardinality(self, column: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT APPROX_COUNT_DISTINCT({column}) FROM {self.table}")
            return cur.fetchone()[0]
    
    def sample(self, n: int, seed: Optional[int] = None) -> pandas.DataFrame:
        seed = str(seed) if seed is not None else ""
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {self.table} ORDER BY RANDOM({seed}) LIMIT {n}")
            return cur.fetch_pandas_all()
