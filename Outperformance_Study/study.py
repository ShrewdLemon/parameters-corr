"""Which parameters reliably predict next-year fund returns, which categories beat
the Nifty 50 by 3-4%, and whether specific funds can be picked in advance.

Every test pairs a fund's parameter in calendar year T with its return in T+1.
The return T+1 = latest year is only Jan-Sep (9 months) and is used solely as a
live check of the final predictions, never to choose or weigh anything.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    DEC25_WORKBOOK, UPDATED_FUND_LIST, UPDATED_PARAMETER_SHEET, UPDATED_RETURN_SHEET,
)
from src.yearwise_summary import load_fund_list_workbook, load_yearwise_data  # noqa: E402

# ---- settings -----------------------------------------------------------------
BENCHMARK_ROW = "Nifty 50 PR INR"     # price index; funds are total return
THRESHOLDS = (3.0, 4.0)               # "beat the Nifty 50 by 3-4%" (percentage points)
MIN_FUNDS_PER_YEAR = 20               # cross-section needed for a yearly IC
MIN_FUNDS_PER_CATEGORY = 3            # funds needed for a category-year average
RELIABLE_T = 2.0                      # |t| of the mean yearly IC
RELIABLE_CONSISTENCY = 0.65           # share of years whose IC has the mean's sign
BACKTEST_FIRST_YEAR = 2010            # first parameter year traded (5 IC years before it)
TRAIN_T = 2.0                         # walk-forward selection, using only past ICs
TRAIN_CONSISTENCY = 0.60
MAX_SIGNALS = 8                       # parameters combined into the score
DEDUPE_RHO = 0.85                     # drop a signal that duplicates a kept one
TOP_SHARE = 0.20                      # top / bottom quintile
TOP_CATEGORIES = 3

# Index levels from Yahoo Finance (fetch_indices.py), cached. Used for the partial
# latest year, which the export does not cover, and to confirm the benchmarks.
INDEX_RETURNS = Path(__file__).resolve().parent / "data" / "index_returns.csv"

# Each category's own benchmark. The export carries it implicitly: fund return
# minus Morningstar's "Excess Return" is identical for every fund in a category,
# and matches these total-return indices. Second name: the Yahoo price index.
CATEGORY_BENCHMARKS = {
    "Small cap Fund": ("Nifty Smallcap 250 TRI", "Nifty Smallcap 250"),
    "Mid Cap Fund": ("Nifty Midcap 150 TRI", "Nifty Midcap 150"),
    "Large & Mid Cap": ("Nifty LargeMidcap 250 TRI", "Nifty LargeMidcap 250"),
    "Multi Cap Fund": ("Nifty 500 Multicap 50:25:25 TRI", "Nifty 500 Multicap 50:25:25"),
    "Large Cap Fund": ("Nifty 100 TRI", "Nifty 100"),
}
DEFAULT_BENCHMARK = ("Nifty 500 TRI", "Nifty 500")


@dataclass
class Data:
    panel: pd.DataFrame              # one row per fund and parameter year
    parameters: list
    nifty: pd.Series                 # calendar-year Nifty 50 PR return, by year
    full_years: list                 # parameter years whose next-year return is a full year
    partial_year: int                # parameter year paired with the partial return
    partial_label: str
    indices: pd.DataFrame = None     # Yahoo price-index returns by index and period
    benchmarks: pd.DataFrame = None  # category, year, benchmark name, total return
    nifty_partial: float = None      # Nifty 50 return over the partial period
    notes: dict = field(default_factory=dict)


def _nifty_returns(workbook):
    """Nifty 50 PR calendar returns from the benchmark row's 'Return (Cumulative)'."""
    raw = pd.read_excel(workbook, sheet_name=UPDATED_PARAMETER_SHEET, header=None)
    header = next(i for i in range(40) if "Group/Investment" in [str(v) for v in raw.iloc[i]])
    row = next(i for i in range(header, len(raw)) if str(raw.iat[i, 1]).strip() == BENCHMARK_ROW)
    ends = raw.iloc[header - 1]
    returns = {}
    year = None
    for column in range(raw.shape[1]):
        if pd.notna(ends[column]):
            value = ends[column]
            year = value.year if hasattr(value, "year") else int(str(value)[-4:])
        label = " ".join(str(raw.iat[header, column]).split())
        if year and label == "Return (Cumulative)":
            returns[year] = float(raw.iat[row, column])
    return pd.Series(returns).sort_index()


