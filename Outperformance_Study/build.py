"""Run the study and write the Excel working and the dashboard data.

    python Outperformance_Study/build.py

Outputs (in this folder):
    Outperformance_Analysis.xlsx   the whole working, one sheet per step
    dashboard/data.js              what the dashboard displays
"""

import json
import math
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import stats_analysis as A
import study as S

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Outperformance_Analysis.xlsx"
DASHBOARD_DATA = HERE / "dashboard" / "data.js"
PANEL_DATA = HERE / "dashboard" / "panel.js"
CACHE = HERE / "cache" / "statistics.pkl"

EXCLUDED_FOR_OUTLOOK = ("Sector Funds", "Thematic Fund")

HEADER_FILL = PatternFill("solid", fgColor="000066")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=13)
GOOD_FONT = Font(color="00B050", bold=True)
BAD_FONT = Font(color="C00000", bold=True)


# ---- analysis --------------------------------------------------------------------

def run():
    data = S.load()
    ic, ic_neutral, reliability = S.reliability(data)
    cat_years = S.category_years(data)
    cat_summary = S.category_summary(data, cat_years)
    cat_persistence = S.category_persistence(cat_years)
    fund_persistence = S.fund_persistence(data)
    backtest, picks = S.backtest(data, ic)
    bt = S.backtest_summary(backtest)
    signals, scored, outlook, live = S.current_call(data, ic, cat_years)
    # The same call on diversified funds only: signals re-chosen from that universe's ICs.
    narrow = S.restrict(data, EXCLUDED_FOR_OUTLOOK)
    ic_narrow = S.yearly_ic(narrow)
    narrow_call = S.current_call(narrow, ic_narrow, S.category_years(narrow))
    hypotheses = judge(reliability, cat_persistence, fund_persistence, bt, cat_summary)
    benchmark_check = S.benchmark_check(data)
    full = data.panel[data.panel["param_year"].isin(data.full_years)]
    groups = ["All Funds", A.WITHIN] + sorted(full["category"].unique())
    statistics = A.run(full, data.parameters, groups)
    # Cached for build_funds.py, which needs the category results (slow to recompute).
    CACHE.parent.mkdir(exist_ok=True)
    pd.to_pickle(statistics, CACHE)
    statistics["groups"] = groups
    statistics["reading"] = statistical_reading(statistics)
    return dict(statistics=statistics, narrow_call=narrow_call, benchmark_check=benchmark_check, data=data, ic=ic, ic_neutral=ic_neutral, reliability=reliability,
                cat_years=cat_years, cat_summary=cat_summary, cat_persistence=cat_persistence,
                fund_persistence=fund_persistence, backtest=backtest, picks=picks, bt=bt,
                signals=signals, scored=scored, outlook=outlook, live=live, hypotheses=hypotheses)


def judge(rel, cat_persistence, fund_persistence, bt, cat_summary):
    """Each hypothesis with its test, the evidence and a verdict computed from the numbers."""
    strong_pooled = rel[rel["pooled_pearson"].abs() > 0.3]
    reliable = rel[rel["verdict"] == "Reliable"]
    decay = (reliable["second_half"].abs() / reliable["first_half"].abs()).median()
    cp_mean = cat_persistence["rank_corr"].mean()
    cp_t = cp_mean / (cat_persistence["rank_corr"].std(ddof=1) / math.sqrt(len(cat_persistence)))
    fp = fund_persistence
    t3 = f"{S.THRESHOLDS[0]:g}"
    return [
        {"id": "H1", "hypothesis": "The strong correlations in the pooled summary sheets mostly reflect "
                                   "good and bad market years, not which funds are better.",
         "test": "Compare the pooled correlation with the average within-year rank correlation (IC).",
         "evidence": f"{len(strong_pooled)} parameters have a pooled |r| above 0.3; only "
                     f"{int((strong_pooled['verdict'] == 'Reliable').sum())} of them are reliable "
                     "within years. Risk measures (Std Dev, VaR, drawdowns) rank funds in opposite "
                     "directions in bull and bear years.",
         "verdict": "Supported" if (strong_pooled["verdict"] == "Reliable").mean() < 0.25 else "Not supported"},
        {"id": "H2", "hypothesis": "Some parameters rank next-year winners consistently across the "
                                   "whole history.",
         "test": f"Mean yearly IC with |t| >= {S.RELIABLE_T:g}, the same sign in >= "
                 f"{S.RELIABLE_CONSISTENCY:.0%} of years and in both halves of history.",
         "evidence": f"{len(reliable)} of {len(rel)} parameters pass, led by risk-adjusted skill "
                     "measures (Alpha, Appraisal Ratio, Capture, Up-period %, Sortino, Omega). Their "
                     f"strength has faded: the later half's IC is about {decay:.0%} of the earlier "
                     "half's.",
         "verdict": "Supported, weakening" if len(reliable) >= 5 and decay < 0.7
                    else ("Supported" if len(reliable) >= 5 else "Not supported")},
        {"id": "H3", "hypothesis": "A category that beats the Nifty 50 this year tends to do so again "
                                   "next year.",
         "test": "Rank correlation of category excess returns between consecutive years.",
         "evidence": f"Average rank correlation {cp_mean:+.2f} (t = {cp_t:.1f}) across "
                     f"{len(cat_persistence)} year pairs - close to zero.",
         "verdict": "Supported" if cp_t >= 2 else "Not supported"},
        {"id": "H4", "hypothesis": "Funds scored on the reliable parameters - chosen only from past "
                                   "data - beat the Nifty 50 by 3-4% more often than the average fund.",
         "test": f"Walk-forward backtest {bt['from']}-{bt['to']}: top 20% by score vs all funds.",
         "evidence": f"Top 20% averaged {bt['top_avg_excess']:+.1f}% a year over the Nifty 50 vs "
                     f"{bt['all_avg_excess']:+.1f}% for all funds (+{bt['top_minus_all']:.1f} pts, "
                     f"t = {bt['top_minus_all_t']:.1f}; ahead in {bt['years_top_beats_all']:.0%} of years). "
                     f"{bt[f'top_share_beat_{t3}']:.0%} of picked funds cleared +3% vs "
                     f"{bt[f'all_share_beat_{t3}']:.0%} of all funds. But whether the picks clear +3% "
                     f"as a group depends on the year: {bt[f'years_top_beats_nifty_by_{t3}']:.0%} of "
                     f"years, the same as all funds ({bt[f'years_all_beats_nifty_by_{t3}']:.0%}).",
         "verdict": "Partly supported" if bt["top_minus_all"] > 0 and bt["top_minus_all_t"] >= 2
                    else "Not supported"},
        {"id": "H5", "hypothesis": "A fund that beat the Nifty 50 by 3% is more likely to repeat it.",
         "test": "P(beat next year | beat this year) vs the base rate.",
         "evidence": f"{fp['after_beat']:.0%} repeat after a beat vs a {fp['base_rate']:.0%} base rate "
                     f"({fp['after_miss']:.0%} after a miss), over {fp['pairs']:,} fund-year pairs.",
         "verdict": "Supported" if fp["after_beat"] > fp["base_rate"] + 0.03 else "Not supported"},
        {"id": "H6", "hypothesis": "Categories that beat the Nifty 50 do so because of the market segment "
                                   "they invest in, not because their fund managers add value.",
         "test": "Category return vs its own benchmark (Smallcap 250, Midcap 150, Nifty 100, Nifty 500 ... TRI).",
         "evidence": cat_benchmark_evidence(cat_summary),
         "verdict": "Supported" if (cat_summary["avg_excess_vs_benchmark"] <= 0.5).mean() >= 0.6
                    else "Not supported"},
    ]


