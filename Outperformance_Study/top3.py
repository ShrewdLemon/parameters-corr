"""Top 3 picks: can a method name, in advance, next year's 3 best funds?

For each group (all funds, each category) and each test year Y (parameter years TEST_FIRST..
last full year, returns Y+1), every method ranks the group's funds using only information
available at the end of Y and picks its top 3. Checks:

* the hit: did the pick beat the Nifty 50 by 3%+ that year? hit ratio = picks that did / picks,
  against random picks (the share of the group's funds that did) and the chance by luck;
* exact: how many picks are in the actual top 3;
* close: how many picks are in the actual top 10, and their actual percentile in the group
  (100% = best fund, 0% = worst, 50% = middle);
* random: picking 3 funds blindly from N, each pick lands in the top 3 with chance 3/N and in
  the top 10 with chance 10/N, at a 50% percentile on average.

Methods (all walk-forward):
* every unique candidate parameter from Testing & prediction, ranked by its value in the
  direction of its average yearly slope before Y;
* the Research methods signals (direction: their rank correlation with next-year relative
  return before Y) and the ridge regression;
* the Markov chain's expected excess (ties broken by last year's excess).
"""

import numpy as np
import pandas as pd
from scipy import stats

import markov_chain as MC
import research_methods as RM

TEST_FIRST = 2020
TARGET = 3.0                # the hit: a pick beats the Nifty 50 by 3%+ that year
HIT_RATIO = 0.60
PICKS = 3
CLOSE = 10
ALL = "All funds"


def luck_hits(ns, hits):
    """P(at least `hits` of the picks land in the top 3 by luck): each year the number of picks
    in the top 3 is hypergeometric (N funds, 3 winners, 3 picks); the years are added up."""
    dist = np.array([1.0])
    for n in ns:
        k = np.arange(PICKS + 1)
        pk = stats.hypergeom.pmf(k, n, PICKS, PICKS)
        dist = np.convolve(dist, pk)
    return float(dist[hits:].sum())


def luck_beat(years, beats):
    """P(at least `beats` picks beat the Nifty by 3%+ by luck): each year 3 blind picks from N funds
    of which K beat (hypergeometric); the years are added up. years = [(N, K), ...]."""
    dist = np.array([1.0])
    for n, k_ in years:
        k = np.arange(PICKS + 1)
        dist = np.convolve(dist, stats.hypergeom.pmf(k, n, k_, PICKS))
    return float(dist[beats:].sum())


def luck_pct(ns, pct, picks):
    """P(an average percentile at least this high by luck) - normal approximation; a random
    pick's percentile is uniform on 0..1 (variance about 1/12)."""
    var = np.mean([(n + 1) / (12 * (n - 1)) for n in ns]) / picks
    return float(stats.norm.sf((pct - 0.5) / np.sqrt(var)))


def rank_desc(s):
    """1 = highest."""
    return s.rank(ascending=False, method="first")


