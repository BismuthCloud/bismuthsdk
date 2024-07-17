from .file import FileConnector
from .postgresql import PostgresConnector
from .snowflake import SnowflakeConnector
import csv
import os
import pytest

def setup_postgres():
    dataset = csv.reader(open("src/bismuth/ml/connectors/testdata/iris.csv"))
    next(dataset) # skip header
    pg = PostgresConnector("postgresql://postgres:password@localhost:5432/postgres", "iris")
    with pg.conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS iris")
        cur.execute("CREATE TABLE iris (sepal_length FLOAT, sepal_width FLOAT, petal_length FLOAT, petal_width FLOAT, variety TEXT)")
        cur.executemany("INSERT INTO iris VALUES (%s, %s, %s, %s, %s)", dataset)
        pg.conn.commit()
    return pg

@pytest.fixture(params=[
    FileConnector("src/bismuth/ml/connectors/testdata/iris.csv"),
    setup_postgres(),
    SnowflakeConnector({
        "user": os.environ["SNOWFLAKE_USER"],
        "password": os.environ["SNOWFLAKE_PASSWORD"],
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "warehouse": "COMPUTE_WH",
        "database": "TEST",
        "schema": "PUBLIC",
    }, "IRIS")
])
def connector(request):
    return request.param

def test_columns(connector):
    assert [c.lower() for c in connector.columns] == ["sepal_length","sepal_width","petal_length","petal_width","variety"]

def test_count(connector):
    assert connector.approx_count() == 150

def test_cardinality(connector):
    assert connector.approx_cardinality("variety") == 3
    
def test_sample(connector):
    sample1 = connector.sample(3, seed=42)
    sample2 = connector.sample(3, seed=42)
    assert sample1.equals(sample2), "sample should be deterministic with the same seed"