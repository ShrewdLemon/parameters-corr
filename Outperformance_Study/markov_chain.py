"""Markov chain: does this year's result predict next year's?

Each fund's calendar-year excess return over the Nifty 50 is put in a state:
    S1  lagged by 3%+        excess < -3
    S2  slightly behind      -3 <= excess < 0
    S3  slightly ahead        0 <= excess < 3
    S4  beat by 3%+           excess >= 3
A transition matrix P[i, j] = share of funds in state i one year that were in state j
the next. It is estimated per category from past years only and blended with the
all-funds matrix (SMOOTH pseudo-transitions), so small categories borrow strength.

Prediction for next year from this year's state i: the row P[i, :]. P(beat by 3%+)
= P[i, S4]; expected excess = sum_j P[i, j] x the average excess of state j (past years,
category, blended the same way). Calls, hit ratios and the naive call as in Testing &
prediction.

A second chain does the same for each category's average excess (does a category that
beat the Nifty 50 by 3%+ keep doing so?), pooled over categories.
"""

import numpy as np
import pandas as pd

STATES = ["Lagged by 3%+", "Behind by 0-3%", "Ahead by 0-3%", "Beat by 3%+"]
CUTS_STATE = (-3.0, 0.0, 3.0)
TARGET = 3.0
TEST_FIRST = 2020
SMOOTH = 10.0                  # pseudo-transitions from the all-funds matrix added to each category row
TOLERANCES = (1, 2, 3, 5)
TOLERANCE = 3
HIT_RATIO = 0.60
MIN_CALLS = 30
ALL = "All funds"


def state(x):
    """0..3 for an excess return (NaN stays NaN)."""
    return pd.cut(x, [-np.inf, *CUTS_STATE, np.inf], right=False, labels=False)


def transitions(data):
    """Every fund's consecutive pair of calendar years: state and excess in year t and t+1.
    Return year t = parameter year t-1 (the panel pairs parameters in T with returns in T+1)."""
    latest_year = data.partial_year or max(data.full_years)
    p = data.panel[data.panel["param_year"].isin(data.full_years + [latest_year])].copy()
    p["return_year"] = p["param_year"] + 1
    p["x"] = np.where(p["param_year"] == latest_year, p["fund_return"] - data.nifty_partial, p["excess"])
    p = p.dropna(subset=["x"])[["scheme_id", "scheme_name", "category", "return_year", "x"]]
    p["s"] = state(p["x"])
    nxt = p.copy()
    nxt["return_year"] -= 1
    t = p.merge(nxt, on=["scheme_id", "return_year"], suffixes=("", "_next"))
    t = t.rename(columns={"return_year": "year"})            # transition from calendar year `year` to `year + 1`
    t["category"] = t["category_next"]
    return p, t[["scheme_id", "scheme_name", "category", "year", "x", "s", "x_next", "s_next"]], latest_year


def counts(t):
    c = np.zeros((4, 4))
    for (i, j), n in t.groupby(["s", "s_next"]).size().items():
        c[int(i), int(j)] += n
    return c


def matrix(t, category=None):
    """Blended transition probabilities and state averages from transitions t."""
    pc = counts(t)
    pooled = (pc + 1e-9) / (pc + 1e-9).sum(axis=1, keepdims=True)
    pmean = t.groupby("s_next")["x_next"].mean().reindex(range(4)).to_numpy()
    if category is None or category == ALL:
        return pooled, pmean, pc
    tc = t[t["category"] == category]
    cc = counts(tc)
    P = (cc + SMOOTH * pooled) / (cc.sum(axis=1, keepdims=True) + SMOOTH)
    n_to = tc.groupby("s_next").size().reindex(range(4)).fillna(0).to_numpy()
    s_to = tc.groupby("s_next")["x_next"].sum().reindex(range(4)).fillna(0).to_numpy()
    cmean = (s_to + SMOOTH * pmean) / (n_to + SMOOTH)
    return P, cmean, cc


def predict_rows(rows, P, means):
    """rows have column s (current state). Returns P(next state) and expected excess."""
    probs = P[rows["s"].astype(int).to_numpy()]
    return probs, probs @ means


