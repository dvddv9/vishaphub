# -*- coding: utf-8 -*-
"""Regression: anomaly must fail-quiet on non-numeric text.

Bug v5.10.4-v5.10.5: enrich_anomaly ran on Java/C/Python source code,
finding line numbers and hex constants as "numbers" (samples=22 on
RequestFilter.java, mean=645, std=794). Harmless but noisy in audit trail.

Fix v5.10.6: density guard -- if len(numbers)/len(text) < 0.01, return {}.
"""
from src.tools.anomaly import enrich_anomaly


JAVA_CODE = (
    "package org.example;\n"
    "public class A {\n"
    "    int x = 0x7fffffff;\n"
    "    long y = 1024L;\n"
    "    String s = \"hello world\";\n"
    "    public void run() { System.out.println(s); }\n"
    "}\n"
)

PYTHON_CODE = (
    "def hello():\n"
    "    x = 1\n"
    "    return x + 2\n"
)


def test_anomaly_skips_java_code():
    """Java source with few numbers -> empty anomaly."""
    result = enrich_anomaly(JAVA_CODE)
    assert result == {"anomaly": {}}, f"expected empty, got {result}"


def test_anomaly_skips_python_code():
    """Python source with few numbers -> empty anomaly."""
    result = enrich_anomaly(PYTHON_CODE)
    assert result == {"anomaly": {}}


def test_anomaly_works_on_metrics_log():
    """Real metrics log with high number density -> analysis runs."""
    log = "\n".join([f"latency={48 + i % 5}ms" for i in range(20)])
    log += "\nlatency=5000ms"
    result = enrich_anomaly(log)
    assert "anomaly" in result
    assert result["anomaly"].get("verdict") == "ANOMALIES_FOUND"


def test_anomaly_works_on_csv_numbers():
    """Pure numeric series -> analysis runs."""
    csv = "1,2,3,4,5,6,7,8,9,10,100"
    result = enrich_anomaly(csv)
    assert "anomaly" in result


def test_anomaly_density_threshold_boundary():
    """At boundary (density == 0.01) -- analysis runs."""
    text = "value=42 rest"
    result = enrich_anomaly(text)
    assert "anomaly" in result