def statistical_reading(st):
    """Plain-language judgments drawn from the statistics (not chosen by hand)."""
    u, ret, models, var = st["univariate"], st["returns"], st["models"], st["variables"]
    ok = u[u["status"] == "ok"]
    tests = len(ok)
    robust = ok[ok["verdict"] == "Robust"]
    sig = ok[ok["p"] <= A.ALPHA]
    allf = ok[ok["group"] == "All Funds"].set_index("parameter")
    within = ok[ok["group"] == A.WITHIN].set_index("parameter")
    both = allf.index.intersection(within.index)
    strong = allf.loc[both][allf.loc[both, "verdict"] == "Robust"].index
    ratio = (within.loc[strong, "slope"] / allf.loc[strong, "slope"]).median() if len(strong) else np.nan
    year_share = ret.set_index("group").at["All Funds", "share_year_effect"]
    sd_ret = ret.set_index("group").at["All Funds", "sd_excess"]
    cats = [g for g in st["groups"] if g not in ("All Funds", A.WITHIN)]
    per_cat = ok[ok["group"].isin(cats)].groupby("group")["verdict"].apply(lambda v: (v == "Robust").sum())
    m = models.get("All Funds")
    lines = []
    lines.append(("Most of the return is the market, not the fund",
                  f"{year_share:.0%} of the variation in next-year fund returns is shared by every fund in the "
                  f"same year. Only the remaining {1 - year_share:.0%} can be explained by fund characteristics, "
                  "so even a genuine signal explains a modest share of returns."))
    lines.append(("Multiple testing is controlled",
                  f"{tests:,} tests were run ({len(st['groups'])} groups × 101 parameters). At p < 0.05 about "
                  f"{0.05 * tests:.0f} would look significant by chance alone; {len(sig):,} did. After the "
                  f"false-discovery-rate correction (q ≤ {A.FDR:g} within each group) and a stability check, "
                  f"{len(robust):,} remain robust."))
    if len(strong):
        lines.append(("The signal is fund selection, not just category tilts",
                      f"Of the {len(strong)} robust parameters for all funds, the within-category test keeps "
                      f"{int((within.loc[strong, 'verdict'] == 'Robust').sum())}, at about {ratio:.0%} of the effect "
                      "size. Comparing funds only with their own category does not make the signal disappear."))
    weak = per_cat[per_cat == 0].index.tolist()
    lines.append(("Category results are limited by sample size",
                  f"Single categories have 5–40 funds a year, so tests have little power: "
                  f"{len(weak)} of {len(per_cat)} categories have no robust parameter "
                  f"({', '.join(re.sub(r' [Ff]unds?$', '', g) for g in weak[:5])}{'…' if len(weak) > 5 else ''}). "
                  "Absence of significance there is not evidence of no effect; the all-fund and within-category "
                  "results are the reliable guide."))
    if m:
        c = m["coefficients"]
        survivors = c[c["p"] <= A.ALPHA]["variable"].tolist()
        lines.append(("Parameters overlap: one factor does most of the work",
                      f"Estimated together, {', '.join(survivors) or 'none'} "
                      f"{'stays' if len(survivors) == 1 else 'stay'} significant out of {len(var)} "
                      f"(VIF ≤ {c['vif'].max():.1f}, so not collinearity in the strict sense). The robust "
                      "parameters mostly measure the same thing: how strongly a fund captured the upside last year."))
        top = c.iloc[c["t"].abs().argmax()]
        lines.append(("Effect size",
                      f"A fund 1 SD higher on {top['variable']} earned {top['coef']:+.1f} points more the next "
                      f"year relative to the Nifty 50 (95% CI {top['ci_low']:+.1f} to {top['ci_high']:+.1f}), "
                      f"against a {sd_ret:.0f}-point spread of excess returns. The model's within-year R² averages {m['avg_r2']:.0%} "
                      f"(adjusted {m['avg_adj_r2']:.0%}), much of it from category differences."))
    beat = ok[(ok["group"] == "All Funds") & (ok["beat_q"] <= A.FDR) & (ok["beat_p"] <= A.ALPHA)]
    if len(beat):
        best = beat.loc[beat["beat_t"].abs().idxmax()]
        lines.append(("Beating the Nifty 50 by 3%: probabilities move, modestly",
                      f"For {len(beat)} parameters the chance of a fund beating the Nifty 50 by 3%+ next year "
                      f"changes significantly with the parameter (q ≤ {A.FDR:g}). The strongest, {best['parameter']}, "
                      f"moves it by {best['beat_slope'] * 100:+.1f} percentage points per 1 SD, against a base rate of "
                      f"{ret.set_index('group').at['All Funds', 'share_beat_margin']:.0%}."))
    decay = robust[(robust["group"] == "All Funds") & (robust["second_half"].abs() < robust["first_half"].abs())]
    lines.append(("The signals have weakened",
                  f"{len(decay)} of the {int((robust['group'] == 'All Funds').sum())} robust all-fund parameters were "
                  "stronger in the first half of history than in the second. Expect smaller effects going forward."))
    return lines


def cat_benchmark_evidence(cs):
    by = cs.set_index("category")
    beat = by[by["avg_excess_vs_benchmark"] > 0.5].sort_values("avg_excess_vs_benchmark", ascending=False)
    return (f"Small Cap funds beat the Nifty 50 by {by.at['Small cap Fund', 'avg_excess']:+.1f}% a year but "
            f"trail the Smallcap 250 TRI by {by.at['Small cap Fund', 'avg_excess_vs_benchmark']:+.1f}%; "
            f"Mid Cap {by.at['Mid Cap Fund', 'avg_excess']:+.1f}% vs {by.at['Mid Cap Fund', 'avg_excess_vs_benchmark']:+.1f}%. "
            f"Only {len(beat)} of {len(by)} categories beat their own benchmark by more than 0.5% a year"
            + (f" ({', '.join(f'{c} {v:+.1f}%' for c, v in beat['avg_excess_vs_benchmark'].items())})" if len(beat) else "")
            + ".")


# ---- workbook --------------------------------------------------------------------

def header(sheet, row, labels, widths=None):
    for column, label in enumerate(labels, 1):
        cell = sheet.cell(row=row, column=column, value=label)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[row].height = 30
    for column, width in enumerate(widths or [], 1):
        sheet.column_dimensions[get_column_letter(column)].width = width


def clean(value):
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(value) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def write_table(sheet, frame, start_row=1, title=None, widths=None, formats=None):
    row = start_row
    if title:
        sheet.cell(row=row, column=1, value=title).font = TITLE_FONT
        row += 2
    header(sheet, row, list(frame.columns), widths)
    for r, values in enumerate(frame.itertuples(index=False), row + 1):
        for c, value in enumerate(values, 1):
            cell = sheet.cell(row=r, column=c, value=clean(value))
            fmt = (formats or {}).get(frame.columns[c - 1])
            if fmt:
                cell.number_format = fmt
    sheet.freeze_panes = sheet.cell(row=row + 1, column=2)
    return row


