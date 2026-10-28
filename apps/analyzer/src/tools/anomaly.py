# -*- coding: utf-8 -*-
"""P2-12 Anomaly Detection: statistical outlier detection in numeric series.

Extends audit trail with anomaly detection over numeric data in the material
(logs, metrics, CSV). Complements the LLM pipeline with deterministic math.

Architecture:
    patterns.py -> ANOMALY_CONFIG (data)
    anomaly.py  -> parse_numbers(), detect_anomaly(), enrich_anomaly() (logic)

Methods:
    zscore -- |x - mean| / std > threshold (default 3.0)
    iqr    -- x < Q1 - m*IQR or x > Q3 + m*IQR (default m=1.5)
    ewma   -- |x_t - EWMA_{t-1}| > threshold * std (default alpha=0.3)

Deterministic: stdlib statistics only, no LLM.
Fail-open: returns {} or {"anomaly": {}} on error or insufficient data.
Backward compatible: adds new field, does not mutate input.
"""
import re
import statistics

from src.tools.patterns import ANOMALY_CONFIG


def _is_timestamp_part(text: str, start: int, end: int) -> bool:
    """Check if a number touches a timestamp separator on either side.

    Timestamps: 2026-10-14, 14:32:00, 2026/10/14.
    Rule: if either neighbor is '-' / ':' / '/', treat as timestamp part.
    # P2-12-fix2
    """
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    ts_chars = {"-", ":", "/"}
    return before in ts_chars or after in ts_chars


def parse_numbers(material: str) -> list[float]:
    """Extract numeric values from material.

    Handles: plain numbers, "key=123", "key: 123", "key 123ms".
    Skips numbers that are part of timestamps (2026-10-14, 14:32:00).

    Returns: list of floats in order of appearance.
    """
    if not material:
        return []

    # Match numbers NOT preceded by digit or ts separator directly.
    # Use lookbehind: don't match if previous char is digit (part of longer number).
    pattern = re.compile(r"(?<![\d])(\d+(?:\.\d+)?)")
    values = []
    for m in pattern.finditer(material):
        start, end = m.start(), m.end()
        if _is_timestamp_part(material, start, end):
            continue
        try:
            values.append(float(m.group()))
        except ValueError:
            continue
    return values


def _detect_zscore(values: list[float], threshold: float) -> dict:
    mean = statistics.mean(values)
    try:
        std = statistics.stdev(values)
    except statistics.StatisticsError:
        std = 0.0

    anomalies = []
    if std > 0:
        for i, v in enumerate(values):
            z = (v - mean) / std
            if abs(z) > threshold:
                anomalies.append({
                    "index": i,
                    "value": v,
                    "score": round(z, 3),
                    "reason": f"z-score {z:.2f} > {threshold}",
                })
    return {"baseline": {"mean": round(mean, 3), "std": round(std, 3)},
            "anomalies": anomalies}


