"""Parameters vs excess return over the Nifty 50, from each fund's own history.

For every fund and parameter, the fund's value in calendar year T is paired with
the fund's own excess return over the Nifty 50 in calendar year T+1 (fund return
minus the Nifty 50's return that year):

* the correlation between the two across the fund's years (Spearman);
* the fund's own values cut into RANGES equal-count ranges (low / middle / high),
  and the fund's average next-year excess return in each;
* where the fund's latest value sits.

Expected excess return for the next calendar year: every parameter with
|correlation| >= MIN_CORRELATION gives the fund's average next-year excess in the
range its latest value is in; these are averaged, weighted by |correlation|, with
near-duplicate parameters counted once. No category or peer data is used.
"""

import numpy as np
import pandas as pd
from scipy import stats

from stats_analysis import bh_qvalues

MIN_FUND_YEARS = 8          # years of the fund's own history needed
RANGES = 3                  # the fund's own values cut into low / middle / high
MIN_CORRELATION = 0.30      # default: a parameter enters the prediction above this |correlation|
DUPLICATE_RHO = 0.90        # parameters moving this closely in the fund's history count as one
STRONG_P, MODERATE_P = 0.05, 0.10
LABELS = ["Strong", "Moderate", "Weak", "Too little history"]


def wilson(beats, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = beats / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def own_ranges(pair, parameter):
    """The fund's own values cut into RANGES equal-count ranges, with the fund's
    average excess return over the Nifty 50 in the following year for each."""
    # ties broken by year, so the split is reproducible (the dashboard re-derives it)
    ordered = pair.sort_values([parameter, "param_year"], kind="mergesort").reset_index(drop=True)
    out = []
    for idx in np.array_split(np.arange(len(ordered)), RANGES):
        g = ordered.iloc[idx]
        out.append({"low": g[parameter].min(), "high": g[parameter].max(), "n": len(g),
                    "avg_excess": g["excess"].mean(), "years": g["param_year"].astype(int).tolist()})
    return out


def locate(ranges, value):
    """Index of the range a value belongs to, and whether it lies outside the fund's history."""
    if value is None or not np.isfinite(value):
        return None, False
    outside = value < ranges[0]["low"] or value > ranges[-1]["high"]
    for i, r in enumerate(ranges[:-1]):
        # boundary between this range and the next: midway between their values
        if value <= (r["high"] + ranges[i + 1]["low"]) / 2:
            return i, outside
    return len(ranges) - 1, outside


def label(p):
    if not np.isfinite(p):
        return LABELS[3]
    return LABELS[0] if p <= STRONG_P else LABELS[1] if p <= MODERATE_P else LABELS[2]


def analyse_fund(frame, parameters, latest_row):
    frame = frame.sort_values("param_year")
    rows, ranges = [], {}
    for parameter in parameters:
        pair = frame[["param_year", parameter, "excess"]].dropna()
        n = len(pair)
        rec = {"parameter": parameter, "years": n, "rho": np.nan, "p": np.nan}
        current = latest_row.get(parameter) if latest_row is not None else None
        rec["current"] = current if current is not None and np.isfinite(current) else np.nan
        if n >= MIN_FUND_YEARS and pair[parameter].nunique() >= RANGES + 1 and pair["excess"].nunique() >= 4:
            rho, p = stats.spearmanr(pair[parameter], pair["excess"])
            rec.update(rho=rho, p=p)
            rg = own_ranges(pair, parameter)
            ranges[parameter] = rg
            idx, outside = locate(rg, rec["current"])
            if idx is not None:
                r = rg[idx]
                rec.update(range=idx + 1, outside=outside, range_low=r["low"], range_high=r["high"],
                           range_n=r["n"], range_excess=r["avg_excess"],
                           range_years=", ".join(str(y) for y in r["years"]))
        rows.append(rec)
    table = pd.DataFrame(rows)
    table["q"] = bh_qvalues(table["p"])
    table["label"] = table["p"].map(label)
    # Near-duplicates: parameters whose values moved together in this fund's history.
    values = frame[parameters]
    corr = values.rank().corr(min_periods=MIN_FUND_YEARS).abs()
    cluster, next_id = {}, 0
    for p in parameters:
        if p in cluster:
            continue
        cluster[p] = next_id
        for q in parameters:
            if q not in cluster and np.isfinite(corr.at[p, q]) and corr.at[p, q] > DUPLICATE_RHO:
                cluster[q] = next_id
        next_id += 1
    table["cluster"] = table["parameter"].map(cluster)
    return table, ranges


def predict(table, threshold=MIN_CORRELATION):
    """Expected next-year excess over the Nifty 50: the fund's average next-year excess
    in the range of each parameter's latest value, weighted by |correlation|."""
    use = table[(table["rho"].abs() >= threshold) & table["range_excess"].notna()].copy() \
        if "range_excess" in table else table.iloc[0:0]
    if use.empty:
        return use, None
    use = use.loc[use.groupby("cluster")["rho"].apply(lambda s: s.abs().idxmax())]
    use["weight"] = use["rho"].abs() / use["rho"].abs().sum()
    use["contribution"] = use["weight"] * use["range_excess"]
    return use.sort_values("weight", ascending=False), {
        "parameters": len(use), "expected_excess": float(use["contribution"].sum())}


def run(data):
    full = data.panel[data.panel["param_year"].isin(data.full_years)].dropna(subset=["excess"]).copy()
    latest_year = data.partial_year or max(data.full_years)
    latest_frame = data.panel[data.panel["param_year"] == latest_year]
    latest = {row["scheme_id"]: row for _, row in latest_frame.iterrows()}
    tables, summary, used = [], [], []
    for fund_id, frame in full.groupby("scheme_id"):
        name, category = frame["scheme_name"].iloc[0], frame["category"].iloc[0]
        table, _ = analyse_fund(frame, data.parameters, latest.get(fund_id))
        table.insert(0, "scheme_id", fund_id)
        table.insert(1, "fund", name)
        table.insert(2, "category", category)
        table = table.sort_values("rho", key=lambda s: -s.abs().fillna(-1)).reset_index(drop=True)
        tables.append(table)
        contrib, result = predict(table)
        summary.append({"scheme_id": fund_id, "fund": name, "category": category, "years": len(frame),
                        "first_year": int(frame["param_year"].min()), "last_year": int(frame["param_year"].max()),
                        "parameters": result["parameters"] if result else 0,
                        "avg_excess": frame["excess"].mean(),
                        "expected_excess": result["expected_excess"] if result else np.nan})
        if result:
            used.append(contrib)
    years = [y + 1 for y in data.full_years]
    return {"table": pd.concat(tables, ignore_index=True), "summary": pd.DataFrame(summary),
            "used": pd.concat(used, ignore_index=True) if used else pd.DataFrame(),
            "latest_year": latest_year, "target_year": latest_year + 1,
            "nifty_average": float(data.nifty.reindex(years).mean()), "nifty_years": (min(years), max(years))}
