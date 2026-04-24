import pytest
import numpy as np
from app.detector import AnomalyDetector


@pytest.fixture
def trained_detector():
    detector = AnomalyDetector(contamination=0.1)

    # clean baseline — tight distribution, no outliers
    normal = []
    for _ in range(200):
        normal.append({
            "error_count": int(np.random.normal(2, 1)),
            "latency_ms": int(np.random.normal(120, 20)),
            "memory_used_mb": int(np.random.normal(256, 30)),
            "request_count": int(np.random.normal(100, 15)),
        })

    detector.train(normal)
    return detector


def test_normal_log_not_flagged(trained_detector):
    # typical healthy Lambda invocation — should never trip the detector
    log = {
        "error_count": 2,
        "latency_ms": 115,
        "memory_used_mb": 260,
        "request_count": 98,
    }
    result = trained_detector.detect(log)
    assert result["is_anomaly"] is False


def test_anomalous_log_flagged(trained_detector):
    # everything spiked at once — this should always be caught
    log = {
        "error_count": 999,
        "latency_ms": 9000,
        "memory_used_mb": 2048,
        "request_count": 1,
    }
    result = trained_detector.detect(log)
    assert result["is_anomaly"] is True


def test_severity_score_higher_for_worse_anomaly(trained_detector):
    mild = {
        "error_count": 10,
        "latency_ms": 200,
        "memory_used_mb": 300,
        "request_count": 80,
    }
    severe = {
        "error_count": 999,
        "latency_ms": 9000,
        "memory_used_mb": 2048,
        "request_count": 1,
    }
    mild_result = trained_detector.detect(mild)
    severe_result = trained_detector.detect(severe)

    # worse signal should always score higher
    assert severe_result["severity_score"] > mild_result["severity_score"]


def test_detect_raises_if_not_trained():
    # calling detect before train should fail loudly, not silently return junk
    detector = AnomalyDetector()
    with pytest.raises(RuntimeError):
        detector.detect({"error_count": 1})


def test_result_has_required_keys(trained_detector):
    log = {"error_count": 2, "latency_ms": 120, "memory_used_mb": 256, "request_count": 100}
    result = trained_detector.detect(log)

    assert "timestamp" in result
    assert "is_anomaly" in result
    assert "severity_score" in result
    assert "log_entry" in result