def _detect_iqr(values: list[float], multiplier: float) -> dict:
    sorted_v = sorted(values)
    n = len(sorted_v)
    q1 = sorted_v[n // 4]
    q3 = sorted_v[(3 * n) // 4]
    iqr = q3 - q1
    low = q1 - multiplier * iqr
    high = q3 + multiplier * iqr

    anomalies = []
    for i, v in enumerate(values):
        if v < low or v > high:
            anomalies.append({
                "index": i,
                "value": v,
                "score": round(max(low - v, v - high), 3),
                "reason": f"outside IQR box [{low:.2f}, {high:.2f}]",
            })
    return {"baseline": {"q1": q1, "q3": q3, "iqr": round(iqr, 3)},
            "anomalies": anomalies}


def _detect_ewma(values: list[float], alpha: float) -> dict:
    if len(values) < 2:
        return {"baseline": {}, "anomalies": []}

    try:
        std = statistics.stdev(values)
    except statistics.StatisticsError:
        std = 0.0

    ewma = values[0]
    anomalies = []
    threshold = 3.0 * std if std > 0 else 0.0

    for i in range(1, len(values)):
        diff = abs(values[i] - ewma)
        if threshold > 0 and diff > threshold:
            anomalies.append({
                "index": i,
                "value": values[i],
                "score": round(diff, 3),
                "reason": f"|x - EWMA| = {diff:.2f} > {threshold:.2f}",
            })
        ewma = alpha * values[i] + (1 - alpha) * ewma

    return {"baseline": {"ewma_final": round(ewma, 3), "std": round(std, 3)},
            "anomalies": anomalies}


def detect_anomaly(values: list[float], method: str = "zscore",
                   threshold: float | None = None) -> dict:
    """Detect anomalies in a numeric series.

    Args:
        values: numeric series.
        method: "zscore" | "iqr" | "ewma".
        threshold: override default from ANOMALY_CONFIG.

    Returns:
        {
            "method": str,
            "verdict": "ANOMALIES_FOUND" | "NORMAL" | "INSUFFICIENT_DATA",
            "count": int,
            "anomalies": [{"index", "value", "score", "reason"}, ...],
            "baseline": {...},
            "samples": int,
        }
        Empty dict if values empty.
    """
    if not values:
        return {}

    min_samples = ANOMALY_CONFIG["min_samples"]
    if len(values) < min_samples:
        return {
            "method": method,
            "verdict": "INSUFFICIENT_DATA",
            "count": 0,
            "anomalies": [],
            "baseline": {},
            "samples": len(values),
        }

    methods_cfg = ANOMALY_CONFIG["methods"]
    cfg = methods_cfg.get(method, methods_cfg[ANOMALY_CONFIG["default_method"]])

    if method == "zscore":
        t = threshold if threshold is not None else cfg["threshold"]
        result = _detect_zscore(values, t)
    elif method == "iqr":
        t = threshold if threshold is not None else cfg["multiplier"]
        result = _detect_iqr(values, t)
    elif method == "ewma":
        t = threshold if threshold is not None else cfg["alpha"]
        result = _detect_ewma(values, t)
    else:
        return {}

    anomalies = result["anomalies"]
    max_cap = ANOMALY_CONFIG["max_anomalies"]
    if len(anomalies) > max_cap:
        anomalies = sorted(anomalies, key=lambda a: abs(a["score"]), reverse=True)[:max_cap]
        anomalies.sort(key=lambda a: a["index"])

    verdict = "ANOMALIES_FOUND" if anomalies else "NORMAL"
    return {
        "method": method,
        "verdict": verdict,
        "count": len(anomalies),
        "anomalies": anomalies,
        "baseline": result["baseline"],
        "samples": len(values),
    }


def enrich_anomaly(material: str, method: str | None = None) -> dict:
    """Enrich audit with anomaly detection.

    Returns: {"anomaly": {...}} or {"anomaly": {}}.

    # v5.10.6-density-guard: если текст не числовой (плотность чисел < 1%),
    возвращаем {} -- иначе на коде (Java/C/Python) будет ложный анализ
    номеров строк / hex-констант.
    """
    try:
        values = parse_numbers(material)
        if not values:
            return {"anomaly": {}}

        # v5.10.6-density-guard
        density = len(values) / max(len(material), 1)
        if density < 0.01:
            return {"anomaly": {}}

        # v5.10.7-std-ratio-guard-v2: код vs метрики.
        # Dogfood find (packet-btl2cap.c): 310 чисел в C-коде (ревизия 28412, hex,
        # размеры) -> mean=141, std=1684 (ratio 11.9).
        # Реальные метрики (latency, RPS, errors) имеют std < 2x mean
        # и малые абсолютные значения.
        #
        # Критерий A: std > 10x mean (packet-btl2cap.c: 11.9x).
        # Критерий B: mean > 1000 AND std > 1000 (большие разбросанные числа).
        if len(values) >= 2:
            _mean = sum(values) / len(values)
            _var = sum((x - _mean) ** 2 for x in values) / (len(values) - 1)
            _std = _var ** 0.5
            _crit_a = _mean > 0 and _std > 10 * _mean
            _crit_b = _mean > 1000 and _std > 1000
            if _crit_a or _crit_b:
                return {"anomaly": {}}

        m = method or ANOMALY_CONFIG["default_method"]
        result = detect_anomaly(values, method=m)
        # v5.10.6-insufficient-guard: если данных мало -- не пишем шум в audit.
        if result.get("verdict") == "INSUFFICIENT_DATA":
            return {"anomaly": {}}
        return {"anomaly": result}
    except Exception:
        return {"anomaly": {}}
