"""Predictions from the Statistical analysis parameters, after a backtest.

1. Candidates: the parameters the Statistical analysis tab rates "Robust" for a group
   (Fama-MacBeth slope with p <= 0.05, q <= 0.10, same sign in both halves). A group with
   no Robust parameter uses its significant ones (p <= 0.05) instead, labelled as such.
2. Unique: versions of one measure count once (Alpha / Alpha (Annualized) ...), and,
   strongest first, a parameter moving with one already kept (|rank corr| > UNIQUE_RHO)
   is dropped.
3. Backtest, parameter years TEST_FIRST..last full year: in each year Y, funds are split
   into fifths by the parameter (as in the Statistical analysis quintiles); each fifth's
   average next-year excess over the Nifty 50 comes only from the years before Y. A fund
   is called to beat the Nifty 50 by TARGET%+ if its fifth's average is >= TARGET. Hit
   ratio = right calls (beat / not beat) / all funds. Naive: the group's own past average
   decides the same call for every fund.
4. Feasible = hit ratio above the cut on MIN_CALLS+ calls, and above the naive call. Prediction for the next year:
   each feasible parameter puts the fund in a fifth of its group's latest year; that
   fifth's historical average next-year excess over the Nifty 50 (the Statistical
   analysis quintile figure) is weighted by the parameter's |t|.
"""

import numpy as np
import pandas as pd

from category_analysis import family

TEST_FIRST = 2020            # backtest parameter years from here (returns from TEST_FIRST + 1)
MIN_PAST_YEARS = 8           # past years needed before a backtest year
HIT_RATIO = 0.60             # default cut; the page offers others
CUTS = (0.55, 0.60, 0.65)
MIN_CALLS = 30
TARGET = 3.0                 # the question: does the fund beat the Nifty 50 by 3%+ next year?
TOLERANCES = (1, 2, 3, 5)    # hit ratio 2: the prediction is right if within this many points of the actual
TOLERANCE = 3                # default tolerance on the page and in the workbook
UNIQUE_RHO = 0.80
QUINTILE_MIN_FUNDS = 10
STATUS = ["Unique", "Version of", "Moves with"]
# where candidates come from: the Robust parameters, or - if a group has none - the significant ones (p <= 0.05)
TIERS = ["Robust", "Significant (p <= 0.05), not Robust", "none"]


def fifths(values):
    """1..5 by value within one cross-section (ties broken by order, as the Statistical
    analysis does); None if too few funds."""
    v = values.dropna()
    if len(v) < QUINTILE_MIN_FUNDS or v.nunique() < 5:
        return None
    return (pd.qcut(v.rank(method="first"), 5, labels=False) + 1).astype(int)


def select(candidates, rows, parameters):
    """Status of each candidate: (0 kept | 1 version of | 2 moves with, other)."""
    status, best = {}, {}
    for _, r in candidates.sort_values("p").iterrows():
        k = family(r["parameter"])
        if k in best:
            status[r["parameter"]] = (1, best[k])
        else:
            best[k] = r["parameter"]
    corr = rows[parameters].rank().corr(min_periods=30).abs()
    kept = []
    for p in best.values():
        twin = next((q for q in kept if np.isfinite(corr.at[p, q]) and corr.at[p, q] > UNIQUE_RHO), None)
        if twin:
            status[p] = (2, twin)
        else:
            status[p] = (0, None)
            kept.append(p)
    return status, kept


def fifth_history(rows, parameter):
    """Per parameter year: the funds with their fifth (1 = lowest values) and excess."""
    out = {}
    for y, fr in rows.groupby("param_year"):
        pair = fr[["scheme_name", parameter, "excess"]].dropna()
        k = fifths(pair[parameter])
        if k is not None:
            out[int(y)] = pair.assign(fifth=k)
    return out