def hits(pred_exp, p_beat, naive, actual):
    e, en = np.abs(actual - pred_exp), np.abs(actual - naive)
    call, act = p_beat >= 0.5, actual >= TARGET
    out = {"n": len(actual), "hits": int((call == act).sum()), "naive": int((act == (naive >= TARGET)).sum()),
           "called": int(call.sum()), "called_right": int((call & act).sum()), "beat": int(act.sum()),
           "ge": int((actual >= pred_exp).sum()), "naive_ge": int((actual >= naive).sum()),
           "abs_err": float(e.sum()), "naive_abs_err": float(en.sum())}
    out |= {f"tol{t}": int((e <= t).sum()) for t in TOLERANCES}
    out |= {f"naive_tol{t}": int((en <= t).sum()) for t in TOLERANCES}
    return out


def add(a, b):
    return {k: a.get(k, 0) + b[k] for k in b} if a else dict(b)


def run(data):
    p, t, latest_year = transitions(data)
    last_full_return = max(data.full_years) + 1
    full = t[t["year"] + 1 <= last_full_return]                     # transitions whose "next" year is a full year
    cats = sorted(t["category"].unique())
    test_years = [y for y in range(TEST_FIRST + 1, last_full_return + 1)]   # predicted return years
    out = {"latest_year": latest_year, "target_year": latest_year + 1, "categories": cats,
           "test": (TEST_FIRST + 1, last_full_return), "live_label": data.partial_label,
           "transitions": t, "fund_years": p, "groups": {}}
    for g in [ALL] + cats:
        tg = full if g == ALL else full[full["category"] == g]
        res, by_year, calls = {}, [], []
        for y in test_years:
            # predict return year y from the state in y-1, using transitions that ended by y-1
            past = full[full["year"] + 1 <= y - 1]
            P, means = matrix(past, g)[:2]
            cur = tg[tg["year"] == y - 1]
            if cur.empty:
                continue
            probs, exp = predict_rows(cur, P, means)
            cm = past if g == ALL else past[past["category"] == g]
            naive = cm.groupby("year")["x_next"].mean().mean()        # the group's past average, as before
            h = hits(exp, probs[:, 3], np.full(len(cur), naive), cur["x_next"].to_numpy())
            res = add(res, h)
            by_year.append({"year": y, **h, "naive_avg": float(naive)})
            for (_, r), pr, e in zip(cur.iterrows(), probs, exp):
                calls.append({"group": g, "fund": r["scheme_name"], "category": r["category"], "year": y, "state": int(r["s"]),
                              "probs": pr.tolist(), "expected": float(e), "naive": float(naive), "actual": float(r["x_next"])})
        # live: the latest partial period, from the full history
        P, means, c = matrix(full, g)
        cur = (t if g == ALL else t[t["category"] == g])
        cur = cur[cur["year"] == last_full_return]                   # 2025 -> Jan-Sep 2026
        live = None
        cm = full if g == ALL else full[full["category"] == g]
        naive_all = cm.groupby("year")["x_next"].mean().mean()
        if len(cur):
            probs, exp = predict_rows(cur, P, means)
            live = hits(exp, probs[:, 3], np.full(len(cur), naive_all), cur["x_next"].to_numpy())
        # next-year prediction: every fund's latest full-year state
        now = p[(p["return_year"] == last_full_return)]
        if g != ALL:
            now = now[now["category"] == g]
        probs, exp = predict_rows(now, P, means)
        pred = now.assign(**{f"p{j}": probs[:, j] for j in range(4)}, expected=exp)
        out["groups"][g] = {"overall": res or None, "years": by_year, "calls": calls, "live": live, "P": P, "means": means,
                            "counts": c, "pooled_counts": counts(full), "pred": pred, "naive_all": float(naive_all),
                            "transitions_n": int(len(tg))}
    out["category_chain"] = category_chain(p[p["return_year"] <= last_full_return], test_years)
    return out


