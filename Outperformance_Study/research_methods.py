"""Research methods: predicting a fund's excess return over the Nifty 50 with approaches
from the fund-performance literature, tested on the same data and the same question
("does the fund beat the Nifty 50 by 3%+ next calendar year?").

Two-part prediction (excess over the Nifty 50 = category part + fund part):
* category part: the category's average yearly excess over the Nifty 50 in the years
  before (equal weight per year);
* fund part: the fund's expected return relative to its category's average that year,
  from one method:
    mom1     last year's return relative to the category (fund momentum; Carhart 1997,
             Kaniel et al. 2023)
    mom3     the same averaged over the last 3 years
    alpha3   3-year average Alpha (Annualized)
    ir3      3-year average Information Ratio (arith)
    lowr2    R2 against the benchmark (low = more active; Amihud & Goyenko 2013)
    sel      low R2 + high Alpha together (Amihud & Goyenko's double sort, as one score)
    ridge    a ridge regression on all of the above (combining characteristics; DeMiguel
             et al. 2023, Kaniel et al. 2023), features standardised within category-year
  For a single signal, funds are put in fifths within their category each year and the
  fund part is the average relative return of that fifth in the years before.

Walk-forward backtest on parameter years TEST_FIRST..last full year: every number used
for year Y comes from the years before Y. Live check: latest parameter year -> the
partial return period.
"""

import numpy as np
import pandas as pd
from scipy import stats

TEST_FIRST = 2020
TARGET = 3.0
HIT_RATIO = 0.60
MIN_CALLS = 30
MIN_PAST_YEARS = 5
MIN_FUNDS = 5               # funds a category needs in a year to be split into fifths
RIDGE = 0.10                # ridge penalty, as a share of the training rows
Z_CAP = 3.0
ALPHA, IR, R2, TE = "Alpha (Annualized)", "Information Ratio (arith) (Annualized)", "R2", "Tracking Error (Annualized)"

METHODS = [
    ("mom1", "1-year momentum", "Last year's return relative to the category average. Funds that did well relative to "
                                "their peers last year are expected to keep doing so (Carhart 1997; Kaniel et al. 2023)."),
    ("mom3", "3-year momentum", "The same, averaged over the last three years: a steadier read of a fund's record."),
    ("alpha3", "3-year average Alpha", "Alpha (Annualized) averaged over the last three parameter years."),
    ("ir3", "3-year average Information Ratio", "Information Ratio (arith) averaged over the last three parameter years: "
                                                "return over the benchmark per unit of tracking error."),
    ("lowr2", "Low R² (more active)", "R² against the benchmark: a low R² means the fund departs more from the index "
                                      "(Amihud & Goyenko 2013 find low-R² funds do better)."),
    ("sel", "Low R² + high Alpha", "Amihud & Goyenko's selectivity: the average of the fund's within-category rank by Alpha "
                                   "and by low R² - active funds that also had high alpha."),
    ("ridge", "Combined (ridge regression)", "A ridge regression of next-year relative return on all six signals together, "
                                             "each standardised within category and year, refitted every year on the past only "
                                             "(the combining idea of DeMiguel et al. 2023 and Kaniel et al. 2023)."),
]
FEATURES = ["mom1", "mom3", "alpha3", "ir3", "lowr2", "sel"]


def prepare(data):
    """Fund-years with the target (excess over the Nifty 50 next year; the partial period
    for the latest year), its category-relative part, and every method's signal."""
    latest_year = data.partial_year or max(data.full_years)
    p = data.panel[data.panel["param_year"].isin(data.full_years + [latest_year])].copy()
    p["target"] = np.where(p["param_year"] == latest_year, p["fund_return"] - data.nifty_partial, p["excess"])
    keys = ["param_year", "category"]
    p["cat_mean"] = p.groupby(keys)["target"].transform("mean")
    p["rel"] = p["target"] - p["cat_mean"]
    p = p.sort_values(["scheme_id", "param_year"]).reset_index(drop=True)
    g = p.groupby("scheme_id")

    def lagged(col, k):
        s = g[col].shift(k)
        ok = (p["param_year"] - g["param_year"].shift(k)) == k
        return s.where(ok)

    # momentum known at the end of parameter year T: relative returns realised in T, T-1, T-2
    p["mom1"] = lagged("rel", 1)
    p["mom3"] = pd.concat([lagged("rel", k) for k in (1, 2, 3)], axis=1).mean(axis=1, skipna=False)
    p["alpha3"] = pd.concat([p[ALPHA], lagged(ALPHA, 1), lagged(ALPHA, 2)], axis=1).mean(axis=1, skipna=False)
    p["ir3"] = pd.concat([p[IR], lagged(IR, 1), lagged(IR, 2)], axis=1).mean(axis=1, skipna=False)
    p["lowr2"] = -p[R2]
    ra = p.groupby(keys)[ALPHA].rank(pct=True)
    rr = p.groupby(keys)[R2].rank(pct=True)
    p["sel"] = (ra + (1 - rr)) / 2
    return p, latest_year


