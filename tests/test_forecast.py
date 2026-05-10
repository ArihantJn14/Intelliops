"""Tests for the NumPy polynomial forecaster."""
import pytest
import numpy as np
from unittest.mock import patch
from forecast.prophet_model import CPUForecaster


@pytest.fixture
def forecaster(tmp_path):
    f = CPUForecaster(field="cpu_percent")
    f.model_path = tmp_path / "test_model.json"
    return f


def _make_fake_history(n=50):
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        {"timestamp": (base + timedelta(minutes=i * 5)).isoformat(), "value": 30.0 + i * 0.1}
        for i in range(n)
    ]


def test_train_returns_status(forecaster):
    with patch("forecast.prophet_model.query_history", return_value=_make_fake_history()):
        result = forecaster.train(hours=1)
    assert result["status"] == "trained"
    assert result["field"] == "cpu_percent"
    assert result["samples"] > 0


def test_predict_after_train(forecaster):
    with patch("forecast.prophet_model.query_history", return_value=_make_fake_history()):
        forecaster.train(hours=1)
    result = forecaster.predict(periods=6)
    assert "predictions" in result
    assert len(result["predictions"]) == 6


def test_predict_without_training(forecaster):
    result = forecaster.predict(periods=6)
    assert "error" in result or "predictions" in result


def test_forecast_values_are_numbers(forecaster):
    with patch("forecast.prophet_model.query_history", return_value=_make_fake_history()):
        forecaster.train(hours=1)
    result = forecaster.predict(periods=3)
    for point in result["predictions"]:
        assert isinstance(point["predicted"], float)
        assert isinstance(point["lower"], float)
        assert isinstance(point["upper"], float)


def test_confidence_band_ordering(forecaster):
    with patch("forecast.prophet_model.query_history", return_value=_make_fake_history()):
        forecaster.train(hours=1)
    result = forecaster.predict(periods=3)
    for point in result["predictions"]:
        assert point["lower"] <= point["predicted"] <= point["upper"]


def test_model_persists_to_disk(forecaster):
    with patch("forecast.prophet_model.query_history", return_value=_make_fake_history()):
        forecaster.train(hours=1)
    assert forecaster.model_path.exists()