def category_chain(p, test_years):
    """Each category's average excess per calendar year (all its funds) as a state; pooled transitions."""
    cy = p.groupby(["category", "return_year"])["x"].mean().rename("x").reset_index().rename(columns={"return_year": "year"})
    cy["s"] = state(cy["x"])
    nx = cy.copy()
    nx["year"] -= 1
    ct = cy.merge(nx, on=["category", "year"], suffixes=("", "_next")).dropna(subset=["s", "s_next"])
    res, rows = {}, []
    for y in test_years:
        past = ct[ct["year"] + 1 <= y - 1]
        if past.empty:
            continue
        P, means, _ = matrix(past)
        cur = ct[ct["year"] == y - 1]
        probs, exp = predict_rows(cur, P, means)
        naive = np.array([past[past["category"] == c].groupby("year")["x_next"].mean().mean() for c in cur["category"]])
        h = hits(exp, probs[:, 3], naive, cur["x_next"].to_numpy())
        res = add(res, h)
        for (_, r), pr, e, nv in zip(cur.iterrows(), probs, exp, naive):
            rows.append({"category": r["category"], "year": y, "state": int(r["s"]), "probs": pr.tolist(), "expected": float(e),
                         "naive": float(nv), "actual": float(r["x_next"])})
    P, means, c = matrix(ct)
    now = cy[cy["year"] == cy["year"].max()].copy()
    probs, exp = predict_rows(now, P, means)
    now = now.assign(**{f"p{j}": probs[:, j] for j in range(4)}, expected=exp)
    return {"overall": res, "rows": rows, "P": P, "means": means, "counts": c, "series": cy, "pred": now}


def feasible(res, how="call", tol=TOLERANCE, cut=HIT_RATIO):
    if not res or res["n"] < MIN_CALLS:
        return False
    if how == "diff":
        right, naive = res[f"tol{tol}"], res[f"naive_tol{tol}"]
    elif how == "ge":
        right, naive = res["ge"], res["naive_ge"]
    else:
        right, naive = res["hits"], res["naive"]
    return right / res["n"] > cut and right > naive


# ---------------------------------------------------------------------------
# Parameter-based chains: the state includes where the fund's parameter sits.
#   "param"        state = the fund's third of its category by the parameter this year (3 states)
#   "param+return" state = that third x this year's return state (12 states)
# Next-year state is still the return state (4), so P(beat by 3%+) and the expected excess
# come out exactly as for the return-only chain.

VARIANTS = {"param": "Parameter only", "param+return": "Parameter + last year's return"}
THIRDS = ["Low third", "Middle third", "High third"]
MIN_FUNDS_THIRDS = 6


def thirds(values):
    v = values.dropna()
    out = pd.Series(np.nan, index=values.index)
    if len(v) >= MIN_FUNDS_THIRDS:
        r = v.rank(method="first")
        out.loc[v.index] = np.floor((r - 1) * 3 / len(v))
    return out


def gmatrix(t, col, k, category=None):
    """Transition probabilities from a k-state column to the 4 return states, blended for categories."""
    def cnt(x):
        c = np.zeros((k, 4))
        for (i, j), n in x.groupby([col, "s_next"]).size().items():
            c[int(i), int(j)] += n
        return c
    pc = cnt(t)
    pooled = (pc + 1e-9) / (pc + 1e-9).sum(axis=1, keepdims=True)
    pmean = t.groupby("s_next")["x_next"].mean().reindex(range(4)).to_numpy()
    if category is None or category == ALL:
        return pooled, pmean, pc
    tc = t[t["category"] == category]
    cc = cnt(tc)
    P = (cc + SMOOTH * pooled) / (cc.sum(axis=1, keepdims=True) + SMOOTH)
    n_to = tc.groupby("s_next").size().reindex(range(4)).fillna(0).to_numpy()
    s_to = tc.groupby("s_next")["x_next"].sum().reindex(range(4)).fillna(0).to_numpy()
    return P, (s_to + SMOOTH * pmean) / (n_to + SMOOTH), cc