def backtest(rows, parameter, last_year):
    """Per test year Y: each fifth's average next-year excess from the years before Y
    only; a fund's predicted excess = its fifth's average; call 'beats the Nifty 50 by
    TARGET+' if that is >= TARGET. Naive call: the group's past average for every fund."""
    hist = fifth_history(rows, parameter)
    year_mean = rows.groupby("param_year")["excess"].mean()
    years, detail = [], []
    for y in range(TEST_FIRST, last_year + 1):
        past = [t for t in hist if t < y]
        if len(past) < MIN_PAST_YEARS or y not in hist:
            continue
        avg = pd.concat([hist[t].groupby("fifth")["excess"].mean() for t in past], axis=1).mean(axis=1)
        naive_avg = float(year_mean[year_mean.index < y].mean())
        fr = hist[y]
        pred = fr["fifth"].map(avg)
        call, actual, naive = pred >= TARGET, fr["excess"] >= TARGET, naive_avg >= TARGET
        years.append({"year": y, "past_years": len(past), "fifth_avg": [float(avg.get(q, np.nan)) for q in range(1, 6)],
                      "naive_avg": naive_avg, "funds": len(fr), "called": int(call.sum()), "beat": int(actual.sum()),
                      "hits": int((call == actual).sum()), "naive_hits": int((actual == naive).sum()),
                      "called_right": int((call & actual).sum()),
                      **other_hits(pred.to_numpy(), np.full(len(fr), naive_avg), fr["excess"].to_numpy())})
        for (_, x), pv, c in zip(fr.iterrows(), pred, call):
            detail.append({"year": y, "fund": x["scheme_name"], "value": x[parameter], "fifth": int(x["fifth"]),
                           "pred": float(pv), "excess": x["excess"], "naive_avg": naive_avg})
    tot = lambda k: sum(t[k] for t in years)
    out = {"years": years, "calls": tot("funds"), "hits": tot("hits"), "naive": tot("naive_hits"),
           "called": tot("called"), "called_right": tot("called_right"), "beat": tot("beat"), "detail": detail}
    for k in OTHER_KEYS:
        out[k] = tot(k)
    return out


OTHER_KEYS = [f"tol{t}" for t in TOLERANCES] + [f"naive_tol{t}" for t in TOLERANCES] + ["ge", "naive_ge", "abs_err", "naive_abs_err",
                                                                                         "dev", "naive_dev"]
# baskets of predicted excess over the Nifty 50 (% points): below 0, 0-1, 1-2, ..., 9-10, 10 and above
BASKETS = [-np.inf] + list(range(0, 11)) + [np.inf]


def other_hits(pred, naive, actual):
    """The two other hit ratios: within +/- t points of the actual, and actual >= predicted.
    Also the summed absolute errors (for the average miss)."""
    e, en = np.abs(actual - pred), np.abs(actual - naive)
    out = {f"tol{t}": int((e <= t).sum()) for t in TOLERANCES}
    out |= {f"naive_tol{t}": int((en <= t).sum()) for t in TOLERANCES}
    out |= {"ge": int((actual >= pred).sum()), "naive_ge": int((actual >= naive).sum()),
            "abs_err": float(e.sum()), "naive_abs_err": float(en.sum()),
            "dev": float((actual - pred).sum()), "naive_dev": float((actual - naive).sum())}
    return out


def basket_label(lo, hi):
    if not np.isfinite(lo):
        return f"below {hi:g}%"
    if not np.isfinite(hi):
        return f"{lo:g}% and above"
    return f"{lo:g}-{hi:g}%"


def baskets(pred, actual):
    """Predictions grouped by predicted excess: count, average predicted, average actual, average
    deviation (actual - predicted), and how many actually beat the Nifty 50 by TARGET%+."""
    pred, actual = np.asarray(pred, dtype=float), np.asarray(actual, dtype=float)
    out = []
    for lo, hi in zip(BASKETS[:-1], BASKETS[1:]):
        m = (pred >= lo) & (pred < hi)
        n = int(m.sum())
        out.append({"label": basket_label(lo, hi), "lo": lo, "hi": hi, "n": n,
                    "sum_pred": float(pred[m].sum()), "sum_actual": float(actual[m].sum()),
                    "beat": int((actual[m] >= TARGET).sum()), "abs_dev": float(np.abs(actual[m] - pred[m]).sum())})
    return out


def live_check(latest, parameter, quintile_avg, group_avg):
    """The latest year's fifths, predicted with the all-years fifth averages, against the
    partial-year excess."""
    fr = latest[["scheme_name", parameter, "live_excess"]].dropna()
    k = fifths(fr[parameter])
    if k is None or not quintile_avg:
        return None
    pred = k.map(lambda q: quintile_avg[q - 1])
    call, actual, naive = pred >= TARGET, fr["live_excess"] >= TARGET, group_avg >= TARGET
    detail = [{"fund": x["scheme_name"], "value": x[parameter], "fifth": int(q), "pred": float(pv), "excess": x["live_excess"]}
              for (_, x), q, pv in zip(fr.iterrows(), k, pred)]
    return {"calls": len(fr), "hits": int((call == actual).sum()), "naive": int((actual == naive).sum()),
            "called": int(call.sum()), "called_right": int((call & actual).sum()), "beat": int(actual.sum()),
            "group_avg": group_avg, "detail": detail,
            **other_hits(pred.to_numpy(dtype=float), np.full(len(fr), group_avg), fr["live_excess"].to_numpy(dtype=float))}