def _partial_label(workbook):
    raw = pd.read_excel(workbook, sheet_name=UPDATED_RETURN_SHEET, header=None, nrows=10)
    header = next(i for i in range(len(raw)) if "Group/Investment" in [str(v) for v in raw.iloc[i]])
    start = pd.to_datetime(raw.iloc[header - 2].dropna().iloc[-1], dayfirst=True)
    end = pd.to_datetime(raw.iloc[header - 1].dropna().iloc[-1], dayfirst=True)
    full = (start.month, start.day, end.month, end.day) == (1, 1, 12, 31)
    return end.year, (None if full else f"{start:%b}-{end:%b} {end.year}")


def load(workbook=DEC25_WORKBOOK):
    classes = load_fund_list_workbook(UPDATED_FUND_LIST)
    forward, parameters = load_yearwise_data(workbook, UPDATED_PARAMETER_SHEET,
                                             UPDATED_RETURN_SHEET, classes)
    panel = forward[forward["fund_class"] != "Unclassified"].copy()
    panel = panel.rename(columns={"fund_class": "category", "category": "morningstar_category",
                                  "year": "param_year", "target_year": "return_year",
                                  "next_year_return": "fund_return"})
    nifty = _nifty_returns(workbook)
    last_return_year, partial = _partial_label(workbook)
    panel["nifty_return"] = panel["return_year"].map(nifty)
    panel["excess"] = panel["fund_return"] - panel["nifty_return"]
    for threshold in THRESHOLDS:
        panel[f"beat_{threshold:g}"] = (panel["excess"] >= threshold).where(panel["excess"].notna())
    years = sorted(panel["param_year"].unique())
    partial_year = last_return_year - 1 if partial else None
    full_years = [y for y in years if y != partial_year and (y + 1) in nifty.index]
    data = Data(panel.reset_index(drop=True), parameters, nifty, full_years, partial_year,
                partial or "")
    data.benchmarks = category_benchmarks(data)
    if INDEX_RETURNS.exists():
        data.indices = pd.read_csv(INDEX_RETURNS)
        data.nifty_partial = index_return(data, "Nifty 50", partial)
    return data


def benchmark_of(category):
    return CATEGORY_BENCHMARKS.get(category, DEFAULT_BENCHMARK)


def index_return(data, name, period):
    """A cached Yahoo price-index return for a period label such as 'Jan-Sep 2026'."""
    if data.indices is None or not period:
        return None
    hit = data.indices[(data.indices["index"] == name) & (data.indices["period"] == period)]
    return float(hit["return"].iloc[0]) if len(hit) else None


def category_benchmarks(data):
    """Each category's benchmark total return per calendar year, read from the export:
    a fund's own-year return minus its 'Excess Return (Cumulative)'."""
    frame = data.panel[["category", "param_year", "Return (Cumulative)",
                        "Excess Return (Cumulative)"]].dropna()
    frame = frame.assign(implied=frame["Return (Cumulative)"] - frame["Excess Return (Cumulative)"])
    grouped = frame.groupby(["category", "param_year"])["implied"]
    table = grouped.median().rename("benchmark_return").reset_index()
    table["spread"] = grouped.agg(lambda s: s.max() - s.min()).values
    table = table.rename(columns={"param_year": "year"})
    table["benchmark"] = table["category"].map(lambda c: benchmark_of(c)[0])
    return table