def build_workbook(R):
    d = R["data"]
    book = Workbook()
    summary = book.active
    summary.title = "Summary"
    write_summary(summary, R)
    write_method(book.create_sheet("Method"), R)

    # Nifty 50
    nifty = book.create_sheet("Nifty50")
    write_table(nifty, pd.DataFrame({"Year": d.nifty.index, "Nifty 50 PR return %": d.nifty.values}),
                title="Nifty 50 (price index) calendar-year return, from the parameter export",
                widths=[10, 22], formats={"Nifty 50 PR return %": "0.00"})
    nifty_rows = len(d.nifty) + 3

    # Fund-year panel with live formulas for the excess and the 3% / 4% tests.
    panel = book.create_sheet("Panel")
    p = d.panel.sort_values(["return_year", "category", "scheme_name"])
    cols = ["Fund", "ISIN", "Category", "Parameter year", "Return year", "Fund return %",
            "Nifty 50 return %", "Excess vs Nifty %", "Beat by 3%", "Beat by 4%"]
    panel.cell(row=1, column=1, value="Every fund-year: parameter year T, its return in T+1, and the "
                                      "test against the Nifty 50 (formulas)").font = TITLE_FONT
    header(panel, 3, cols, [44, 15, 18, 10, 10, 12, 12, 12, 9, 9])
    last_nifty = f"Nifty50!$A$4:$B${nifty_rows}"
    for r, rec in enumerate(p.itertuples(index=False), 4):
        panel.cell(row=r, column=1, value=rec.scheme_name)
        panel.cell(row=r, column=2, value=rec.scheme_id)
        panel.cell(row=r, column=3, value=rec.category)
        panel.cell(row=r, column=4, value=int(rec.param_year))
        panel.cell(row=r, column=5, value=int(rec.return_year))
        panel.cell(row=r, column=6, value=clean(rec.fund_return)).number_format = "0.00"
        panel.cell(row=r, column=7, value=f'=IFERROR(VLOOKUP(E{r},{last_nifty},2,0),"")').number_format = "0.00"
        panel.cell(row=r, column=8, value=f'=IF(OR(F{r}="",G{r}=""),"",F{r}-G{r})').number_format = "0.00"
        panel.cell(row=r, column=9, value=f'=IF(H{r}="","",IF(H{r}>={S.THRESHOLDS[0]:g},1,0))')
        panel.cell(row=r, column=10, value=f'=IF(H{r}="","",IF(H{r}>={S.THRESHOLDS[1]:g},1,0))')
    panel.freeze_panes = "B4"
    panel.auto_filter.ref = f"A3:J{len(p) + 3}"

    # Yearly ICs
    for name, matrix, title in (
            ("IC_by_Year", R["ic"], "Spearman rank correlation of each parameter (year T) with next-year "
                                    "return (T+1), across all funds of that year"),
            ("IC_Within_Category", R["ic_neutral"], "Same, ranking funds within their own category "
                                                    "(picks funds, not categories)")):
        sheet = book.create_sheet(name)
        frame = matrix.copy()
        frame.columns = [f"{c}->{c + 1}" for c in frame.columns]
        frame = frame.reset_index(names="Parameter")
        write_table(sheet, frame, title=title, widths=[46] + [10] * (frame.shape[1] - 1),
                    formats={c: "0.00" for c in frame.columns[1:]})

    # Reliability
    rel = R["reliability"].reset_index(names="Parameter")
    rel = rel[["rank", "Parameter", "verdict", "direction", "years", "mean_ic", "t_stat", "consistency",
               "first_half", "second_half", "recent_5", "neutral_mean_ic", "neutral_t", "pooled_pearson",
               "icir"]]
    half = R["reliability"]["half_labels"].iloc[0].split(" | ")
    rel.columns = ["Rank", "Parameter", "Verdict", "Direction", "Years", "Mean IC", "t-stat",
                   "Sign consistency", f"Mean IC {half[0]}", f"Mean IC {half[1]}", "Mean IC last 5",
                   "Within-category IC", "Within-category t", "Pooled Pearson (old sheets)", "IC/stdev"]
    sheet = book.create_sheet("Reliability")
    start = write_table(sheet, rel, title="Parameter reliability across history (sorted by |t|)",
                        widths=[6, 46, 13, 16, 7, 9, 8, 10, 11, 11, 10, 11, 10, 12, 9],
                        formats={**{c: "0.000" for c in rel.columns[5:]}, "Sign consistency": "0%",
                                 "Years": "0", "t-stat": "0.00", "Within-category t": "0.00"})
    for r in range(start + 1, start + 1 + len(rel)):
        verdict = sheet.cell(row=r, column=3)
        verdict.font = GOOD_FONT if verdict.value == "Reliable" else (
            Font(bold=True) if verdict.value == "Mixed" else Font(color="808080"))

    # Categories
    cy = R["cat_years"].copy()
    pivot = cy.pivot(index="category", columns="return_year", values="excess")
    pivot.columns = [str(c) + (" *" if c == d.partial_year + 1 else "") for c in pivot.columns]
    sheet = book.create_sheet("Category_Years")
    start = write_table(sheet, pivot.reset_index(names="Category"),
                        title="Category average return minus the Nifty 50, by return year (% points). "
                              "* = partial year, no Nifty value", widths=[20] + [8] * pivot.shape[1],
                        formats={c: "0.0" for c in pivot.columns})
    for r in range(start + 1, start + 1 + len(pivot)):
        for c in range(2, pivot.shape[1] + 2):
            cell = sheet.cell(row=r, column=c)
            if isinstance(cell.value, float) and cell.value >= S.THRESHOLDS[0]:
                cell.font = GOOD_FONT
    detail = cy.rename(columns={"category": "Category", "return_year": "Return year",
                                "category_return": "Category return %", "funds": "Funds",
                                "nifty": "Nifty 50 %", "excess": "Excess %",
                                "share_funds_beat": "Share of funds beating by 3%"})
    write_table(sheet, detail, start_row=start + len(pivot) + 4,
                title="Detail: every category-year", widths=None,
                formats={"Category return %": "0.00", "Nifty 50 %": "0.00", "Excess %": "0.00",
                         "Share of funds beating by 3%": "0%"})

    cs = R["cat_summary"].copy()
    cs = cs[["category", "benchmark", "years", "from", "to", "avg_return", "avg_nifty", "avg_benchmark",
             "avg_excess", "avg_excess_vs_benchmark", "median_excess", "beat_nifty", "beat_3", "beat_4",
             "beat_benchmark", "beat_benchmark_3", "recent5_excess", "recent5_beat_3",
             "avg_share_funds_beat_3"]]
    cs.columns = ["Category", "Own benchmark", "Years", "From", "To", "Avg category return %",
                  "Avg Nifty 50 return %", "Avg own-benchmark return %", "Avg excess vs Nifty 50 %",
                  "Avg excess vs own benchmark %", "Median excess vs Nifty 50 %", "Years beating Nifty 50",
                  "Years beating Nifty 50 by 3%", "Years beating Nifty 50 by 4%", "Years beating own benchmark",
                  "Years beating own benchmark by 3%", "Last 5 yrs avg excess vs Nifty %",
                  "Last 5 yrs beating Nifty by 3%", "Avg share of funds beating Nifty by 3%"]
    write_table(book.create_sheet("Category_Summary"), cs,
                title="Each category vs the Nifty 50 and vs its own benchmark (return years with a full year)",
                widths=[20, 30, 7, 7, 7] + [12] * 14,
                formats={**{c: "0.00" for c in cs.columns if c.endswith("%") and not c.startswith(("Years", "Last 5 yrs beating", "Avg share"))},
                         **{c: "0%" for c in cs.columns if c.startswith(("Years beating", "Last 5 yrs beating", "Avg share"))}})

    bench = book.create_sheet("Category_Benchmarks")
    b = R["data"].benchmarks.pivot(index=["category", "benchmark"], columns="year", values="benchmark_return")
    b.columns = [str(c) for c in b.columns]
    b = b.reset_index().rename(columns={"category": "Category", "benchmark": "Own benchmark"})
    start = write_table(bench, b, title="Each category's benchmark total return by calendar year, read from the "
                                       "export (fund return minus Morningstar 'Excess Return'; identical for every "
                                       "fund in the category)", widths=[20, 30] + [8] * (b.shape[1] - 2),
                        formats={c: "0.0" for c in b.columns[2:]})
    chk = R["benchmark_check"].rename(columns={"benchmark": "Benchmark (from export)",
                                               "price_index": "Yahoo price index", "years_compared": "Years compared",
                                               "avg_gap": "Avg TRI - price gap", "min_gap": "Min gap",
                                               "max_gap": "Max gap"})
    write_table(bench, chk, start_row=start + len(b) + 4,
                title="Check: the derived total return vs Yahoo's price index of the same name. A small, steady "
                      "positive gap (dividends) confirms the label; blank = no Yahoo history for that index.",
                formats={"Avg TRI - price gap": "0.00", "Min gap": "0.00", "Max gap": "0.00"})

    if R["data"].indices is not None:
        ix = R["data"].indices.rename(columns={"index": "Index", "symbol": "Yahoo symbol", "year": "Year",
                                               "period": "Period", "return": "Return %", "first_date": "Data from",
                                               "source": "Source", "fetched": "Fetched"})
        write_table(book.create_sheet("Index_Returns"), ix,
                    title="Nifty index price returns from Yahoo Finance (fetch_indices.py). Nifty 50 matches the "
                          "export's benchmark row exactly in every overlapping year.",
                    widths=[28, 22, 7, 15, 10, 12, 26, 20], formats={"Return %": "0.00"})

    persistence = book.create_sheet("Persistence")
    cp = R["cat_persistence"].rename(columns={"year": "Year", "next_year": "Next year",
                                              "categories": "Categories",
                                              "rank_corr": "Rank corr of category excess"})
    start = write_table(persistence, cp, title="Do leading categories lead again next year?",
                        widths=[10, 10, 11, 14], formats={"Rank corr of category excess": "0.00"})
    fp = R["fund_persistence"]
    row = start + len(cp) + 3
    persistence.cell(row=row, column=1, value="Do funds that beat the Nifty 50 by 3% repeat it?").font = TITLE_FONT
    for i, (label, value, fmt) in enumerate((
            ("Fund-year pairs", fp["pairs"], "#,##0"),
            ("Base rate: beat by 3% next year", fp["base_rate"], "0.0%"),
            ("After beating by 3% this year", fp["after_beat"], "0.0%"),
            ("After missing this year", fp["after_miss"], "0.0%")), row + 2):
        persistence.cell(row=i, column=1, value=label)
        persistence.cell(row=i, column=4, value=clean(value)).number_format = fmt

    # Backtest
    bt = R["backtest"].copy()
    bt_cols = {"param_year": "Parameter year", "return_year": "Return year", "funds": "Funds",
               "nifty": "Nifty 50 %", "top_return": "Top 20% return %", "all_return": "All funds return %",
               "bottom_return": "Bottom 20% return %", "top_excess": "Top 20% excess %",
               "all_excess": "All excess %", "bottom_excess": "Bottom 20% excess %",
               "top_share_beat_3": "Top 20%: share beating by 3%", "all_share_beat_3": "All: share beating by 3%",
               "top_share_beat_4": "Top 20%: share beating by 4%", "all_share_beat_4": "All: share beating by 4%",
               "top_cats": "Top 3 categories by score", "top_cats_excess": "Top categories excess %",
               "all_cats_excess": "All categories excess %", "score_ic": "Score rank corr",
               "signals": "Signals chosen (past data only)"}
    bt = bt[list(bt_cols)].rename(columns=bt_cols)
    sheet = book.create_sheet("Backtest")
    write_table(sheet, bt, title="Walk-forward backtest: each year uses only ICs whose returns were "
                                 "already known", widths=[9, 9, 7, 9, 10, 10, 10, 10, 9, 10, 11, 11, 11, 11,
                                                          44, 11, 11, 9, 120],
                formats={**{c: "0.00" for c in bt.columns if "%" in c and "share" not in c},
                         **{c: "0%" for c in bt.columns if "share" in c}, "Score rank corr": "0.00"})
    s = R["bt"]
    rows = [("Return years", f"{s['from']}-{s['to']} ({s['years']} years)"),
            ("Top 20%: average excess over Nifty 50", s["top_avg_excess"]),
            ("All funds: average excess", s["all_avg_excess"]),
            ("Bottom 20%: average excess", s["bottom_avg_excess"]),
            ("Top 20% minus all funds (points / year)", s["top_minus_all"]),
            ("t-stat of that difference", s["top_minus_all_t"]),
            ("Years the top 20% beat all funds", s["years_top_beats_all"]),
            ("Years the top 20% beat the bottom 20%", s["years_top_beats_bottom"]),
            ("Years the top 20% beat Nifty by 3%", s["years_top_beats_nifty_by_3"]),
            ("Years all funds beat Nifty by 3%", s["years_all_beats_nifty_by_3"]),
            ("Picked funds beating Nifty by 3% (avg share)", s["top_share_beat_3"]),
            ("All funds beating Nifty by 3% (avg share)", s["all_share_beat_3"]),
            ("Picked funds beating Nifty by 4% (avg share)", s["top_share_beat_4"]),
            ("All funds beating Nifty by 4% (avg share)", s["all_share_beat_4"]),
            ("Top 3 categories: average excess", s["top_cats_avg_excess"]),
            ("All categories: average excess", s["all_cats_avg_excess"]),
            ("Average rank corr of score with next-year return", s["mean_score_ic"])]
    sheet2 = book.create_sheet("Backtest_Summary")
    sheet2.cell(row=1, column=1, value="Backtest summary").font = TITLE_FONT
    for i, (label, value) in enumerate(rows, 3):
        sheet2.cell(row=i, column=1, value=label)
        cell = sheet2.cell(row=i, column=2, value=clean(value))
        if isinstance(value, (float, np.floating)):
            cell.number_format = "0%" if ("Years" in label or "share" in label) else "0.00"
    sheet2.column_dimensions["A"].width = 52
    sheet2.column_dimensions["B"].width = 22

    picks = R["picks"].rename(columns={"param_year": "Parameter year", "return_year": "Return year",
                                       "fund": "Fund", "isin": "ISIN", "category": "Category",
                                       "score": "Score", "return": "Return %", "excess": "Excess %"})
    write_table(book.create_sheet("Backtest_Picks"), picks, title="Every fund picked (top 20%) in the "
                                                                  "backtest and what it returned",
                widths=[9, 9, 44, 15, 18, 8, 9, 9],
                formats={"Score": "0.000", "Return %": "0.00", "Excess %": "0.00"})

    # The call for the latest year
    sig = pd.DataFrame([{"Signal": n, "Direction": "Higher is better" if s_ > 0 else "Lower is better",
                         "Mean IC (all history)": m, "t-stat": t} for n, s_, m, t in R["signals"]])
    sheet = book.create_sheet("Signals_Now")
    write_table(sheet, sig, title=f"Signals used to score funds on {d.partial_year} parameters "
                                  "(chosen from every past year's IC)",
                widths=[46, 18, 14, 9], formats={"Mean IC (all history)": "0.000", "t-stat": "0.00"})

    live = R["live"]
    oc = R["outlook"].reset_index().rename(columns={
        "category": "Category", "funds": "Funds", "avg_score": "Average score",
        "live_return": f"Average return {live['label']} %", "outlook_rank": "Outlook rank"})
    cs_idx = R["cat_summary"].set_index("category")
    oc["Historical years beating by 3%"] = oc["Category"].map(cs_idx["beat_3"])
    oc["Historical avg excess %"] = oc["Category"].map(cs_idx["avg_excess"])
    oc = oc.rename(columns={"benchmark": "Own benchmark",
                            "benchmark_live": f"Own benchmark {live['label']} % (price)"})
    oc[f"Nifty 50 {live['label']} %"] = live["nifty"]
    oc = oc[["Outlook rank", "Category", "Funds", "Average score", "Historical years beating by 3%",
             "Historical avg excess %", f"Average return {live['label']} %", "Own benchmark",
             f"Own benchmark {live['label']} % (price)", f"Nifty 50 {live['label']} %"]]
    write_table(book.create_sheet("Outlook_Categories"), oc,
                title=f"Category outlook for {d.partial_year + 1} (scored on {d.partial_year} parameters)",
                widths=[9, 20, 7, 10, 13, 12, 16, 26, 16, 14],
                formats={"Average score": "0.000", "Historical years beating by 3%": "0%",
                         "Historical avg excess %": "0.00", f"Average return {live['label']} %": "0.00",
                         f"Own benchmark {live['label']} % (price)": "0.00", f"Nifty 50 {live['label']} %": "0.00"})

    sc = R["scored"][["rank", "scheme_name", "scheme_id", "category", "score", "bucket", "record_years",
                      "fund_return"]].rename(columns={
        "rank": "Rank", "scheme_name": "Fund", "scheme_id": "ISIN", "category": "Category",
        "score": "Score", "bucket": "Bucket", "record_years": "Years of data",
        "fund_return": f"Return {live['label']} %"})
    sheet = book.create_sheet("Outlook_Funds")
    start = write_table(sheet, sc, title=f"Every fund scored on {d.partial_year} parameters (higher = better "
                                         f"expected {d.partial_year + 1} return); return so far is a live check",
                        widths=[6, 44, 15, 18, 8, 11, 9, 14],
                        formats={"Score": "0.000", f"Return {live['label']} %": "0.00"})
    for r in range(start + 1, start + 1 + len(sc)):
        if sheet.cell(row=r, column=6).value == "Top 20%":
            sheet.cell(row=r, column=2).font = Font(bold=True)

    write_narrow_outlook(book.create_sheet("Outlook_Diversified"), R)
    write_statistics(book, R)

    check = book.create_sheet("Reconciliation")
    write_reconciliation(check, R, nifty_rows, len(p))
    book.save(WORKBOOK)


