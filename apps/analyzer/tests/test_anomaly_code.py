# -*- coding: utf-8 -*-
"""Regression: anomaly must ignore numbers in source code.

Bug v5.10.4-v5.10.6: enrich_anomaly ran on C/Java code, finding revision
numbers, hex constants as "numbers" (packet-btl2cap.c: samples=310,
mean=141, std=1684, ratio=11.9). v5.10.6 density guard insufficient.
Fix v5.10.7: std-ratio guard (std > 10x mean OR mean>1000 AND std>1000).
"""
from src.tools.anomaly import enrich_anomaly


def test_c_code_with_wide_distribution_filtered():
    """C code with scattered numbers -> {} (not metrics)."""
    code = (
        "/* $Id: packet-btl2cap.c 28412 2009-05-19 */\n"
        "#define MAX_SIZE 8000\n"
        "int x = 0x7fffffff;\n"
        "int array[1024];\n"
        "int z = 30000;\n"
        "int w = 28000;\n"
        "int v = 29000;\n"
        "int u = 31000;\n"
        "int t = 32000;\n"
        "int s = 33000;\n"
        "int r = 34000;\n"
        "int q = 35000;\n"
        "int p = 36000;\n"
        "int o = 37000;\n"
        "int n = 38000;\n"
    )
    r = enrich_anomaly(code)
    assert r == {"anomaly": {}}, f"FAIL: C code not filtered, got {r}"


def test_metrics_not_filtered_by_std_ratio():
    """Real metrics (latency) not filtered."""
    log = "\n".join([f"latency={48 + i % 5}ms" for i in range(20)])
    log += "\nlatency=5000ms"
    r = enrich_anomaly(log)
    assert r["anomaly"].get("verdict") == "ANOMALIES_FOUND"


def test_errors_metrics_not_filtered():
    """Error metrics not filtered."""
    log = "\n".join([f"errors={10 + i % 3}" for i in range(20)])
    log += "\nerrors=100"
    r = enrich_anomaly(log)
    assert "anomaly" in r
    # std/mean ratio should be small (<10)
    assert r["anomaly"].get("verdict") in ("NORMAL", "ANOMALIES_FOUND", "INSUFFICIENT_DATA")


def test_no_numbers_still_empty():
    """No numbers -> {}."""
    r = enrich_anomaly("hello world no digits")
    assert r == {"anomaly": {}}


def test_small_numbers_not_filtered():
    """Small numbers (mean<1000) not affected by criteria B."""
    csv = "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,1000"
    r = enrich_anomaly(csv)
    assert "anomaly" in r
    # Should detect 1000 as anomaly
    assert r["anomaly"].get("verdict") == "ANOMALIES_FOUND"
