"""Tests for anomaly detection logic."""
import pytest
from anomaly.detector import AnomalyDetector


@pytest.fixture
def detector():
    return AnomalyDetector()


def test_normal_cpu_not_anomaly(detector):
    reading = {"cpu_percent": 30.0, "memory_percent": 50.0}
    assert not detector.is_anomaly(reading)


def test_high_cpu_is_anomaly(detector):
    reading = {"cpu_percent": 75.0, "memory_percent": 50.0}
    assert detector.is_anomaly(reading)


def test_boundary_cpu_60_not_anomaly(detector):
    reading = {"cpu_percent": 60.0, "memory_percent": 50.0}
    assert not detector.is_anomaly(reading)


def test_boundary_cpu_61_is_anomaly(detector):
    reading = {"cpu_percent": 61.0, "memory_percent": 50.0}
    assert detector.is_anomaly(reading)


def test_score_zero_for_normal(detector):
    reading = {"cpu_percent": 20.0, "memory_percent": 40.0}
    assert detector.score(reading) == 0.0


def test_score_positive_for_high_cpu(detector):
    reading = {"cpu_percent": 80.0, "memory_percent": 50.0}
    assert detector.score(reading) > 0.0


def test_score_scales_with_cpu(detector):
    low = detector.score({"cpu_percent": 65.0, "memory_percent": 50.0})
    high = detector.score({"cpu_percent": 90.0, "memory_percent": 50.0})
    assert high > low


def test_score_max_is_one(detector):
    reading = {"cpu_percent": 100.0, "memory_percent": 90.0}
    assert detector.score(reading) <= 1.0


def test_missing_cpu_key(detector):
    reading = {"memory_percent": 50.0}
    # Should not raise — defaults gracefully
    score = detector.score(reading)
    assert score == 0.0