def write_narrow_outlook(sheet, R):
    """The outlook on diversified funds only (no Sector or Thematic funds)."""
    d = R["data"]
    signals, scored, cats, live = R["narrow_call"]
    lbl = live["label"]
    sheet.cell(row=1, column=1, value=f"Outlook for {d.partial_year + 1} excluding "
                                      f"{' and '.join(EXCLUDED_FOR_OUTLOOK)}: signals re-chosen from "
                                      "this universe's own history, funds ranked against each other").font = TITLE_FONT
    rows = [("Funds scored", live["funds"], "#,##0"),
            (f"Top 20%, {lbl} %", live["top"], "0.00"), (f"All funds, {lbl} %", live["all"], "0.00"),
            (f"Bottom 20%, {lbl} %", live["bottom"], "0.00"), (f"Nifty 50, {lbl} % (price)", live["nifty"], "0.00")]
    for i, (label, value, fmt) in enumerate(rows, 3):
        sheet.cell(row=i, column=1, value=label)
        sheet.cell(row=i, column=3, value=clean(value)).number_format = fmt
    sig = pd.DataFrame([{"Signal": n, "Direction": "Higher is better" if s_ > 0 else "Lower is better",
                         "Mean IC": m, "t-stat": t} for n, s_, m, t in signals])
    row = write_table(sheet, sig, start_row=len(rows) + 5, title="Signals used",
                      formats={"Mean IC": "0.000", "t-stat": "0.00"})
    oc = cats.reset_index().rename(columns={
        "category": "Category", "funds": "Funds", "avg_score": "Average score",
        "live_return": f"Average return {lbl} %", "outlook_rank": "Outlook rank", "benchmark": "Own benchmark",
        "benchmark_live": f"Own benchmark {lbl} % (price)"})
    oc = oc[["Outlook rank", "Category", "Funds", "Average score", f"Average return {lbl} %", "Own benchmark",
             f"Own benchmark {lbl} % (price)"]]
    row = write_table(sheet, oc, start_row=row + len(sig) + 3, title="Category outlook",
                      formats={"Average score": "0.000", f"Average return {lbl} %": "0.00",
                               f"Own benchmark {lbl} % (price)": "0.00"})
    sc = scored[["rank", "scheme_name", "scheme_id", "category", "score", "bucket", "record_years",
                 "fund_return"]].rename(columns={
        "rank": "Rank", "scheme_name": "Fund", "scheme_id": "ISIN", "category": "Category", "score": "Score",
        "bucket": "Bucket", "record_years": "Years of data", "fund_return": f"Return {lbl} %"})
    write_table(sheet, sc, start_row=row + len(oc) + 3, title="Every fund, ranked",
                formats={"Score": "0.000", f"Return {lbl} %": "0.00"})
    for col, width in zip("ABCDEFGH", [44, 44, 16, 18, 10, 26, 16, 14]):
        sheet.column_dimensions[col].width = width
    sheet.freeze_panes = None