def benchmark_check(data):
    """Derived benchmark TRI vs Yahoo's price index of the same name: the gap should
    be a small, steady positive number (the dividend yield) if the label is right."""
    if data.indices is None:
        return pd.DataFrame()
    rows = []
    for category, (tri, price) in {**CATEGORY_BENCHMARKS, "Other categories": DEFAULT_BENCHMARK}.items():
        source = data.benchmarks[data.benchmarks["benchmark"] == tri]
        series = source.groupby("year")["benchmark_return"].first()
        yahoo = data.indices[(data.indices["index"] == price)
                             & data.indices["period"].str.startswith("Jan-Dec")].set_index("year")["return"]
        both = pd.concat([series.rename("tri"), yahoo.rename("price")], axis=1).dropna()
        gap = both["tri"] - both["price"]
        rows.append({"benchmark": tri, "price_index": price, "years_compared": len(both),
                     "avg_gap": gap.mean() if len(both) else None,
                     "min_gap": gap.min() if len(both) else None,
                     "max_gap": gap.max() if len(both) else None})
    return pd.DataFrame(rows)


# ---- 1. parameter reliability ---------------------------------------------------

def yearly_ic(data, neutral=False):
    """Spearman IC per parameter (rows) and parameter year (columns).

    `neutral` ranks parameters and returns within each category first, so the
    IC measures picking funds inside a category rather than picking categories.
    """
    out = {}
    for year in data.full_years:
        frame = data.panel[data.panel["param_year"] == year]
        if len(frame) < MIN_FUNDS_PER_YEAR:
            continue
        if neutral:
            ranked = frame.groupby("category")[data.parameters + ["fund_return"]].rank(pct=True)
            with np.errstate(all="ignore"):
                out[year] = ranked[data.parameters].corrwith(ranked["fund_return"])
        else:
            out[year] = frame[data.parameters].corrwith(frame["fund_return"], method="spearman")
    ic = pd.DataFrame(out).reindex(data.parameters)
    counts = pd.DataFrame({
        year: data.panel[data.panel["param_year"] == year][data.parameters]
        .notna().mul(data.panel.loc[data.panel["param_year"] == year, "fund_return"].notna(), axis=0)
        .sum() for year in ic.columns}).reindex(data.parameters)
    return ic.where(counts >= MIN_FUNDS_PER_YEAR)


def ic_summary(ic):
    """Mean IC, its t-stat, sign consistency and stability across the two halves."""
    mean = ic.mean(axis=1)
    std = ic.std(axis=1, ddof=1)
    n = ic.notna().sum(axis=1)
    t = mean / (std / np.sqrt(n))
    sign = np.sign(mean)
    consistency = ic.apply(lambda row: (np.sign(row.dropna()) == np.sign(row.mean())).mean()
                           if row.notna().any() else np.nan, axis=1)
    cols = list(ic.columns)
    half = len(cols) // 2
    first, second = ic[cols[:half]].mean(axis=1), ic[cols[half:]].mean(axis=1)
    return pd.DataFrame({
        "years": n, "mean_ic": mean, "std_ic": std, "icir": mean / std, "t_stat": t,
        "consistency": consistency, "first_half": first, "second_half": second,
        "recent_5": ic[cols[-5:]].mean(axis=1),
        "same_sign_halves": (np.sign(first) == np.sign(second)) & (first != 0),
        "direction": np.where(sign > 0, "Higher is better", "Lower is better"),
        "half_labels": f"{cols[0] + 1}-{cols[half - 1] + 1} | {cols[half] + 1}-{cols[-1] + 1}",
    })


def reliability(data):
    ic, ic_neutral = yearly_ic(data), yearly_ic(data, neutral=True)
    summary = ic_summary(ic)
    neutral = ic_summary(ic_neutral)
    pooled = pooled_pearson(data)
    summary["neutral_mean_ic"] = neutral["mean_ic"]
    summary["neutral_t"] = neutral["t_stat"]
    summary["pooled_pearson"] = pooled
    reliable = ((summary["t_stat"].abs() >= RELIABLE_T)
                & (summary["consistency"] >= RELIABLE_CONSISTENCY)
                & summary["same_sign_halves"])
    partly = (summary["t_stat"].abs() >= RELIABLE_T) & ~reliable
    summary["verdict"] = np.select([reliable, partly], ["Reliable", "Mixed"], "Not reliable")
    summary = summary.sort_values("t_stat", key=lambda s: -s.abs())
    summary.insert(0, "rank", range(1, len(summary) + 1))
    return ic, ic_neutral, summary


def pooled_pearson(data):
    frame = data.panel[data.panel["param_year"].isin(data.full_years)]
    with np.errstate(all="ignore"):
        return frame[data.parameters].corrwith(frame["fund_return"])


