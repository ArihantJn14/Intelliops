import os

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "intelliops-super-secret-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "intelliops")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "metrics")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    return _client


def query_history(field: str, hours: int = 1) -> list[dict]:
    """
    Fetch the last N hours of a single field from InfluxDB.
    field: 'cpu_percent', 'memory_percent', 'disk_percent', etc.
    Returns a list of {time, value} dicts sorted oldest-first.
    """
    query = f"""
from(bucket: "{INFLUX_BUCKET}")
|> range(start: -{hours}h)
|> filter(fn: (r) => r._measurement == "system_metrics")
|> filter(fn: (r) => r._field == "{field}")
|> sort(columns: ["_time"])
"""

    tables = get_client().query_api().query(query, org=INFLUX_ORG)
    results = []

    for table in tables:
        for record in table.records:
            results.append(
                {
                    "time": record.get_time().isoformat(),
                    "value": round(record.get_value(), 2),
                }
            )

    return results


def query_multi_field(fields: list[str], hours: int = 1) -> dict:
    """Fetch multiple fields at once. Returns {field: [{time, value}]}"""
    return {field: query_history(field, hours) for field in fields}