def param_frame(data, t, p, parameter):
    """Transitions with the fund's parameter third in the 'from' year, plus the latest year's
    rows for the next-year prediction."""
    pan = data.panel[["scheme_id", "param_year", parameter]].rename(columns={"param_year": "year", parameter: "v"})
    tt = t.merge(pan, on=["scheme_id", "year"], how="left")
    tt["third"] = tt.groupby(["category", "year"], group_keys=False)["v"].apply(thirds)
    tt = tt.dropna(subset=["third"])
    tt["third"] = tt["third"].astype(int)
    tt["js"] = tt["s"].astype(int) * 3 + tt["third"]
    return tt


def run_params(data, base, sp_result):
    """Every group's unique candidate parameters, both variants: backtest, live, next-year prediction."""
    p, t = base["fund_years"], base["transitions"]
    last_full_return = base["test"][1]
    test_years = list(range(base["test"][0], last_full_return + 1))
    latest_year = base["latest_year"]
    cands = {}
    for g in sp_result["groups"]:
        name = ALL if g["name"] == "All Funds" else g["name"]
        cands[name] = [r["parameter"] for r in g["params"] if r["status"][0] == 0]
    # rows for next year's prediction: each fund's latest full-year return state + its latest parameter values
    now = p[p["return_year"] == last_full_return].rename(columns={"return_year": "year"})
    out = {}
    cache = {}
    for g in [ALL] + base["categories"]:
        res_g = {}
        for parameter in cands.get(g, []):
            if parameter not in cache:
                tt = param_frame(data, t, p, parameter)
                nw = now.merge(data.panel[data.panel["param_year"] == latest_year][["scheme_id", parameter]]
                               .rename(columns={parameter: "v"}), on="scheme_id", how="left")
                nw["third"] = nw.groupby("category", group_keys=False)["v"].apply(thirds)
                nw = nw.dropna(subset=["third"])
                nw["third"] = nw["third"].astype(int)
                nw["js"] = nw["s"].astype(int) * 3 + nw["third"]
                cache[parameter] = (tt, nw)
            tt, nw = cache[parameter]
            full = tt[tt["year"] + 1 <= last_full_return]
            for variant in VARIANTS:
                col, k = ("third", 3) if variant == "param" else ("js", 12)
                tg = full if g == ALL else full[full["category"] == g]
                res, by_year, calls = {}, [], []
                for y in test_years:
                    past = full[full["year"] + 1 <= y - 1]
                    if past.empty:
                        continue
                    P, means, _ = gmatrix(past, col, k, g)
                    cur = tg[tg["year"] == y - 1]
                    if cur.empty:
                        continue
                    probs = P[cur[col].astype(int).to_numpy()]
                    exp = probs @ means
                    cm = past if g == ALL else past[past["category"] == g]
                    naive = cm.groupby("year")["x_next"].mean().mean()
                    h = hits(exp, probs[:, 3], np.full(len(cur), naive), cur["x_next"].to_numpy())
                    res = add(res, h)
                    by_year.append({"year": y, **h})
                    for (_, r), pr, e in zip(cur.iterrows(), probs, exp):
                        calls.append({"fund": r["scheme_name"], "year": y, "state": int(r[col]), "probs": pr.tolist(),
                                      "expected": float(e), "naive": float(naive), "actual": float(r["x_next"])})
                P, means, c = gmatrix(full, col, k, g)
                pooled_counts = gmatrix(full, col, k)[2]
                livec = tt[(tt["year"] == last_full_return)]
                if g != ALL:
                    livec = livec[livec["category"] == g]
                live = None
                if len(livec):
                    pr = P[livec[col].astype(int).to_numpy()]
                    cm = full if g == ALL else full[full["category"] == g]
                    nv = cm.groupby("year")["x_next"].mean().mean()
                    live = hits(pr @ means, pr[:, 3], np.full(len(livec), nv), livec["x_next"].to_numpy())
                nw_g = nw if g == ALL else nw[nw["category"] == g]
                pr = P[nw_g[col].astype(int).to_numpy()]
                pred = nw_g.assign(**{f"p{j}": pr[:, j] for j in range(4)}, expected=pr @ means)
                res_g[(parameter, variant)] = {"overall": res or None, "years": by_year, "calls": calls, "live": live,
                                               "P": P, "means": means, "counts": c, "pooled_counts": pooled_counts, "pred": pred}
        out[g] = res_g
    return out
