import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="session")
def client():
    # Patch Kafka consumer so it doesn't try to connect during tests
    with patch("api.consumer.start_consumer_thread"):
        from api.main import app
        yield TestClient(app)


@pytest.fixture
def sample_metric():
    return {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "host": "test-host",
        "cpu_percent": 25.0,
        "cpu_count": 4,
        "cpu_per_core": [20.0, 25.0, 30.0, 25.0],
        "memory_percent": 55.0,
        "memory_used_gb": 4.2,
        "memory_total_gb": 8.0,
        "memory_available_gb": 3.8,
        "disk_percent": 40.0,
        "disk_used_gb": 40.0,
        "disk_total_gb": 100.0,
        "net_bytes_sent_mb": 100.0,
        "net_bytes_recv_mb": 200.0,
        "net_packets_sent": 1000,
        "net_packets_recv": 2000,
    }


@pytest.fixture
def high_cpu_metric(sample_metric):
    return {**sample_metric, "cpu_percent": 85.0}
