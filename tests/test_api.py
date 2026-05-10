"""Tests for FastAPI endpoints."""
from unittest.mock import patch, MagicMock


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "buffer_size" in data


def test_metrics_empty(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "count" in data


def test_metrics_latest_no_data(client):
    resp = client.get("/metrics/latest")
    assert resp.status_code == 200


def test_anomalies_empty(client):
    resp = client.get("/anomalies")
    assert resp.status_code == 200
    data = resp.json()
    assert "anomalies" in data
    assert data["count"] == 0 or isinstance(data["anomalies"], list)


def test_ingest_normal(client, sample_metric):
    with patch("api.consumer.write_to_influx"):
        resp = client.post("/ingest", json=sample_metric)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "anomaly_score" in data
    assert data["anomaly_score"] == 0.0  # CPU 25% → not anomalous


def test_ingest_high_cpu(client, high_cpu_metric):
    with patch("api.consumer.write_to_influx"), \
         patch("ai.explainer.explain_anomaly", return_value="Test explanation"):
        resp = client.post("/ingest", json=high_cpu_metric)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["anomaly_score"] > 0  # CPU 85% → anomaly


def test_metrics_summary_after_ingest(client, sample_metric):
    with patch("api.consumer.write_to_influx"):
        client.post("/ingest", json=sample_metric)
    resp = client.get("/metrics/summary")
    assert resp.status_code == 200


def test_chat_endpoint(client):
    mock_answer = "The system is healthy with no anomalies."
    with patch("ai.chat.answer", return_value=mock_answer):
        resp = client.post("/chat", json={"question": "Is the system healthy?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == mock_answer
    assert data["question"] == "Is the system healthy?"


def test_forecast_no_model(client):
    resp = client.get("/forecast")
    assert resp.status_code == 200


def test_latest_explanation_no_anomalies(client):
    resp = client.get("/anomalies/latest/explanation")
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation" in data
