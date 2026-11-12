"""Parameters vs excess return over the Nifty 50, for a category or all funds.

The fund-level method (fund_analysis.py) applied to a group: every fund-year in the
group is pooled, so funds with a short history still count with whatever years they
have. For each parameter:

* the Spearman correlation between the value in calendar year T and the excess
  return over the Nifty 50 in T+1, across all the group's fund-years;
* the pooled values cut into RANGES equal-count ranges (low / middle / high) and the
  average next-year excess in each.

Expected excess for the next calendar year: parameters with p < MAX_P and
|correlation| >= threshold give the average next-year excess of the range a value is
in; weighted by |correlation|, near-duplicates counted once. Applied to the group's
typical fund (median latest values) and to every fund's own latest values.

Testing lives in stats_prediction.py (Statistical analysis parameters, backtested).
"""

import re

import numpy as np
import pandas as pd
from scipy import stats

from fund_analysis import RANGES, locate, own_ranges  # noqa: F401

MIN_OBS = 30                  # fund-years a group needs for a parameter
MAX_P = 0.05                  # a parameter enters only if its pooled correlation is significant
MIN_CORRELATION = 0.15        # default |correlation| cut-off (adjustable on the page)
THRESHOLDS = (0.10, 0.15, 0.20, 0.30)
DUPLICATE_RHO = 0.90          # parameters moving this closely across the group count as one
VARIANTS = r"\((Annualized|arith|geo|non-excess return)\)"
ALL = "All funds"


def groups(frame):
    """(name, rows) for all funds and each category."""
    yield ALL, frame
    for category, rows in frame.groupby("category"):
        yield category, rows


def fit(frame, parameters):
    """Per parameter: pooled correlation, p-value, ranges; plus duplicate clusters."""
    out = {}
    for parameter in parameters:
        pair = frame[["param_year", parameter, "excess"]].dropna()
        if len(pair) < MIN_OBS or pair[parameter].nunique() < RANGES + 1:
            out[parameter] = {"n": len(pair), "rho": np.nan, "p": np.nan, "ranges": None}
            continue
        rho, p = stats.spearmanr(pair[parameter], pair["excess"])
        out[parameter] = {"n": len(pair), "rho": rho, "p": p, "ranges": own_ranges(pair, parameter)}
    corr = frame[parameters].rank().corr(min_periods=MIN_OBS).abs()
    cluster, next_id = {}, 0
    for p in parameters:
        if p in cluster:
            continue
        cluster[p] = next_id
        for q in parameters:
            if q not in cluster and np.isfinite(corr.at[p, q]) and corr.at[p, q] > DUPLICATE_RHO:
                cluster[q] = next_id
        next_id += 1
    for p in parameters:
        out[p]["cluster"] = cluster[p]
    return out


def chosen(fitted, threshold):
    """Parameters used at a threshold, with |correlation| weights (one per cluster)."""
    best = {}
    for p, f in fitted.items():
        if f["ranges"] is None or not (f["p"] < MAX_P and abs(f["rho"]) >= threshold):
            continue
        c = f["cluster"]
        if c not in best or abs(f["rho"]) > abs(fitted[best[c]]["rho"]):
            best[c] = p
    use = sorted(best.values(), key=lambda p: -abs(fitted[p]["rho"]))
    total = sum(abs(fitted[p]["rho"]) for p in use)
    return {p: abs(fitted[p]["rho"]) / total for p in use}


def range_excess(f, value):
    idx, outside = locate(f["ranges"], value)
    return (None, None, False) if idx is None else (f["ranges"][idx]["avg_excess"], idx, outside)


def expected(fitted, weights, values):
    """Expected excess for one set of latest values; weights re-scaled over the
    parameters the fund has a value for."""
    parts = []
    for p, w in weights.items():
        v = values.get(p)
        if v is None or not np.isfinite(v):
            continue
        ex, _, _ = range_excess(fitted[p], v)
        if ex is not None:
            parts.append((w, ex))
    total = sum(w for w, _ in parts)
    return (sum(w * ex for w, ex in parts) / total, len(parts)) if parts else (np.nan, 0)


def family(parameter):
    """Name with the variant tags removed: Alpha and Alpha (Annualized) share one."""
    name = re.sub(VARIANTS, "", parameter).replace(" Population", "").replace("R-Squared", "R2")
    return " ".join(name.split())


def run(data):
    full = data.panel[data.panel["param_year"].isin(data.full_years)].dropna(subset=["excess"]).copy()
    latest_year = data.partial_year or max(data.full_years)
    latest = data.panel[data.panel["param_year"] == latest_year].copy()
    latest["live_excess"] = latest["fund_return"] - data.nifty_partial if data.nifty_partial is not None else np.nan
    params = data.parameters
    out = {"groups": [], "latest_year": latest_year, "target_year": latest_year + 1, "live_label": data.partial_label}
    for name, rows in groups(full):
        members = latest if name == ALL else latest[latest["category"] == name]
        out["groups"].append({
            "name": name, "fitted": fit(rows, params), "typical": {p: members[p].median() for p in params},
            "funds": rows["scheme_id"].nunique(), "obs": len(rows), "first": int(rows["param_year"].min()),
            "last": int(rows["param_year"].max()), "avg_excess": float(rows["excess"].mean()), "members": members})
    return out