def run(data, univariate):
    full = data.panel[data.panel["param_year"].isin(data.full_years)].dropna(subset=["excess"])
    latest_year = data.partial_year or max(data.full_years)
    latest = data.panel[data.panel["param_year"] == latest_year].copy()
    latest["live_excess"] = latest["fund_return"] - data.nifty_partial if data.nifty_partial is not None else np.nan
    last_full = max(data.full_years)
    out = {"latest_year": latest_year, "target_year": latest_year + 1, "test": (TEST_FIRST, last_full),
           "live_label": data.partial_label, "groups": []}
    for group, gu in univariate.groupby("group", sort=False):
        if group.startswith("All Funds,"):        # the within-category transform is not a fund universe
            continue
        rows = full if group == "All Funds" else full[full["category"] == group]
        members = latest if group == "All Funds" else latest[latest["category"] == group]
        candidates, tier = gu[gu["verdict"] == "Robust"], TIERS[0]
        if candidates.empty:           # no Robust parameter: fall back to the significant ones, labelled as the weaker tier
            candidates, tier = gu[(gu["status"] == "ok") & (gu["p"] <= 0.05)], TIERS[1]
        if candidates.empty:
            tier = TIERS[2]
        g = {"name": group, "robust": int((gu["verdict"] == "Robust").sum()), "candidates": len(candidates), "tier": tier,
             "significant": int(((gu["status"] == "ok") & (gu["p"] <= 0.05)).sum()),
             "funds": int(rows["scheme_id"].nunique()), "obs": len(rows), "members": members, "params": [],
             "rows": rows, "group_avg": float(rows.groupby("param_year")["excess"].mean().mean())}
        if len(candidates):
            status, kept = select(candidates, rows, data.parameters)
            for _, r in candidates.sort_values("p").iterrows():
                p = r["parameter"]
                rec = {"parameter": p, "status": status[p], "slope": r["slope"], "se": r["se"], "t": r["t"],
                       "p": r["p"], "q": r["q"], "ic": r["ic"], "share_positive": r["share_positive"],
                       "first_half": r["first_half"], "second_half": r["second_half"], "years": int(r["years"]),
                       "quintiles": r["quintiles"]["excess"] if isinstance(r["quintiles"], dict) else None,
                       "quintile_years": r["quintiles"]["years"] if isinstance(r["quintiles"], dict) else None}
                rec["yearly"] = r["yearly"]
                if status[p][0] == 0:
                    rec["backtest"] = backtest(rows, p, last_full)
                    rec["live"] = live_check(members, p, rec["quintiles"], g["group_avg"])
                    d = rec["backtest"]["detail"]
                    rec["baskets"] = baskets([x["pred"] for x in d], [x["excess"] for x in d])
                    # the latest cross-section: each fund's fifth, and each fifth's value range
                    v = members[["scheme_id", p]].dropna()
                    k = fifths(v[p])
                    rec["latest"] = {} if k is None else {sid: (float(val), int(q)) for sid, val, q in
                                                         zip(v["scheme_id"], v[p], k)}
                    rec["latest_bounds"] = [] if k is None else [
                        (float(v[p][k == q].min()), float(v[p][k == q].max()), int((k == q).sum())) for q in range(1, 6)]
                g["params"].append(rec)
        out["groups"].append(g)
    return out


def measure(b, how="call", tol=TOLERANCE):
    """(right, naive right) under one hit-ratio definition."""
    if how == "diff":
        return b[f"tol{tol}"], b[f"naive_tol{tol}"]
    if how == "ge":
        return b["ge"], b["naive_ge"]
    return b["hits"], b["naive"]


