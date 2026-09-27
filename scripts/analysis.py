"""Deterministic descriptive metrics. Stability labels are rules, not probabilities."""
from __future__ import annotations

import statistics

METHOD_VERSION = "1.0"


def growth(previous, current):
    return 100 * (current / previous - 1) if previous > 0 else None


def sign(value):
    return 0 if abs(value) < 1e-9 else (1 if value > 0 else -1)


def analyze(months, values, totals, page):
    n = len(months)
    flags = []
    if page["status"] != "ok":
        flags.append(page["status"])
    valid = sum(v is not None for v in values)
    if valid < n:
        flags.append("incomplete_article_data")
    valid_totals = sum(v is not None and v > 0 for v in totals)
    if valid_totals < n:
        flags.append("incomplete_project_data")
    created = page.get("created_at", "") or ""
    if created and created[:7] >= months[0]:
        flags.append("article_created_during_period")
    if page.get("mapping") == "manual":
        flags.append("manual_mapping_review_required")
    paired = [(v, t) for v, t in zip(values, totals) if v is not None and t is not None and t > 0]
    if any(v > t for v, t in paired):
        flags.append("inconsistent_article_project_counts")
    shares = [v / t * 1e6 if v is not None and t is not None and t > 0 and v <= t else None for v, t in zip(values, totals)]
    latest = values[-12:]
    latest_sum = sum(latest) if len(latest) == 12 and all(v is not None for v in latest) else None
    out = {"language": page["language"], "article": page.get("title"), "status": page["status"], "observed_months": valid, "expected_months": n, "coverage_pct": round(valid / n * 100, 2), "observed_views": sum(v for v in values if v is not None) if valid else None, "latest_12m_views": latest_sum, "yoy_pct": None, "normalized_yoy_pct": None, "latest_share_per_million": None, "median_monthly_yoy_pct": None, "positive_month_pairs": None, "paired_months": None, "leave_one_pair_out_yoy_range": None, "peak_pair_excluded_yoy_pct": None, "peak_month": None, "peak_share_pct": None, "spike_months": [], "stability": "insufficient", "flags": flags}
    if n < 24:
        flags.append("less_than_24_months")
        return out, shares
    previous, current = values[-24:-12], values[-12:]
    ptotal, ctotal = totals[-24:-12], totals[-12:]
    if any(v is None for v in previous + current):
        return out, shares
    before, after = sum(previous), sum(current)
    yoy = growth(before, after)
    out["yoy_pct"] = yoy
    if before == 0:
        flags.append("zero_baseline")
        return out, shares
    if before < 1200:
        flags.append("low_baseline")
    if all(t is not None and t > 0 for t in ptotal + ctotal) and "inconsistent_article_project_counts" not in flags:
        pshare, cshare = before / sum(ptotal), after / sum(ctotal)
        out["latest_share_per_million"] = cshare * 1e6
        out["normalized_yoy_pct"] = growth(pshare, cshare)
        if sign(yoy) != sign(out["normalized_yoy_pct"]):
            flags.append("raw_normalized_direction_differs")
    pairs = [growth(a, b) for a, b in zip(previous, current) if a > 0]
    out["median_monthly_yoy_pct"] = statistics.median(pairs) if pairs else None
    out["positive_month_pairs"] = sum(v > 0 for v in pairs)
    out["paired_months"] = len(pairs)
    sensitivity = [growth(before - a, after - b) for a, b in zip(previous, current) if before - a > 0]
    if sensitivity:
        out["leave_one_pair_out_yoy_range"] = [min(sensitivity), max(sensitivity)]
        if any(sign(v) != sign(yoy) for v in sensitivity):
            flags.append("direction_sensitive_to_one_pair")
    peak_index = max(range(12), key=lambda i: current[i])
    out["peak_pair_excluded_yoy_pct"] = growth(before - previous[peak_index], after - current[peak_index])
    out["peak_month"] = months[-12:][peak_index]
    out["peak_share_pct"] = current[peak_index] / after * 100 if after else None
    # Diagnostic only: seasonality can also cause high values; no automatic deletion.
    window = previous + current
    median = statistics.median(window)
    mad = statistics.median(abs(v - median) for v in window)
    threshold = median + max(6 * 1.4826 * mad, 2 * max(median, 1))
    out["spike_months"] = [m for m, v in zip(months[-24:], window) if v > threshold]
    if out["spike_months"]:
        flags.append("possible_spikes")
    if out["peak_share_pct"] is not None and out["peak_share_pct"] > 25:
        flags.append("concentrated_in_peak_month")
    insufficient = {"article_created_during_period", "zero_baseline", "inconsistent_article_project_counts"}
    if insufficient.intersection(flags):
        out["stability"] = "insufficient"
    elif flags:
        out["stability"] = "caution"
    else:
        out["stability"] = "consistent"
    return out, shares


def prioritize(metrics, criterion="balanced"):
    """No opaque score: explicit sorting for promising, comparable positive signals."""
    eligible = [m for m in metrics if m["stability"] == "consistent" and m["yoy_pct"] is not None and m["yoy_pct"] > 0 and m["normalized_yoy_pct"] is not None and m["normalized_yoy_pct"] > 0]
    keys = {"balanced": lambda m: (m["normalized_yoy_pct"], m["latest_12m_views"]), "growth": lambda m: (m["yoy_pct"], m["latest_12m_views"]), "volume": lambda m: (m["latest_12m_views"], m["normalized_yoy_pct"])}
    ranked = sorted(eligible, key=keys[criterion], reverse=True)
    return {"criterion": criterion, "rule": "Only complete, consistently positive raw and normalized signals; rank by " + {"balanced": "normalized growth, then volume", "growth": "raw growth, then volume", "volume": "volume, then normalized growth"}[criterion], "research_next": [m["language"] for m in ranked], "review_first": [m["language"] for m in metrics if m["stability"] != "consistent"], "note": "A research shortlist, not a forecast, country ranking, market-size estimate or launch recommendation."}
