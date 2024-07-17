from typing import Optional
import duckdb
import pandas

from .base import DataConnector

class FileConnector(DataConnector):
    """
    A DuckDB backed connector for reading from CSV, JSON, Parquet, etc. files.
    """
    def __init__(self, file_path: str, loader_kwargs: dict = {}):
        match file_path.split('.')[-1]:
            case 'csv':
                self.data = duckdb.read_csv(file_path, **loader_kwargs)
            case 'json':
                self.data = duckdb.read_parquet(file_path, **loader_kwargs)
            case 'parquet':
                self.data = duckdb.read_json(file_path, **loader_kwargs)
            case _:
                raise ValueError(f"Unsupported file type: {file_path}")

    @property
    def columns(self) -> list[str]:
        return self.data.columns
    
    def approx_count(self) -> int:
        return len(self.data)
    
    def approx_cardinality(self, column: str) -> int:
        return len(self.data[column].distinct())
    
    def sample(self, n: int, seed: Optional[int] = None) -> pandas.DataFrame:
        if seed is not None:
            seed = (seed % 2**32) / 2**32
            self.data.query("tbl", f"SELECT setseed({seed})").fetchall()
            return self.data.query("tbl", f"SELECT * FROM tbl ORDER BY RANDOM() LIMIT {n}").df()
        return self.data.query("tbl", f"SELECT * FROM tbl ORDER BY RANDOM() LIMIT {n}").df()