def predict(group, cut=HIT_RATIO, how="call", tol=TOLERANCE):
    """Feasible parameters at a cut (under one hit-ratio definition), weights by |t|, and each fund's prediction."""
    def ok(r):
        b = r.get("backtest")
        if not b or b["calls"] < MIN_CALLS or not r["quintiles"] or not r["latest"]:
            return False
        right, naive = measure(b, how, tol)
        return right / b["calls"] > cut and right > naive
    feas = [r for r in group["params"] if r["status"][0] == 0 and ok(r)]
    total = sum(abs(r["t"]) for r in feas)
    weights = {r["parameter"]: abs(r["t"]) / total for r in feas}
    preds = {}
    for sid in group["members"]["scheme_id"]:
        parts = [(weights[r["parameter"]], r["quintiles"][r["latest"][sid][1] - 1]) for r in feas if sid in r["latest"]]
        tw = sum(w for w, _ in parts)
        if parts:
            preds[sid] = (sum(w * e for w, e in parts) / tw, len(parts))
    return feas, weights, preds


def run_parameters(data, univariate, parameters):
    """The same backtest, live check and next-year prediction for a chosen list of parameters
    (e.g. the 'previous parameters'), in every group, whatever the Statistical analysis rated them."""
    full = data.panel[data.panel["param_year"].isin(data.full_years)].dropna(subset=["excess"])
    latest_year = data.partial_year or max(data.full_years)
    latest = data.panel[data.panel["param_year"] == latest_year].copy()
    latest["live_excess"] = latest["fund_return"] - data.nifty_partial if data.nifty_partial is not None else np.nan
    last_full = max(data.full_years)
    out = {"latest_year": latest_year, "target_year": latest_year + 1, "test": (TEST_FIRST, last_full),
           "live_label": data.partial_label, "groups": []}
    for group, gu in univariate.groupby("group", sort=False):
        if group.startswith("All Funds,"):
            continue
        rows = full if group == "All Funds" else full[full["category"] == group]
        members = latest if group == "All Funds" else latest[latest["category"] == group]
        g = {"name": group, "funds": int(rows["scheme_id"].nunique()), "obs": len(rows), "members": members, "rows": rows,
             "group_avg": float(rows.groupby("param_year")["excess"].mean().mean()), "params": []}
        for p in parameters:
            u = gu[gu["parameter"] == p]
            r = u.iloc[0] if len(u) else None
            q = r["quintiles"] if r is not None and isinstance(r["quintiles"], dict) else None
            rec = {"parameter": p, "status": (0, None),
                   "slope": r["slope"] if r is not None else np.nan, "t": r["t"] if r is not None else np.nan,
                   "p": r["p"] if r is not None else np.nan, "q": r["q"] if r is not None else np.nan,
                   "ic": r["ic"] if r is not None else np.nan, "verdict": r["verdict"] if r is not None else "",
                   "quintiles": q["excess"] if q else None, "quintile_years": q["years"] if q else None,
                   "backtest": backtest(rows, p, last_full)}
            rec["live"] = live_check(members, p, rec["quintiles"], g["group_avg"])
            v = members[["scheme_id", p]].dropna()
            k = fifths(v[p])
            rec["latest"] = {} if k is None else {sid: (float(val), int(f)) for sid, val, f in zip(v["scheme_id"], v[p], k)}
            rec["latest_bounds"] = [] if k is None else [
                (float(v[p][k == f].min()), float(v[p][k == f].max()), int((k == f).sum())) for f in range(1, 6)]
            d = rec["backtest"]["detail"]
            rec["baskets"] = baskets([x["pred"] for x in d], [x["excess"] for x in d])
            g["params"].append(rec)
        out["groups"].append(g)
    return out


# The parameters from the earlier correlation study ("previous parameters"), with the correlation it reported.
PREVIOUS = [("Value at Risk", "Value at Risk", 0.62), ("Covariance", "Covariance", 0.47),
            ("Standard Deviation", "Std Dev (Annualized)", 0.47), ("Semi Deviation", "Semi Dev (Annualized)", 0.40),
            ("Point-to-Point Return", "Return (Cumulative)", -0.44), ("Efficiency Ratio", "Efficiency Ratio (arith) (Annualized)", -0.52),
            ("Down Capture Return", "Down Capture Return", -0.59), ("Longest Down-Streak Return", "Longest Down-Streak Return", -0.65),
            ("Average Drawdown", "Average Drawdown", -0.68)]


def basket_of(value):
    """The basket label of one predicted excess."""
    for lo, hi in zip(BASKETS[:-1], BASKETS[1:]):
        if lo <= value < hi:
            return basket_label(lo, hi)
    return ""