# ---- 2. categories vs the Nifty 50 --------------------------------------------------

def category_years(data):
    """Equal-weight category return per return year, and its excess over the Nifty 50."""
    frame = data.panel[data.panel["fund_return"].notna()]
    grouped = frame.groupby(["category", "return_year"])
    table = grouped["fund_return"].agg(["mean", "count"]).reset_index()
    table = table[table["count"] >= MIN_FUNDS_PER_CATEGORY]
    table["nifty"] = table["return_year"].map(data.nifty)
    table["excess"] = table["mean"] - table["nifty"]
    bench = data.benchmarks.set_index(["category", "year"])["benchmark_return"]
    table["benchmark"] = table["category"].map(lambda c: benchmark_of(c)[0])
    table["benchmark_return"] = [bench.get((c, y)) for c, y in zip(table["category"], table["return_year"])]
    table["excess_vs_benchmark"] = table["mean"] - table["benchmark_return"]
    share = grouped["excess"].apply(lambda s: (s >= THRESHOLDS[0]).mean()).rename("share_funds_beat")
    table = table.merge(share.reset_index(), on=["category", "return_year"], how="left")
    return table.rename(columns={"mean": "category_return", "count": "funds"})


def category_summary(data, table):
    full = table[table["return_year"].isin([y + 1 for y in data.full_years])]
    rows = []
    for category, frame in full.groupby("category"):
        excess = frame["excess"]
        recent = frame[frame["return_year"] >= frame["return_year"].max() - 4]["excess"]
        rows.append({
            "category": category, "years": len(frame),
            "from": int(frame["return_year"].min()), "to": int(frame["return_year"].max()),
            "avg_excess": excess.mean(), "median_excess": excess.median(),
            "beat_nifty": (excess > 0).mean(),
            **{f"beat_{t:g}": (excess >= t).mean() for t in THRESHOLDS},
            "recent5_excess": recent.mean(),
            "recent5_beat_3": (recent >= THRESHOLDS[0]).mean(),
            "avg_share_funds_beat_3": frame["share_funds_beat"].mean(),
            "benchmark": benchmark_of(category)[0],
            "avg_return": frame["category_return"].mean(),
            "avg_benchmark": frame["benchmark_return"].mean(),
            "avg_nifty": frame["nifty"].mean(),
            "avg_excess_vs_benchmark": frame["excess_vs_benchmark"].mean(),
            "beat_benchmark": (frame["excess_vs_benchmark"].dropna() > 0).mean(),
            "beat_benchmark_3": (frame["excess_vs_benchmark"].dropna() >= THRESHOLDS[0]).mean(),
        })
    return pd.DataFrame(rows).sort_values("beat_3", ascending=False).reset_index(drop=True)


def category_persistence(table):
    """Rank correlation of category excess between consecutive years (momentum test)."""
    pivot = table.pivot(index="category", columns="return_year", values="excess")
    years = sorted(pivot.columns)
    rows = []
    for a, b in zip(years, years[1:]):
        pair = pivot[[a, b]].dropna()
        if len(pair) >= 5:
            rows.append({"year": a, "next_year": b, "categories": len(pair),
                         "rank_corr": pair[a].corr(pair[b], method="spearman")})
    return pd.DataFrame(rows)


def fund_persistence(data):
    """Does beating the Nifty by 3% in one year make it more likely the next year?"""
    frame = data.panel[["scheme_id", "return_year", "excess"]].dropna()
    frame = frame[frame["return_year"].isin([y + 1 for y in data.full_years])]
    frame["beat"] = frame["excess"] >= THRESHOLDS[0]
    nxt = frame.assign(return_year=frame["return_year"] - 1)[["scheme_id", "return_year", "beat"]]
    pairs = frame.merge(nxt, on=["scheme_id", "return_year"], suffixes=("", "_next"))
    base = pairs["beat_next"].mean()
    after_beat = pairs.loc[pairs["beat"], "beat_next"].mean()
    after_miss = pairs.loc[~pairs["beat"], "beat_next"].mean()
    return {"pairs": len(pairs), "base_rate": base, "after_beat": after_beat,
            "after_miss": after_miss, "beats": int(pairs["beat"].sum())}