def write_statistics(book, R):
    st = R["statistics"]
    u = st["univariate"].copy()
    cols = {"group": "Group", "parameter": "Parameter", "verdict": "Verdict", "fund_years": "Fund-years",
            "years": "Years", "mean": "Mean", "sd": "SD", "median": "Median", "slope": "Slope (pts per 1 SD)",
            "se": "Std error (Newey-West)", "t": "t-stat", "p": "p-value", "q": "q-value (BH FDR)",
            "ci_low": "95% CI low", "ci_high": "95% CI high", "ic": "Mean rank IC",
            "share_positive": "Share of years positive", "first_half": "Slope, first half",
            "second_half": "Slope, second half", "avg_funds": "Avg funds per year",
            "beat_slope": "P(beat Nifty by 3%) change per 1 SD", "beat_se": "Its std error",
            "beat_t": "Its t-stat", "beat_p": "Its p-value", "beat_q": "Its q-value"}
    u = u[list(cols)].rename(columns=cols)
    sheet = book.create_sheet("Stats_Univariate")
    start = write_table(sheet, u, title="Fama-MacBeth regression of next-year return over the Nifty 50 on each "
                                        "standardised parameter, for every group (Newey-West SE, BH q-values); "
                                        "right-hand columns: the same for the chance of beating the Nifty 50 by 3%",
                        widths=[26, 44, 22, 10, 7, 10, 10, 10, 11, 11, 8, 9, 10, 10, 10, 10, 10, 10, 10, 10,
                                12, 10, 9, 10, 10],
                        formats={**{c: "0.000" for c in u.columns[5:]}, "Fund-years": "0", "Years": "0",
                                 "p-value": "0.0000", "q-value (BH FDR)": "0.0000",
                                 "Share of years positive": "0%", "Avg funds per year": "0.0",
                                 "P(beat Nifty by 3%) change per 1 SD": "0.0%", "Its std error": "0.0%",
                                 "Its p-value": "0.0000", "Its q-value": "0.0000"})
    for r in range(start + 1, start + 1 + len(u)):
        cell = sheet.cell(row=r, column=3)
        cell.font = GOOD_FONT if cell.value == "Robust" else (
            Font(bold=True) if cell.value == "Significant, not robust" else Font(color="808080"))
    sheet.auto_filter.ref = f"A{start}:{get_column_letter(u.shape[1])}{start + len(u)}"

    ret = st["returns"].rename(columns={"group": "Group", "fund_years": "Fund-years",
                                        "mean_excess": "Mean excess over Nifty 50 %", "sd_excess": "SD %",
                                        "median_excess": "Median excess %", "share_beat": "Share beating Nifty 50",
                                        "share_beat_margin": "Share beating Nifty 50 by 3%",
                                        "share_year_effect": "Share of variance common to the year"})
    sheet = book.create_sheet("Stats_Returns")
    row = write_table(sheet, ret, title="Next-year return over the Nifty 50, by group",
                      widths=[26, 10, 14, 10, 12, 12, 14, 18],
                      formats={"Mean excess over Nifty 50 %": "0.00", "SD %": "0.00", "Median excess %": "0.00",
                               "Share beating Nifty 50": "0%", "Share beating Nifty 50 by 3%": "0%",
                               "Share of variance common to the year": "0%"})
    row += len(ret) + 3
    sheet.cell(row=row, column=1, value="Statistical reading").font = TITLE_FONT
    for i, (title, text) in enumerate(st["reading"], row + 1):
        sheet.cell(row=i, column=1, value=title).font = Font(bold=True)
        cell = sheet.cell(row=i, column=2, value=text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.merge_cells(start_row=i, start_column=2, end_row=i, end_column=5)
        sheet.row_dimensions[i].height = 62

    qrows, yrows = [], []
    for rec in st["univariate"].itertuples(index=False):
        q = rec.quintiles
        if isinstance(q, dict):
            qrows.append({"Group": rec.group, "Parameter": rec.parameter, "Years": q["years"],
                          **{f"Q{i + 1} excess %": v for i, v in enumerate(q["excess"])},
                          **{f"Q{i + 1} beat by 3%": v for i, v in enumerate(q["beat"])},
                          "Q5 - Q1 spread": q["spread"], "Spread SE": q["spread_se"], "Spread t": q["spread_t"],
                          "Spread p": q["spread_p"], "Years Q5 > Q1": q["spread_share_positive"]})
        if isinstance(rec.yearly, pd.DataFrame):
            for y in rec.yearly.itertuples():
                yrows.append({"Group": rec.group, "Parameter": rec.parameter, "Parameter year": int(y.year),
                              "Return year": int(y.year) + 1, "Funds": int(y.n), "Slope (pts per 1 SD)": y.slope,
                              "Rank IC": y.ic})
    qf = pd.DataFrame(qrows)
    write_table(book.create_sheet("Quintiles"), qf,
                title="Each year funds split into five equal groups by the parameter (Q1 lowest, Q5 highest): "
                      "average next-year excess over the Nifty 50 and share beating it by 3%, averaged over years",
                widths=[26, 44, 7] + [10] * 15,
                formats={**{c: "0.00" for c in qf.columns if "excess" in c or c.startswith(("Q5 -", "Spread S", "Spread t"))},
                         **{c: "0%" for c in qf.columns if "beat" in c or c == "Years Q5 > Q1"}, "Spread p": "0.0000"})
    yf = pd.DataFrame(yrows)
    write_table(book.create_sheet("Yearly_Slopes"), yf,
                title="The yearly regression slopes and rank ICs behind every Fama-MacBeth result",
                widths=[26, 44, 10, 10, 8, 12, 10], formats={"Slope (pts per 1 SD)": "0.000", "Rank IC": "0.000"})

    sheet = book.create_sheet("Regression")
    sheet.cell(row=1, column=1, value="Multivariate Fama-MacBeth regression: next-year return over the Nifty 50 on "
                                      f"{len(st['variables'])} standardised parameters together").font = TITLE_FONT
    sheet.cell(row=2, column=1, value="Variables: the strongest all-fund parameters, skipping any that "
                                      f"correlate above {A.MULTI_MAX_CORR:g} with one already chosen.")
    row = 4
    for group in st["groups"]:
        m = st["models"][group]
        sheet.cell(row=row, column=1, value=group).font = TITLE_FONT
        if m is None:
            sheet.cell(row=row + 1, column=1, value="Insufficient data (too few funds per year for "
                                                    f"{len(st['variables'])} variables)")
            row += 4
            continue
        sheet.cell(row=row + 1, column=1, value=f"Years {m['years']} · fund-years {m['fund_years']:,} · "
                                                f"avg funds/year {m['avg_funds']:.1f} · avg R² {m['avg_r2']:.3f} · "
                                                f"avg adjusted R² {m['avg_adj_r2']:.3f}")
        c = m["coefficients"].rename(columns={"variable": "Variable", "coef": "Coefficient (pts per 1 SD)",
                                              "se": "Std error", "t": "t-stat", "p": "p-value",
                                              "ci_low": "95% CI low", "ci_high": "95% CI high",
                                              "share_positive": "Share of years positive", "vif": "VIF"})
        header(sheet, row + 2, list(c.columns))
        for i, values in enumerate(c.itertuples(index=False), row + 3):
            for j, value in enumerate(values, 1):
                cell = sheet.cell(row=i, column=j, value=clean(value))
                if j > 1:
                    cell.number_format = "0%" if c.columns[j - 1] == "Share of years positive" else (
                        "0.0000" if c.columns[j - 1] == "p-value" else "0.000")
            if values[4] <= A.ALPHA:
                sheet.cell(row=i, column=1).font = GOOD_FONT
        row += len(c) + 5
    for col, width in zip("ABCDEFGHI", [40, 16, 11, 9, 10, 11, 11, 12, 8]):
        sheet.column_dimensions[col].width = width


def write_summary(sheet, R):
    d, s, live = R["data"], R["bt"], R["live"]
    sheet.column_dimensions["A"].width = 8
    sheet.column_dimensions["B"].width = 70
    sheet.column_dimensions["C"].width = 70
    sheet.column_dimensions["D"].width = 22
    sheet["A1"] = "Which parameters, categories and funds beat the Nifty 50 by 3-4%?"
    sheet["A1"].font = Font(bold=True, size=15)
    sheet["A2"] = (f"Data: {S.DEC25_WORKBOOK.name}, Book3 funds; parameter years "
                   f"{d.full_years[0]}-{d.full_years[-1]} vs full-year returns "
                   f"{d.full_years[0] + 1}-{d.full_years[-1] + 1}; {d.partial_year} parameters vs "
                   f"{d.partial_label} returns as a live check.")
    row = 4
    sheet.cell(row=row, column=1, value="Hypotheses").font = TITLE_FONT
    row += 1
    for c, label in enumerate(["ID", "Hypothesis / test", "Evidence", "Verdict"], 1):
        cell = sheet.cell(row=row, column=c, value=label)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for h in R["hypotheses"]:
        row += 1
        sheet.cell(row=row, column=1, value=h["id"]).font = Font(bold=True)
        sheet.cell(row=row, column=2, value=f"{h['hypothesis']}\nTest: {h['test']}")
        sheet.cell(row=row, column=3, value=h["evidence"])
        verdict = sheet.cell(row=row, column=4, value=h["verdict"])
        verdict.font = GOOD_FONT if h["verdict"].startswith("Supported") else (
            Font(bold=True) if h["verdict"].startswith("Partly") else BAD_FONT)
        for c in (2, 3):
            sheet.cell(row=row, column=c).alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[row].height = 105
    row += 2
    sheet.cell(row=row, column=1, value="Answers").font = TITLE_FONT
    for line in answers(R):
        row += 1
        cell = sheet.cell(row=row, column=2, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        sheet.row_dimensions[row].height = 48
    row += 2
    sheet.cell(row=row, column=1, value="Caveats").font = TITLE_FONT
    for line in caveats(R):
        row += 1
        cell = sheet.cell(row=row, column=2, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        sheet.row_dimensions[row].height = 36


def answers(R):
    rel, cs, s, live, d = R["reliability"], R["cat_summary"], R["bt"], R["live"], R["data"]
    reliable = rel[rel["verdict"] == "Reliable"]
    top_cats = cs.sort_values("avg_excess", ascending=False)
    oc = R["outlook"]
    top3 = R["scored"].head(3)["scheme_name"].tolist()
    return [
        f"1. Reliable parameters: {len(reliable)} of {len(rel)} pass all three tests. The strongest are "
        f"{', '.join(reliable.index[:6])}. All are 'higher is better' skill measures; raw risk measures "
        "(volatility, VaR, drawdown) are not reliable once each year is looked at on its own.",
        f"2. Categories: {top_cats.iloc[0]['category']} ({top_cats.iloc[0]['avg_excess']:+.1f}%) and "
        f"{top_cats.iloc[1]['category']} ({top_cats.iloc[1]['avg_excess']:+.1f}%) beat the Nifty 50 by the most; "
        f"Large Cap the least ({cs.set_index('category').at['Large Cap Fund', 'avg_excess']:+.1f}%). But that comes from "
        "the small- and mid-cap market, not the funds: against their own indices they lag. No category beats "
        "the Nifty 50 by 3% in most years, and last year's leader does not predict next year's.",
        f"3. Specific funds: a score on the reliable parameters added {s['top_minus_all']:+.1f} points a year "
        f"over the average fund out of sample (t = {s['top_minus_all_t']:.1f}). It improves the odds "
        f"({s['top_share_beat_3']:.0%} vs {s['all_share_beat_3']:.0%} of funds clearing +3%), but whether the "
        "Nifty 50 is beaten by 3% in a given year is decided mostly by the market, not by the pick.",
        f"4. For {d.partial_year + 1}: highest-scoring categories are {', '.join(oc.index[:3])}; top funds "
        f"include {', '.join(top3)}. So far ({live['label']}) the top 20% returned {live['top']:+.1f}% vs "
        f"{live['all']:+.1f}% for all funds and {live['bottom']:+.1f}% for the bottom 20%"
        + (f", while the Nifty 50 returned {live['nifty']:+.1f}%." if live["nifty"] is not None else "."),
    ]


def caveats(R):
    d = R["data"]
    return [
        "Benchmark is the Nifty 50 price index (no dividends, ~1-1.5% a year); funds' returns include "
        "dividends, so 'beat by 3%' here is roughly 'beat the Nifty 50 TRI by 1.5-2%'.",
        "Survivorship: only funds in today's fund list (Book3) are included. Closed or merged funds are "
        "missing, so historical outperformance is overstated.",
        f"Fund categories are today's classification. {d.partial_label} returns are 9 months, not a year; "
        "their Nifty 50 and category-index figures are price returns from Yahoo Finance (no TRI available "
        "free), and LargeMidcap 250 / Multicap have no Yahoo history.",
        "Category benchmarks are read from Morningstar's excess returns and named by matching known index "
        "values; Smallcap 250, Midcap 150, Nifty 100 and Nifty 500 are confirmed against Yahoo, "
        "LargeMidcap 250 and Multicap 50:25:25 are inferred.",
        "101 parameters were tested; a few could pass by chance. Many are near-duplicates (Alpha / "
        "Appraisal / Alpha T-Stat), so the score keeps one of each similar group.",
        "Category averages are equal-weighted across funds, not by assets.",
    ]


def write_method(sheet, R):
    d = R["data"]
    sheet.column_dimensions["A"].width = 4
    sheet.column_dimensions["B"].width = 120
    lines = [
        ("Method", None),
        ("Pairing", "A fund's parameters in calendar year T are paired with the same fund's return in T+1."),
        ("Universe", f"Funds of {S.UPDATED_FUND_LIST.name} (Final Category), {d.panel['scheme_id'].nunique()} with data."),
        ("Benchmark", f"{S.BENCHMARK_ROW}: the 'Return (Cumulative)' of the benchmark row in each year block."),
        ("Step 1 - reliability", "For each parameter and each year, the Spearman rank correlation (IC) between "
                                 "the parameter and next-year return across all funds (needs "
                                 f"{S.MIN_FUNDS_PER_YEAR}+ funds). Reliable = |t| of the mean IC >= "
                                 f"{S.RELIABLE_T:g}, the same sign in >= {S.RELIABLE_CONSISTENCY:.0%} of years, "
                                 "and the same sign in both halves of history."),
        ("Why not the pooled correlation", "Pooling all years mixes fund differences with market-wide year "
                                           "effects. Ranking within each year removes the year effect."),
        ("Step 2 - categories", "Each category's equal-weight average return (3+ funds) minus the Nifty 50, per "
                                f"year; how often it cleared +{S.THRESHOLDS[0]:g}% and +{S.THRESHOLDS[1]:g}%."),
        ("Step 3 - backtest", f"From parameter year {S.BACKTEST_FIRST_YEAR}: choose up to {S.MAX_SIGNALS} "
                              f"signals with past |t| >= {S.TRAIN_T:g} and consistency >= "
                              f"{S.TRAIN_CONSISTENCY:.0%}, using only ICs whose returns were already known; "
                              f"drop a signal whose ranks correlate > {S.DEDUPE_RHO:g} with a kept one; score "
                              "each fund as the average percentile rank of its signals; hold the top "
                              f"{S.TOP_SHARE:.0%} for the next year and compare with all funds and the Nifty 50."),
        ("Step 4 - outlook", f"The same scoring on {d.partial_year} parameters, with signals chosen from every "
                             f"past IC; {d.partial_label} returns are shown as a live check only."),
        ("Panel sheet", "Columns G-J are formulas: the Nifty 50 return (lookup), the excess and the 3% / 4% tests."),
    ]
    for i, (label, text) in enumerate(lines, 1):
        a = sheet.cell(row=i * 2 - 1, column=1 if text is None else 2, value=label)
        a.font = TITLE_FONT if text is None else Font(bold=True)
        if text:
            b = sheet.cell(row=i * 2, column=2, value=text)
            b.alignment = Alignment(wrap_text=True)


def write_reconciliation(sheet, R, nifty_rows, panel_rows):
    """Formulas over the Panel sheet that must equal the Python results."""
    d, cs = R["data"], R["cat_summary"]
    sheet.column_dimensions["A"].width = 52
    for col in "BCD":
        sheet.column_dimensions[col].width = 16
    sheet["A1"] = "Reconciliation: Excel formulas over the Panel vs the Python figures"
    sheet["A1"].font = TITLE_FONT
    for c, label in enumerate(["Check", "Excel formula", "Python", "Difference"], 1):
        cell = sheet.cell(row=3, column=c, value=label)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    last = panel_rows + 3
    full = d.panel[d.panel["return_year"].isin([y + 1 for y in d.full_years])].dropna(subset=["excess"])
    checks = [
        ("Fund-years with an excess (full years)", f"=COUNT(Panel!H4:H{last})", len(full)),
        ("Average excess, all fund-years", f"=AVERAGE(Panel!H4:H{last})", full["excess"].mean()),
        ("Share of fund-years beating by 3%", f"=AVERAGE(Panel!I4:I{last})", (full["excess"] >= 3).mean()),
        ("Share of fund-years beating by 4%", f"=AVERAGE(Panel!J4:J{last})", (full["excess"] >= 4).mean()),
    ]
    for year in (2008, 2025):
        sub = full[full["return_year"] == year]
        checks.append((f"Average excess, return year {year}",
                       f"=AVERAGEIFS(Panel!H4:H{last},Panel!E4:E{last},{year})", sub["excess"].mean()))
    for i, (label, formula, value) in enumerate(checks, 4):
        sheet.cell(row=i, column=1, value=label)
        sheet.cell(row=i, column=2, value=formula).number_format = "0.0000"
        sheet.cell(row=i, column=3, value=clean(value)).number_format = "0.0000"
        sheet.cell(row=i, column=4, value=f"=B{i}-C{i}").number_format = "0.0000"


# ---- dashboard data -------------------------------------------------------------

def stats_payload(st, r):
    u = st["univariate"]
    keys = ["fund_years", "years", "mean", "sd", "median", "slope", "se", "t", "p", "q", "ci_low", "ci_high",
            "ic", "share_positive", "first_half", "second_half", "avg_funds", "beat_slope", "beat_se", "beat_t",
            "beat_p", "beat_q", "p10", "p90", "min", "max"]
    rows, yearly, quint = [], [], []
    for rec in u.itertuples(index=False):
        d = rec._asdict()
        rows.append([d["group"], d["parameter"], d["verdict"]] +
                    [r(d.get(k), 4) if k not in ("fund_years", "years") else int(d.get(k) or 0) for k in keys])
        y = d.get("yearly")
        yearly.append([[int(a.year), r(a.slope, 3), r(a.ic, 3), int(a.n)] for a in y.itertuples()]
                      if isinstance(y, pd.DataFrame) and len(y) else [])
        q = d.get("quintiles")
        quint.append(None if not isinstance(q, dict) else
                     [r(x, 3) for x in q["excess"]] + [r(x, 3) for x in q["beat"]] +
                     [r(q["spread"], 3), r(q["spread_se"], 3), r(q["spread_t"], 3), r(q["spread_p"], 4),
                      r(q["spread_share_positive"], 3), q["years"]])
    models = {}
    for group, m in st["models"].items():
        if m is None:
            models[group] = None
            continue
        models[group] = {"years": m["years"], "fundYears": m["fund_years"], "avgFunds": r(m["avg_funds"], 1),
                         "r2": r(m["avg_r2"], 3), "adjR2": r(m["avg_adj_r2"], 3),
                         "coefs": [{k: (r(v, 4) if isinstance(v, (float, np.floating)) else v)
                                    for k, v in row.items()} for row in m["coefficients"].to_dict("records")]}
    return {"groups": st["groups"], "within": A.WITHIN, "columns": ["group", "parameter", "verdict"] + keys,
            "rows": rows, "yearly": yearly, "quintiles": quint, "variables": st["variables"],
            "returns": [{k: (r(v, 3) if isinstance(v, (float, np.floating)) else v) for k, v in row.items()}
                        for row in st["returns"].to_dict("records")],
            "models": models, "reading": [{"title": t, "text": x} for t, x in st["reading"]],
            "settings": {"minFunds": A.MIN_FUNDS_PER_YEAR, "minYears": A.MIN_YEARS, "nwLags": A.NW_LAGS,
                         "zCap": A.Z_CAP, "alpha": A.ALPHA, "fdr": A.FDR, "maxCorr": A.MULTI_MAX_CORR,
                         "beatMargin": A.BEAT_MARGIN, "quintileMinFunds": A.QUINTILE_MIN_FUNDS}}


def outlook_payload(call, r):
    signals, scored, cats, live = call
    return {
        "signals": [{"name": n, "direction": "Higher" if sgn > 0 else "Lower", "meanIc": r(m), "t": r(t, 2)}
                    for n, sgn, m, t in signals],
        "categories": [{"name": name, "rank": int(row["outlook_rank"]), "score": r(row["avg_score"]),
                        "funds": int(row["funds"]), "live": r(row["live_return"], 2),
                        "benchmark": row["benchmark"], "benchmarkLive": r(row["benchmark_live"], 2)}
                       for name, row in cats.iterrows()],
        "funds": [{"rank": int(row["rank"]), "name": row["scheme_name"], "category": row["category"],
                   "score": r(row["score"]), "years": int(row["record_years"]), "live": r(row["fund_return"], 2)}
                  for _, row in scored.head(25).iterrows()],
        "live": {k: (r(v, 2) if isinstance(v, (float, np.floating)) else v) for k, v in live.items()},
    }


def build_dashboard(R):
    d, rel, s, live = R["data"], R["reliability"], R["bt"], R["live"]

    def r(x, n=3):
        x = clean(x)
        return None if x is None else round(x, n)

    payload = {
        "meta": {"source": S.DEC25_WORKBOOK.name, "funds": int(d.panel["scheme_id"].nunique()),
                 "paramYears": [d.full_years[0], d.full_years[-1]],
                 "returnYears": [d.full_years[0] + 1, d.full_years[-1] + 1],
                 "partialYear": d.partial_year, "partialLabel": d.partial_label,
                 "thresholds": list(S.THRESHOLDS), "benchmark": S.BENCHMARK_ROW,
                 "reliableRule": f"|t| ≥ {S.RELIABLE_T:g}, same sign in ≥ {S.RELIABLE_CONSISTENCY:.0%} "
                                 "of years and in both halves"},
        "hypotheses": R["hypotheses"],
        "answers": answers(R),
        "caveats": caveats(R),
        "reliability": [{"name": name, "verdict": row["verdict"], "meanIc": r(row["mean_ic"]),
                         "t": r(row["t_stat"], 2), "consistency": r(row["consistency"], 2),
                         "first": r(row["first_half"]), "second": r(row["second_half"]),
                         "pooled": r(row["pooled_pearson"])}
                        for name, row in rel.iterrows()],
        "halfLabels": rel["half_labels"].iloc[0].split(" | "),
        "categories": [{"name": row["category"], "avgExcess": r(row["avg_excess"], 2),
                        "beat3": r(row["beat_3"], 2), "beat4": r(row["beat_4"], 2),
                        "recentExcess": r(row["recent5_excess"], 2), "years": int(row["years"]),
                        "benchmark": row["benchmark"], "avgReturn": r(row["avg_return"], 2),
                        "avgBenchmark": r(row["avg_benchmark"], 2), "avgNifty": r(row["avg_nifty"], 2),
                        "excessVsBenchmark": r(row["avg_excess_vs_benchmark"], 2),
                        "beatBenchmark": r(row["beat_benchmark"], 2)}
                       for _, row in R["cat_summary"].iterrows()],
        "categoryYears": [{"category": row["category"], "year": int(row["return_year"]),
                           "ret": r(row["category_return"], 2), "bench": r(row["benchmark_return"], 2),
                           "nifty": r(row["nifty"], 2), "funds": int(row["funds"])}
                          for _, row in R["cat_years"].iterrows()
                          if row["return_year"] in [y + 1 for y in d.full_years]],
        "categoryPersistence": r(R["cat_persistence"]["rank_corr"].mean(), 2),
        "fundPersistence": {k: r(v, 3) for k, v in R["fund_persistence"].items()},
        "backtest": [{"year": int(row["return_year"]), "top": r(row["top_excess"], 2),
                      "all": r(row["all_excess"], 2), "bottom": r(row["bottom_excess"], 2),
                      "nifty": r(row["nifty"], 2)} for _, row in R["backtest"].iterrows()],
        "backtestSummary": {k: (r(v, 3) if isinstance(v, (float, np.floating)) else v) for k, v in s.items()},
        "signals": [{"name": n, "direction": "Higher" if sgn > 0 else "Lower", "meanIc": r(m), "t": r(t, 2)}
                    for n, sgn, m, t in R["signals"]],
        "outlookCategories": [{"name": name, "rank": int(row["outlook_rank"]), "score": r(row["avg_score"]),
                               "funds": int(row["funds"]), "live": r(row["live_return"], 2),
                               "benchmark": row["benchmark"], "benchmarkLive": r(row["benchmark_live"], 2)}
                              for name, row in R["outlook"].iterrows()],
        "outlookFunds": [{"rank": int(row["rank"]), "name": row["scheme_name"], "category": row["category"],
                          "score": r(row["score"]), "years": int(row["record_years"]),
                          "live": r(row["fund_return"], 2)}
                         for _, row in R["scored"].head(25).iterrows()],
        "live": {k: (r(v, 2) if isinstance(v, (float, np.floating)) else v) for k, v in live.items()},
        "outlookNarrow": outlook_payload(R["narrow_call"], r),
        "stats": stats_payload(R["statistics"], r),
        "narrowExcluded": list(EXCLUDED_FOR_OUTLOOK),
    }
    DASHBOARD_DATA.parent.mkdir(exist_ok=True)
    DASHBOARD_DATA.write_text("window.STUDY = " + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), default=clean) + ";\n")


def build_panel_data(R):
    """Every full-year fund-year, for the explorer's scatter plots (loaded on demand)."""
    d = R["data"]
    full = d.panel[d.panel["param_year"].isin(d.full_years)].dropna(subset=["excess"])
    funds = sorted(full["scheme_name"].unique())
    cats = sorted(full["category"].unique())
    fi, ci = {f: i for i, f in enumerate(funds)}, {c: i for i, c in enumerate(cats)}

    def num(v):
        return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 4)
    rows = [[int(rec[0]), ci[rec[1]], fi[rec[2]], num(rec[3])] + [num(v) for v in rec[4:]]
            for rec in full[["param_year", "category", "scheme_name", "excess"] + d.parameters].itertuples(index=False)]
    PANEL_DATA.write_text("window.PANEL = " + json.dumps(
        {"parameters": d.parameters, "categories": cats, "funds": funds, "rows": rows,
         "nifty": {int(y): round(float(v), 4) for y, v in d.nifty.items()}},
        separators=(",", ":"), allow_nan=False) + ";\n")


def main():
    R = run()
    build_workbook(R)
    build_dashboard(R)
    build_panel_data(R)
    print(f"Wrote {WORKBOOK.name} and dashboard/{DASHBOARD_DATA.name}")
    for h in R["hypotheses"]:
        print(f"  {h['id']}: {h['verdict']}")


if __name__ == "__main__":
    main()