def fifth(values):
    """1..5 within one category-year (ties by order); NaN where too few funds."""
    v = values.dropna()
    out = pd.Series(np.nan, index=values.index)
    if len(v) >= MIN_FUNDS:
        r = v.rank(method="first")
        out.loc[v.index] = np.floor((r - 1) * 5 / len(v)) + 1
    return out


def add_fifths(p, col):
    return p.groupby(["param_year", "category"], group_keys=False)[col].apply(fifth)


def zscores(p, cols):
    def z(s):
        sd = s.std(ddof=1)
        return ((s - s.mean()) / sd).clip(-Z_CAP, Z_CAP) if sd and np.isfinite(sd) else s * np.nan
    return p.groupby(["param_year", "category"])[cols].transform(z)


def ridge_fit(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    pen = RIDGE * len(X) * np.eye(X1.shape[1])
    pen[0, 0] = 0
    return np.linalg.solve(X1.T @ X1 + pen, X1.T @ y)


def category_part(p, before):
    """Each category's average yearly excess over the Nifty 50 over parameter years < before."""
    cm = p[p["param_year"] < before].groupby(["category", "param_year"])["target"].mean()
    return cm.groupby("category").mean()


def fund_part(p, method, before, rows):
    """Predicted relative return for rows, using parameter years < before only."""
    past = p[(p["param_year"] < before)]
    if method == "ridge":
        z = zscores(p, FEATURES)
        tr = past.index[past["rel"].notna()]
        Xtr = z.loc[tr].fillna(0).to_numpy()
        keep = z.loc[tr].notna().sum(axis=1) >= 3
        beta = ridge_fit(Xtr[keep.to_numpy()], past.loc[tr, "rel"].to_numpy()[keep.to_numpy()])
        Xr = z.loc[rows].fillna(0).to_numpy()
        ok = z.loc[rows].notna().sum(axis=1) >= 3
        pred = pd.Series(np.column_stack([np.ones(len(Xr)), Xr]) @ beta, index=rows).where(ok)
        return pred, {"beta": beta, "z": z.loc[rows]}
    q = p["_fifth"]
    years = past.loc[q.loc[past.index].notna()].groupby("param_year").size()
    if len(years) < MIN_PAST_YEARS:
        return pd.Series(np.nan, index=rows), None
    # each fifth's average relative return: per year (pooled over categories), then over the years
    by_year = past.assign(f=q.loc[past.index]).dropna(subset=["f", "rel"]).groupby(["param_year", "f"])["rel"].mean()
    avg = by_year.groupby("f").mean()
    return q.loc[rows].map(avg), {"fifth_avg": avg, "years": int(len(years))}


def evaluate(p, rows, pred_rel, cat_part):
    """The 3%+ call and the within-category checks for one set of predictions."""
    d = p.loc[rows, ["param_year", "category", "target", "rel", "scheme_id", "scheme_name"]].copy()
    d["rel_pred"] = pred_rel
    d["cat_part"] = d["category"].map(cat_part)
    d = d.dropna(subset=["rel_pred", "cat_part", "target"])
    if d.empty:
        return None, d
    d["pred"] = d["cat_part"] + d["rel_pred"]
    return metrics(d), d


def metrics(d):
    d = d.copy()
    d["call"] = d["pred"] >= TARGET
    d["actual"] = d["target"] >= TARGET
    d["naive_call"] = d["cat_part"] >= TARGET
    d["right"] = d["call"] == d["actual"]
    d["naive_right"] = d["naive_call"] == d["actual"]
    d["pf"] = d.groupby(["param_year", "category"], group_keys=False)["rel_pred"].apply(fifth)
    top, bot = d[d["pf"] == 5], d[d["pf"] == 1]
    med = d.groupby(["param_year", "category"])["rel"].transform("median")
    spread = (top.groupby("param_year")["rel"].mean() - bot.groupby("param_year")["rel"].mean()).dropna()
    ics = [stats.spearmanr(g["rel_pred"], g["rel"])[0] for _, g in d.groupby(["param_year", "category"])
           if len(g) >= MIN_FUNDS and g["rel_pred"].nunique() > 1]
    res = {"n": len(d), "hits": int(d["right"].sum()), "naive": int(d["naive_right"].sum()),
           "called": int(d["call"].sum()), "called_right": int((d["call"] & d["actual"]).sum()), "beat": int(d["actual"].sum()),
           "top_n": len(top), "top_beat": int(top["actual"].sum()),
           "top_above": int((d.loc[top.index, "rel"] > med.loc[top.index]).sum()),
           "bot_n": len(bot), "bot_below": int((d.loc[bot.index, "rel"] < med.loc[bot.index]).sum()),
           "bot_beat": int(bot["actual"].sum()),
           "spread": float(spread.mean()) if len(spread) else np.nan, "spread_years": int((spread > 0).sum()),
           "years": int(len(spread)), "ic": float(np.nanmean(ics)) if ics else np.nan,
           "top_rel": float(top["rel"].mean()) if len(top) else np.nan, "bot_rel": float(bot["rel"].mean()) if len(bot) else np.nan}
    return res


def run(data, test_first=TEST_FIRST):
    p, latest_year = prepare(data)
    full_years = sorted(data.full_years)
    last_full = max(full_years)
    test_years = [y for y in full_years if y >= test_first]
    out = {"latest_year": latest_year, "target_year": latest_year + 1, "test": (test_first, last_full),
           "live_label": data.partial_label, "methods": [], "panel": p, "categories": sorted(p["category"].unique())}
    full_mask = p["param_year"].isin(full_years)
    for key, label, text in METHODS:
        if key != "ridge":
            p["_fifth"] = add_fifths(p, key)
        backtest_rows = []
        detail = []
        for y in test_years:
            rows = p.index[(p["param_year"] == y)]
            rel_pred, info = fund_part(p, key, y, rows)
            cat = category_part(p[full_mask], y)
            res, d = evaluate(p, rows, rel_pred, cat)
            if res is None:
                continue
            res["year"] = y
            res["fifth_avg"] = None if not info or "fifth_avg" not in info else [float(info["fifth_avg"].get(f, np.nan)) for f in range(1, 6)]
            backtest_rows.append(res)
            d["method"] = key
            detail.append(d)
        detail = pd.concat(detail) if detail else pd.DataFrame()
        # totals over the test years, overall and by category (each year keeps its own category part)
        overall = metrics(detail) if len(detail) else None
        by_cat = {c: metrics(g) for c, g in detail.groupby("category")} if len(detail) else {}
        # live: fit on every full year, predict the latest year
        rows_l = p.index[p["param_year"] == latest_year]
        rel_l, info_l = fund_part(p, key, latest_year, rows_l)
        cat_l = category_part(p[full_mask], latest_year)
        live, dl = evaluate(p, rows_l, rel_l, cat_l)
        # the next-year prediction for every fund with latest values (same fit as the live check)
        pr = p.loc[rows_l, ["scheme_id", "scheme_name", "category"]].copy()
        pr["signal"] = p.loc[rows_l, key] if key != "ridge" else np.nan
        pr["fifth"] = p.loc[rows_l, "_fifth"] if key != "ridge" else np.nan
        pr["rel_pred"] = rel_l
        pr["cat_part"] = pr["category"].map(cat_l)
        pr["pred"] = pr["cat_part"] + pr["rel_pred"]
        out["methods"].append({"key": key, "label": label, "text": text, "years": backtest_rows, "overall": overall,
                               "by_cat": by_cat, "live": live, "detail": detail, "pred": pr, "info": info_l,
                               "cat_part": cat_l})
    p.drop(columns=["_fifth"], inplace=True, errors="ignore")
    # the category part on its own: how well the past average called each category's year
    cat_rows = []
    cm = p[full_mask].groupby(["category", "param_year"])["target"].mean()
    for y in test_years:
        past = category_part(p[full_mask], y)
        for c, v in past.items():
            if (c, y) in cm.index:
                cat_rows.append({"category": c, "year": y, "predicted": float(v), "actual": float(cm[(c, y)])})
    out["category_check"] = pd.DataFrame(cat_rows)
    out["category_yearly"] = cm
    # avoid-the-worst screen: last year's bottom fifth by momentum
    out["avoid"] = {}
    for key in ("mom1", "mom3"):
        d = p[full_mask & p["param_year"].isin(test_years)].copy()
        d["f"] = add_fifths(d, key)
        med = d.groupby(["param_year", "category"])["rel"].transform("median")
        bot, top = d[d["f"] == 1], d[d["f"] == 5]
        out["avoid"][key] = {"bot_n": len(bot), "bot_below": int((bot["rel"] < med[bot.index]).sum()),
                             "bot_rel": float(bot["rel"].mean()), "top_n": len(top),
                             "top_above": int((top["rel"] > med[top.index]).sum()), "top_rel": float(top["rel"].mean()),
                             "bot_beat": float((bot["target"] >= TARGET).mean()), "all_beat": float((d["target"] >= TARGET).mean()),
                             "rest_beat": float((d.loc[d["f"] > 1, "target"] >= TARGET).mean())}
    return out


def feasible(res):
    return bool(res and res["n"] >= MIN_CALLS and res["hits"] / res["n"] > HIT_RATIO and res["hits"] > res["naive"])