# ---- 3. walk-forward fund selection ---------------------------------------------------

def choose_signals(ic_history, cross_section, parameters):
    """Signals chosen only from past ICs: strong, consistent, not duplicates."""
    summary = ic_summary(ic_history)
    eligible = summary[(summary["t_stat"].abs() >= TRAIN_T)
                       & (summary["consistency"] >= TRAIN_CONSISTENCY)
                       & summary["mean_ic"].notna()]
    if eligible.empty:
        eligible = summary.dropna(subset=["icir"]).reindex(
            summary["icir"].abs().sort_values(ascending=False).index[:3])
    order = eligible["t_stat"].abs().sort_values(ascending=False).index
    kept = []
    for name in order:
        values = cross_section[name]
        if values.notna().sum() < MIN_FUNDS_PER_YEAR:
            continue
        duplicate = any(abs(values.corr(cross_section[k], method="spearman")) > DEDUPE_RHO
                        for k in kept)
        if not duplicate:
            kept.append(name)
        if len(kept) == MAX_SIGNALS:
            break
    return [(name, 1.0 if summary.at[name, "mean_ic"] > 0 else -1.0,
             summary.at[name, "mean_ic"], summary.at[name, "t_stat"]) for name in kept]


def score(frame, signals):
    """Mean percentile rank across the signals, oriented so higher is better."""
    ranks = []
    for name, sign, *_ in signals:
        ranks.append(frame[name].rank(pct=True, ascending=sign > 0))
    if not ranks:
        return pd.Series(np.nan, index=frame.index)
    stacked = pd.concat(ranks, axis=1)
    enough = stacked.notna().sum(axis=1) >= max(1, len(signals) / 2)
    return stacked.mean(axis=1).where(enough)


def backtest(data, ic):
    """For each year: choose signals from past ICs only, score funds, follow the top 20%."""
    rows, picks = [], []
    years = [y for y in data.full_years if y >= BACKTEST_FIRST_YEAR]
    for year in years:
        history = ic[[c for c in ic.columns if c + 1 <= year]]   # returns known at year end
        frame = data.panel[data.panel["param_year"] == year].copy()
        signals = choose_signals(history, frame, data.parameters)
        frame["score"] = score(frame, signals)
        scored = frame.dropna(subset=["score", "fund_return"])
        cut = max(1, int(round(len(scored) * TOP_SHARE)))
        top = scored.nlargest(cut, "score")
        bottom = scored.nsmallest(cut, "score")
        nifty = data.nifty.get(year + 1)
        cat = scored.groupby("category").agg(score=("score", "mean"), ret=("fund_return", "mean"),
                                             n=("score", "size"))
        cat = cat[cat["n"] >= MIN_FUNDS_PER_CATEGORY]
        top_cats = cat.nlargest(TOP_CATEGORIES, "score")
        rows.append({
            "param_year": year, "return_year": year + 1, "funds": len(scored),
            "signals": "; ".join(f"{n} ({'+' if s > 0 else '-'})" for n, s, *_ in signals),
            "nifty": nifty,
            "top_return": top["fund_return"].mean(), "all_return": scored["fund_return"].mean(),
            "bottom_return": bottom["fund_return"].mean(),
            "top_excess": top["fund_return"].mean() - nifty,
            "all_excess": scored["fund_return"].mean() - nifty,
            "bottom_excess": bottom["fund_return"].mean() - nifty,
            **{f"top_share_beat_{t:g}": (top["excess"] >= t).mean() for t in THRESHOLDS},
            **{f"all_share_beat_{t:g}": (scored["excess"] >= t).mean() for t in THRESHOLDS},
            "top_cats": ", ".join(top_cats.index),
            "top_cats_excess": top_cats["ret"].mean() - nifty,
            "all_cats_excess": cat["ret"].mean() - nifty,
            "score_ic": scored["score"].corr(scored["fund_return"], method="spearman"),
        })
        for _, fund in top.iterrows():
            picks.append({"param_year": year, "return_year": year + 1, "fund": fund["scheme_name"],
                          "isin": fund["scheme_id"], "category": fund["category"],
                          "score": fund["score"], "return": fund["fund_return"],
                          "excess": fund["excess"]})
    return pd.DataFrame(rows), pd.DataFrame(picks)


