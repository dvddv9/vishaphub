# -*- coding: utf-8 -*-
"""P2-12: Anomaly Detection tests (TDD).

Tests define the API of src/tools/anomaly.py before implementation.
All tests will fail on ImportError until anomaly.py is written.
"""
from src.tools.anomaly import parse_numbers, detect_anomaly, enrich_anomaly
from src.tools.patterns import ANOMALY_CONFIG


# ---------- parse_numbers ----------

def test_parse_numbers_plain():
    assert parse_numbers("1 2 3 4") == [1.0, 2.0, 3.0, 4.0]


def test_parse_numbers_kv():
    result = parse_numbers("latency=50\nlatency=52\nlatency=48")
    assert result == [50.0, 52.0, 48.0]


def test_parse_numbers_colon():
    result = parse_numbers("error_rate: 0.5\nerror_rate: 0.7")
    assert result == [0.5, 0.7]


def test_parse_numbers_empty():
    assert parse_numbers("") == []


def test_parse_numbers_no_numbers():
    assert parse_numbers("hello world no digits here") == []


def test_parse_numbers_skips_timestamps():
    """Numbers inside timestamps (2026-10-14) must be filtered out."""
    result = parse_numbers("2026-10-14 latency=100\n2026-10-15 latency=110")
    assert 2026 not in result
    assert 100.0 in result
    assert 110.0 in result


# ---------- detect_anomaly ----------

def test_detect_anomaly_zscore_simple():
    result = detect_anomaly([1.0] * 10 + [10.0], method="zscore")
    assert result["verdict"] == "ANOMALIES_FOUND"
    assert result["count"] >= 1
    assert any(a["value"] == 10.0 for a in result["anomalies"])


def test_detect_anomaly_zscore_no_anomaly():
    result = detect_anomaly([5.0] * 15, method="zscore")
    assert result["verdict"] == "NORMAL"
    assert result["count"] == 0


def test_detect_anomaly_iqr_method():
    result = detect_anomaly([1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 4.0, 4.0, 5.0, 100.0], method="iqr")
    assert result["method"] == "iqr"
    assert result["verdict"] == "ANOMALIES_FOUND"


def test_detect_anomaly_ewma_trend():
    values = [float(i) for i in range(1, 20)] + [1000.0]
    result = detect_anomaly(values, method="ewma")
    assert result["method"] == "ewma"
    assert result["verdict"] == "ANOMALIES_FOUND"


def test_detect_anomaly_insufficient_data():
    result = detect_anomaly([1.0, 2.0], method="zscore")
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["count"] == 0


def test_detect_anomaly_empty():
    assert detect_anomaly([], method="zscore") == {}


def test_detect_anomaly_max_cap():
    values = [1.0] * 10 + [100.0] * 50
    result = detect_anomaly(values, method="zscore")
    assert len(result["anomalies"]) <= ANOMALY_CONFIG["max_anomalies"]


# ---------- enrich_anomaly ----------

def test_enrich_anomaly_backward_compat():
    material = "latency=50\nlatency=52\nlatency=48\nlatency=5000"
    result = enrich_anomaly(material)
    assert "anomaly" in result


def test_enrich_anomaly_new_field():
    material = "\n".join([f"latency={50 + i}" for i in range(10)]) + "\nlatency=5000"
    result = enrich_anomaly(material)
    assert isinstance(result["anomaly"], dict)
    assert result["anomaly"].get("verdict") in ("ANOMALIES_FOUND", "NORMAL", "INSUFFICIENT_DATA")


def test_enrich_anomaly_empty():
    result = enrich_anomaly("no numbers here at all")
    assert result == {"anomaly": {}}


def test_enrich_anomaly_does_not_mutate_input():
    material = "latency=50\nlatency=52\nlatency=48\nlatency=5000"
    original = material
    enrich_anomaly(material)
    assert material == original
