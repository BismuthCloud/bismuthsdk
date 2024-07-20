from abc import ABC, abstractmethod
from functools import cached_property
from typing import Any, Iterator, Optional
import polars

class DataConnector(ABC):
    """
    The base class for all Bismuth ML data connectors.
    """
    @cached_property
    @abstractmethod
    def columns(self) -> list[str]:
        """
        The column names in the data source.
        """
        ...
    
    @abstractmethod
    def approx_count(self) -> int:
        """
        An approximate count of the rows in the data source.
        """
        ...
    
    @abstractmethod
    def approx_cardinality(self, column: str) -> int:
        """
        The number of distinct values in the given column.
        """
        ...
    
    @abstractmethod
    def sample(self, n: int, seed: Optional[int] = None) -> Iterator[polars.DataFrame]:
        """
        Randomly sample n rows from the data source.
        """
        ...
        
    def __getitem__(self, columns: list[str]) -> 'DataConnectorView':
        """
        Create a view of this data connector with the given columns.
        """
        for column in columns:
            if column not in self.columns:
                raise ValueError(f"Column {column} not found in data source.")
        return DataConnectorView(self, columns)

class DataConnectorView:
    """
    A view of a data connector selecting specific columns.
    """
    connector: DataConnector
    columns: list[str]
    
    def __init__(self, connector: DataConnector, columns: list[str]):
        self.connector = connector
        self.columns = columns