def backtest_summary(results):
    r = results
    out = {
        "years": len(r), "from": int(r["return_year"].min()), "to": int(r["return_year"].max()),
        "top_avg_excess": r["top_excess"].mean(), "all_avg_excess": r["all_excess"].mean(),
        "bottom_avg_excess": r["bottom_excess"].mean(),
        "top_minus_all": (r["top_excess"] - r["all_excess"]).mean(),
        "years_top_beats_all": (r["top_return"] > r["all_return"]).mean(),
        "years_top_beats_bottom": (r["top_return"] > r["bottom_return"]).mean(),
        "mean_score_ic": r["score_ic"].mean(),
        "top_cats_avg_excess": r["top_cats_excess"].mean(),
        "all_cats_avg_excess": r["all_cats_excess"].mean(),
    }
    for t in THRESHOLDS:
        out[f"years_top_beats_nifty_by_{t:g}"] = (r["top_excess"] >= t).mean()
        out[f"years_all_beats_nifty_by_{t:g}"] = (r["all_excess"] >= t).mean()
        out[f"top_share_beat_{t:g}"] = r[f"top_share_beat_{t:g}"].mean()
        out[f"all_share_beat_{t:g}"] = r[f"all_share_beat_{t:g}"].mean()
        out[f"years_topcats_beat_{t:g}"] = (r["top_cats_excess"] >= t).mean()
    diff = r["top_excess"] - r["all_excess"]
    out["top_minus_all_t"] = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))
    return out


# ---- 4. the call for the latest year ---------------------------------------------------

def restrict(data, exclude):
    """The same data without the given categories (e.g. Sector and Thematic funds)."""
    keep = ~data.panel["category"].isin(exclude)
    clone = Data(data.panel[keep].reset_index(drop=True), data.parameters, data.nifty,
                 data.full_years, data.partial_year, data.partial_label, data.indices,
                 data.benchmarks, data.nifty_partial)
    return clone


def current_call(data, ic, category_table):
    """Score funds on the latest parameters, with signals chosen from all past ICs."""
    year = data.partial_year or max(data.panel["param_year"])
    frame = data.panel[data.panel["param_year"] == year].copy()
    signals = choose_signals(ic, frame, data.parameters)
    frame["score"] = score(frame, signals)
    # Track record: parameter years with any value up to and including this one.
    history = data.panel[data.panel["param_year"] <= year]
    has_values = history[data.parameters].notna().any(axis=1)
    record = history[has_values].groupby("scheme_id")["param_year"].nunique()
    frame["record_years"] = frame["scheme_id"].map(record).fillna(0).astype(int)
    scored = frame.dropna(subset=["score"]).sort_values("score", ascending=False)
    scored["rank"] = range(1, len(scored) + 1)
    cut = max(1, int(round(len(scored) * TOP_SHARE)))
    scored["bucket"] = np.where(scored["rank"] <= cut, "Top 20%",
                                np.where(scored["rank"] > len(scored) - cut, "Bottom 20%", "Middle"))
    live = scored.dropna(subset=["fund_return"])
    check = {
        "year": year, "label": data.partial_label, "funds": len(live),
        "top": live.loc[live["bucket"] == "Top 20%", "fund_return"].mean(),
        "all": live["fund_return"].mean(),
        "bottom": live.loc[live["bucket"] == "Bottom 20%", "fund_return"].mean(),
        "nifty": data.nifty_partial,
        "score_ic": live["score"].corr(live["fund_return"], method="spearman"),
    }
    cats = scored.groupby("category").agg(funds=("score", "size"), avg_score=("score", "mean"),
                                          live_return=("fund_return", "mean"))
    cats["benchmark"] = [benchmark_of(c)[0].replace(" TRI", "") for c in cats.index]
    cats["benchmark_live"] = [index_return(data, benchmark_of(c)[1], data.partial_label)
                              for c in cats.index]
    cats = cats.sort_values("avg_score", ascending=False)
    cats["outlook_rank"] = range(1, len(cats) + 1)
    return signals, scored, cats, check