def run(data, sp_result):
    p, latest_year = RM.prepare(data)
    full_years = sorted(data.full_years)
    years = [y for y in full_years if y >= TEST_FIRST] + [latest_year]
    _, trans, _ = MC.transitions(data)
    # last calendar year's excess (state for the Markov chain)
    g = p.groupby("scheme_id")
    p["last_x"] = g["target"].shift(1).where((p["param_year"] - g["param_year"].shift(1)) == 1)
    groups = [ALL] + sorted(p["category"].unique())
    sp_groups = {("All funds" if x["name"] == "All Funds" else x["name"]): x for x in sp_result["groups"]}

    # ---- scores for every fund-year, by method
    scores = {}
    labels = {}
    for key, label, _ in RM.METHODS:
        labels[key] = ("research", label)
    labels["markov"] = ("markov", "Markov chain (expected excess)")
    for y in years:
        rows = p.index[p["param_year"] == y]
        past = p[(p["param_year"] < y) & p["rel"].notna()]
        for key, _, _ in RM.METHODS:
            if key == "ridge":
                s, _ = RM.fund_part(p, "ridge", y, rows)
            else:
                pr = past[[key, "rel"]].dropna()
                sign = np.sign(stats.spearmanr(pr[key], pr["rel"])[0]) if len(pr) > 30 else np.nan
                s = p.loc[rows, key] * sign
            scores.setdefault(key, {}).update(s.dropna().to_dict())
        # Markov: per group's matrix, so stored per (group, index) below
    # Markov and the candidate parameters depend on the group
    group_scores = {}
    for grp in groups:
        gs = {}
        # Markov
        mk = {}
        for y in years:
            past_t = trans[trans["year"] + 1 <= y]
            P, means, _ = MC.matrix(past_t, grp if grp != ALL else MC.ALL)
            rows = p[(p["param_year"] == y) & p["last_x"].notna()]
            if grp != ALL:
                rows = rows[rows["category"] == grp]
            st = MC.state(rows["last_x"]).astype(int).to_numpy()
            exp = P[st] @ means
            mk.update(dict(zip(rows.index, exp + 1e-6 * rows["last_x"].to_numpy())))
        gs["markov"] = mk
        # candidate parameters of this group (Testing & prediction shortlist, unique)
        spg = sp_groups.get(grp)
        if spg:
            for r in spg["params"]:
                if r["status"][0] != 0:
                    continue
                key = "param:" + r["parameter"]
                labels[key] = ("parameter", r["parameter"])
                slopes = r["yearly"].set_index("year")["slope"]
                d = {}
                for y in years:
                    past = slopes[slopes.index < y]
                    if len(past) < 5:
                        continue
                    rows = p[(p["param_year"] == y)]
                    if grp != ALL:
                        rows = rows[rows["category"] == grp]
                    v = rows[r["parameter"]].dropna() * np.sign(past.mean())
                    d.update(v.to_dict())
                gs[key] = d
        group_scores[grp] = gs

    # ---- evaluate
    out = {"groups": {}, "labels": labels, "latest_year": latest_year, "target_year": latest_year + 1,
           "test": (TEST_FIRST, max(full_years)), "live_label": data.partial_label, "panel": p}
    for grp in groups:
        gp = p if grp == ALL else p[p["category"] == grp]
        methods = {k: scores[k] for k, _, _ in RM.METHODS} | group_scores[grp]
        res = {}
        for key, sc in methods.items():
            picks, by_year = [], []
            for y in years:
                yr = gp[(gp["param_year"] == y) & gp["target"].notna()]
                if len(yr) < PICKS + 2:
                    continue
                arank = rank_desc(yr["target"])
                n = len(yr)
                cand = pd.Series({i: sc[i] for i in yr.index if i in sc})
                if len(cand) < PICKS:
                    continue
                top = cand.sort_values(ascending=False).index[:PICKS]
                rec = []
                for k, i in enumerate(top, 1):
                    ar = int(arank[i])
                    rec.append({"year": y, "fund": yr.at[i, "scheme_name"], "category": yr.at[i, "category"], "pick": k,
                                "score": float(cand[i]), "actual": float(yr.at[i, "target"]), "actual_rank": ar, "of": n,
                                "pct": 1 - (ar - 1) / (n - 1), "group_avg": float(yr["target"].mean())})
                picks += rec
                actual_top = yr.loc[arank.sort_values().index[:PICKS], ["scheme_name", "target"]]
                k_beat = int((yr["target"] >= TARGET).sum())
                by_year.append({"year": y, "of": n, "scored": len(cand), "hits": sum(r["actual_rank"] <= PICKS for r in rec),
                                "beat": sum(r["actual"] >= TARGET for r in rec), "k_beat": k_beat,
                                "random_beat": PICKS * k_beat / n,
                                "close": sum(r["actual_rank"] <= CLOSE for r in rec), "pct": float(np.mean([r["pct"] for r in rec])),
                                "picks_avg": float(np.mean([r["actual"] for r in rec])), "group_avg": float(yr["target"].mean()),
                                "random_hits": PICKS * PICKS / n, "random_close": PICKS * min(CLOSE, n) / n,
                                "actual_top": [[a, float(b)] for a, b in actual_top.itertuples(index=False)],
                                "live": y == latest_year})
            if not by_year:
                continue
            bt = [b for b in by_year if not b["live"]]
            lv = [b for b in by_year if b["live"]]

            def agg(bs):
                if not bs:
                    return None
                n = PICKS * len(bs)
                pk = [r for r in picks if r["year"] in {b["year"] for b in bs}]
                return {"years": len(bs), "picks": n, "hits": sum(b["hits"] for b in bs), "close": sum(b["close"] for b in bs),
                        "random_hits": sum(b["random_hits"] for b in bs), "random_close": sum(b["random_close"] for b in bs),
                        "pct": float(np.mean([r["pct"] for r in pk])), "picks_avg": float(np.mean([r["actual"] for r in pk])),
                        "group_avg": float(np.mean([b["group_avg"] for b in bs])),
                        "beat3": sum(r["actual"] >= 3 for r in pk), "years_any_hit": sum(b["hits"] > 0 for b in bs),
                        "luck_hits": luck_hits([b["of"] for b in bs], sum(b["hits"] for b in bs)),
                        "beat": sum(b["beat"] for b in bs), "random_beat": sum(b["random_beat"] for b in bs),
                        "luck_beat": luck_beat([(b["of"], b["k_beat"]) for b in bs], sum(b["beat"] for b in bs)),
                        "luck_pct": luck_pct([b["of"] for b in bs], float(np.mean([r["pct"] for r in pk])), n)}
            res[key] = {"backtest": agg(bt), "live": agg(lv), "years": by_year, "picks": picks}
        # next-year picks: the latest year's scores (live year), top 3 by score
        out["groups"][grp] = {"methods": res, "n_latest": int((gp["param_year"] == latest_year).sum())}
    # methods that work the same way in every category: their picks pooled over all categories
    common = [k for k, _, _ in RM.METHODS] + ["markov"]
    cats = [g for g in groups if g != ALL]
    pooled = {}
    for key in common:
        yrs, beats, picks, rb = [], 0, 0, 0.0
        per = []
        for c in cats:
            m = out["groups"][c]["methods"].get(key)
            if not m or not m["backtest"]:
                continue
            for b in m["years"]:
                if b["live"]:
                    continue
                yrs.append((b["of"], b["k_beat"]))
                beats += b["beat"]
                picks += PICKS
                rb += b["random_beat"]
            per.append(c)
        if picks:
            pooled[key] = {"categories": len(per), "picks": picks, "beat": beats, "random_beat": rb,
                           "luck_beat": luck_beat(yrs, beats)}
    out["pooled"] = pooled
    return out


def passes(bt, n_methods):
    """A method counts if its picks beat the Nifty by 3%+ more than HIT_RATIO of the time, more often
    than random picks, and the chance of that by luck clears the multiple-testing bar."""
    return bool(bt and bt["beat"] / bt["picks"] > HIT_RATIO and bt["beat"] > bt["random_beat"]
                and bt["luck_beat"] < 0.05 / n_methods)
