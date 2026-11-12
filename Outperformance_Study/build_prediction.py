"""Backtest the Statistical analysis parameters and predict the next year with the feasible ones.

    python build.py              # once: caches the Statistical analysis (cache/statistics.pkl)
    python build_prediction.py

Outputs:
    Stats_Prediction.xlsx        the working: candidates, backtest by year, prediction, every fund
    dashboard/prediction.js      data for the dashboard's Testing & prediction tab
"""

import json
import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

import stats_prediction as SP
import study as S
from build import CACHE, TITLE_FONT, clean, write_table

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Stats_Prediction.xlsx"
DATA = HERE / "dashboard" / "prediction.js"


def short(name):
    return name.replace(" Funds", "").replace(" Fund", "").replace("Small cap", "Small Cap")


def col(n):
    return get_column_letter(n)


def put_formulas(sheet, first_row, n_rows, column, template):
    """template uses {r} for the row number."""
    for r in range(first_row, first_row + n_rows):
        sheet.cell(row=r, column=column, value=template.format(r=r))


# basket label of a predicted excess (cell reference c), matching SP.basket_label
BASKET_F = '=IF({c}="","",IF({c}<0,"below 0%",IF({c}>=10,"10% and above",INT({c})&"-"&(INT({c})+1)&"%")))'


def note(sheet, row, text):
    sheet.cell(row=row, column=1, value=text).font = Font(italic=True)


def find_row(sheet, match):
    """First data row (from 4) whose cells equal match {column number: value}."""
    for r in range(4, sheet.max_row + 1):
        if all(sheet.cell(row=r, column=c).value == v for c, v in match.items()):
            return r
    return None


def write_guide(book, R, data, cut):
    """Read_Me: what the workbook says, how the sheets connect, and worked examples to
    check by hand with exact sheet / row references."""
    T, ly, ty = SP.TARGET, R["latest_year"], R["target_year"]
    a, b = R["test"]
    G = {g["name"]: g for g in R["groups"]}
    sh = book.create_sheet("Read_Me", 0)
    sh.column_dimensions["A"].width = 26
    sh.column_dimensions["B"].width = 118
    row = [1]

    def line(k, v=None, bold=False, title=False):
        c = sh.cell(row=row[0], column=1, value=k)
        c.font = TITLE_FONT if title else Font(bold=True)
        if v is not None:
            cell = sh.cell(row=row[0], column=2, value=v)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if bold:
                cell.font = Font(bold=True)
            sh.row_dimensions[row[0]].height = max(15, 15 * (len(str(v)) // 115 + 1))
        row[0] += 1

    def gap():
        row[0] += 1

    # ---- the answer
    line("READ ME FIRST", title=True)
    gap()
    feas_all = {n: SP.predict(g, cut)[0] for n, g in G.items()}
    best = []
    for n, g in G.items():
        kept = [r for r in g["params"] if r["status"][0] == 0 and r["backtest"]["calls"]]
        if kept:
            x = max(kept, key=lambda r: r["backtest"]["hits"] / r["backtest"]["calls"])
            best.append((n, x))
    any_feas = any(feas_all.values())
    line("The question", f"Does a fund beat the Nifty 50 by {T:g}%+ in the next calendar year, and which parameters from the "
                         f"Statistical analysis can tell that in advance? Prediction period: calendar {ty} (1 Jan - 31 Dec {ty}).")
    line("The answer", ("Feasible parameters found: " + "; ".join(f"{n}: {', '.join(r['parameter'] for r in f)}" for n, f in feas_all.items() if f))
         if any_feas else
         f"No parameter passes. A parameter must be right on more than {cut:.0%} of funds in the backtest (returns {a + 1}-{b + 1}) "
         f"AND more often than the naive call (the same answer for every fund from the category's own past). None does, so this "
         f"workbook makes no {ty} prediction; the prediction sheets say so.", bold=True)
    for n, x in best:
        bt = x["backtest"]
        line(f"  closest in {n}", f"{x['parameter']}: right {bt['hits']} of {bt['calls']} = {bt['hits'] / bt['calls']:.1%}; naive "
                                  f"right {bt['naive']} = {bt['naive'] / bt['calls']:.1%}.")
    weak = [short(g["name"]) for g in R["groups"] if g["tier"] == SP.TIERS[1]]
    line("Candidates by category", "All Funds, Flexi Cap, Large Cap and Mid Cap have parameters the Statistical analysis rates Robust "
                                   "(p <= 0.05, q <= 0.10, same sign in both halves); those are their candidates. The other categories "
                                   "have none (20-40 funds a year is too few to pass all three checks), so their candidates are the "
                                   "parameters that are significant (p <= 0.05) but not Robust - a weaker starting point, labelled "
                                   f"in Group_Summary and Shortlist: {', '.join(weak)}. Every category then faces the same backtest.")
    untested = [short(g["name"]) for g in R["groups"] if g["candidates"] and not any(
        r.get("backtest") and r["backtest"]["calls"] for r in g["params"] if r["status"][0] == 0)]
    if untested:
        line("Not testable", f"{', '.join(untested)}: too few funds a year to split into fifths over {SP.MIN_PAST_YEARS}+ past years, "
                             "so the candidates exist but cannot be backtested (blank in Group_Summary).")
    line("100% = naive", "A hit ratio equal to the naive one (e.g. 100% vs 100%) means the parameter gave every fund the same "
                         "answer as the naive call; it adds nothing, so it is not feasible.")
    line("Three hit ratios", f"(1) the {T:g}% call (the rule above); (2) within tolerance: right if |actual - predicted| <= the "
                             f"tolerance in Shortlist cell Z2 (default {SP.TOLERANCE} points); (3) actual >= predicted. Each is "
                             "compared with the naive call. (3) rewards low predictions, so it only means something next to naive. "
                             "Shortlist columns Y-AH; Backtest_Calls columns P-U.")
    gap()

    # ---- how to read
    line("HOW THE SHEETS CONNECT", title=True)
    gap()
    for k, v in [
        ("1  Fund_Data", f"The raw data: every fund-year. Parameter year T with the return in T+1; Excess = fund return - Nifty 50 (formula)."),
        ("2  Statistical_Analysis", "The Statistical analysis tab's results; Verdict = 'Robust' makes a parameter a candidate."),
        ("3  Shortlist", "Every candidate: unique, or a version of / moving with a stronger one. For unique ones: backtest calls, "
                         "right, hit ratio, naive, precision, Feasible? - all formulas reading Backtest_Calls and Live_Check."),
        ("4  Group_Yearly_Excess", "The category's average excess each year: the input of the naive call."),
        ("5  Quintile_History", "For each unique candidate and year: funds split into fifths (Q1 lowest values), each fifth's "
                                "average excess the next year: the input of every prediction."),
        ("6  Backtest_Calls", f"One row per fund per test year (parameters {a}-{b}): predicted excess = AVERAGEIFS over Quintile_History, "
                              f"years before only; call; actual; Right (1/0); naive call; Naive right (1/0)."),
        ("7  Backtest", "The same calls totalled by parameter and year."),
        ("8  Prediction_Weights, Fund_Placement, Fund_Predictions", f"Only for feasible parameters: the {ly} fifth of each fund, "
                              f"weights by |t|, and the {ty} prediction (formulas)."),
        ("9  Live_Check", f"Each candidate's call for {ly} -> {R['live_label']} (nine months) against what happened so far."),
        ("Tip", "Every table has filters on its header row: filter Group and Parameter to see one parameter's rows."),
    ]:
        line(k, v)
    gap()

    # ---- worked example 1: one backtest call
    n, x = max(best, key=lambda t: t[1]["backtest"]["hits"] / t[1]["backtest"]["calls"] - t[1]["backtest"]["naive"] / t[1]["backtest"]["calls"])
    g, par = G[n], x["parameter"]
    year = max(t["year"] for t in x["backtest"]["years"])
    calls_y = [c for c in x["backtest"]["detail"] if c["year"] == year]
    c = sorted([c for c in calls_y if c["pred"] >= T and c["excess"] >= T] or calls_y, key=lambda c: c["fund"])[0]
    fd, qh, gy, bc, slr = book["Fund_Data"], book["Quintile_History"], book["Group_Yearly_Excess"], book["Backtest_Calls"], book["Shortlist"]
    pcol = next(i for i in range(1, fd.max_column + 1) if fd.cell(row=3, column=i).value == par)
    fr_ = find_row(fd, {1: c["fund"], 3: year})
    hist = SP.fifth_history(g["rows"], par)
    yr_ = hist[year]
    vals = sorted(yr_[par])
    rank = sum(1 for v in vals if v < c["value"]) + 1
    past = sorted(t for t in hist if t < year)
    past_avgs = [(t, float(hist[t].groupby("fifth")["excess"].mean().get(c["fifth"]))) for t in past]
    qrows = [find_row(qh, {1: n, 2: par, 3: t}) for t in past]
    ym = g["rows"].groupby("param_year")["excess"].mean()
    naive_avg = float(ym[ym.index < year].mean())
    grows = [find_row(gy, {1: n, 2: int(t)}) for t in ym.index if t < year]
    br = find_row(bc, {1: n, 2: par, 3: year, 5: c["fund"]})
    qletter = col(5 + c["fifth"])
    line(f"VERIFY BY HAND - 1. one backtest call", title=True)
    gap()
    line("Example", f"{c['fund']} ({n}), parameter {par}, parameter year {year} -> return year {year + 1}. "
                    f"It is row {br} of Backtest_Calls.", bold=True)
    line("Step 1  the fund's value", f"Fund_Data row {fr_}, column {col(pcol)} ({par}) = {c['value']:.4f}. Same row: fund return "
                                     f"{fd.cell(row=fr_, column=5).value:.2f}% and Nifty 50 {fd.cell(row=fr_, column=6).value:.2f}% "
                                     f"in {year + 1}, so excess = {c['excess']:.2f}%.")
    line("Step 2  its fifth", f"In {year}, {len(vals)} {short(n)} funds have a value. Filter Fund_Data on Category = {n} and Parameter "
                              f"year = {year} and sort by {par}: this fund ranks {rank} of {len(vals)} (lowest = 1), so it is in "
                              f"fifth Q{c['fifth']} (each fifth holds about {len(vals) / 5:.0f} funds).")
    line("Step 3  predicted excess", f"Quintile_History, Group = {n}, Parameter = {par}, years before {year} (rows "
                                     f"{min(qrows)}-{max(qrows)}), column {qletter} (Q{c['fifth']}): "
                                     + ", ".join(f"{t}: {v:+.2f}" for t, v in past_avgs)
                                     + f". Average of these {len(past_avgs)} = {c['pred']:+.2f}%. (Backtest_Calls column H.)")
    line("Step 4  the call", f"{c['pred']:+.2f}% {'>=' if c['pred'] >= T else '<'} {T:g}%, so the call is "
                             f"'{'Beat ' + format(T, 'g') + '%+' if c['pred'] >= T else 'No'}'. Actual excess {c['excess']:+.2f}% "
                             f"{'>=' if c['excess'] >= T else '<'} {T:g}%, so it {'did' if c['excess'] >= T else 'did not'} beat by "
                             f"{T:g}%. Right = {int((c['pred'] >= T) == (c['excess'] >= T))} (columns I, K, L).")
    line("Step 5  the naive call", f"Group_Yearly_Excess, Group = {n}, years before {year} (rows {min(grows)}-{max(grows)}), "
                                   f"column E: average = {naive_avg:+.2f}%, so the naive call for every {short(n)} fund is "
                                   f"'{'Beat' if naive_avg >= T else 'No'}' and it is "
                                   f"{'right' if (naive_avg >= T) == (c['excess'] >= T) else 'wrong'} here (columns M, N, O).")
    gap()

    # ---- worked example 2: the feasibility decision
    srow = find_row(slr, {1: n, 2: par})
    bt = x["backtest"]
    line("VERIFY BY HAND - 2. is the parameter feasible?", title=True)
    gap()
    line("Example", f"{par} for {n}: Shortlist row {srow}.", bold=True)
    line("Calls", f"Backtest_Calls filtered on Group = {n} and Parameter = {par}: {bt['calls']} rows (all {short(n)} funds with a "
                  f"value in {a}-{b}). Shortlist column H.")
    line("Right", f"Sum of column L (Right) over those rows = {bt['hits']}; hit ratio = {bt['hits']} / {bt['calls']} = "
                  f"{bt['hits'] / bt['calls']:.1%}. Shortlist columns I, J.")
    line("Naive", f"Sum of column O (Naive right) = {bt['naive']} = {bt['naive'] / bt['calls']:.1%}. Shortlist columns K, L.")
    line("Precision", f"Rows with Call = 'Beat {T:g}%+': {bt['called']}; of those actually beat: {bt['called_right']}"
                      + (f" = {bt['called_right'] / bt['called']:.1%}" if bt['called'] else "") + ". Shortlist columns M-O.")
    ok = bt["calls"] >= SP.MIN_CALLS and bt["hits"] / bt["calls"] > cut and bt["hits"] > bt["naive"]
    line("Decision", f"Feasible needs calls >= {SP.MIN_CALLS} ({bt['calls']}: {'yes' if bt['calls'] >= SP.MIN_CALLS else 'no'}), "
                     f"hit ratio > {cut:.0%} ({bt['hits'] / bt['calls']:.1%}: {'yes' if bt['hits'] / bt['calls'] > cut else 'no'}) and "
                     f"right > naive right ({bt['hits']} vs {bt['naive']}: {'yes' if bt['hits'] > bt['naive'] else 'no'}) -> "
                     f"{'FEASIBLE' if ok else 'NOT feasible'}. Shortlist column P.", bold=True)
    gap()

    # ---- worked example 3: how a prediction is built
    line("VERIFY BY HAND - 3. a prediction", title=True)
    gap()
    line("How it is built", f"For each feasible parameter: the fund's {ly} value -> its fifth among the group's {ly} funds "
                            f"(Fund_Placement column G) -> that fifth's average over all years (Prediction_Weights columns H-L = "
                            f"AVERAGEIFS over Quintile_History) -> x weight (|t| / the fund's total |t|) = contribution. "
                            f"Prediction = sum of contributions (Fund_Predictions column C or E). Call: beats by {T:g}%+ if >= {T:g}.")
    if any_feas:
        gname = next(nm for nm, f in feas_all.items() if f)
        line("Example", f"Filter Fund_Placement on Group = {gname} and any fund: add up column K; it equals that fund's prediction.")
    else:
        line("This workbook", f"No parameter is feasible, so these sheets are empty and every fund's {ty} prediction is blank. "
                              "Nothing is predicted rather than predicting from parameters that failed the test.", bold=True)
    gap()
    line("Checked", "Every formula in this workbook was recalculated and compared with the Python model: all backtest calls, "
                    "the shortlist and the year totals match exactly.")


def write_workbook(R, data, univariate, nifty_avg):
    ly, ty = R["latest_year"], R["target_year"]
    a, b = R["test"]
    cut, T = SP.HIT_RATIO, SP.TARGET
    book = Workbook()
    book.calculation.fullCalcOnLoad = True
    sheet = book.active
    sheet.title = "Method"
    lines = [
        ("Testing & prediction: will a fund beat the Nifty 50 by 3%+ next year?", None),
        ("Question", f"Which parameters from the Statistical analysis really tell, in advance, whether a fund will beat the "
                     f"Nifty 50 by {T:g}%+ the next calendar year; and with those, a prediction for calendar {ty}."),
        ("Data", "Parameter data updated-Dec 25(1).xlsx: parameters per calendar year, fund returns per calendar year, "
                 "the Nifty 50 (price index) row. Parameter year T is paired with the return in T+1. Excess = fund return - "
                 "Nifty 50 return. Funds and categories: Book3.xlsx."),
        ("1 Candidates", "The parameters the Statistical analysis rates 'Robust' for the group: Fama-MacBeth slope of "
                         "next-year excess on the parameter (standardised within each year), p <= 0.05, q <= 0.10 "
                         "(false discovery rate across the 101 parameters), same sign in both halves."),
        ("2 Unique", "Versions of one measure count once (Alpha / Alpha (Annualized), arith / geo, non-excess return): the "
                     f"most significant is kept. Then, most significant first, a parameter moving with one already kept "
                     f"(|rank correlation| > {SP.UNIQUE_RHO:g}) is dropped."),
        ("3 Backtest", f"Parameter years {a}-{b} (returns {a + 1}-{b + 1}). In each year Y the group's funds are split into "
                       f"fifths by the parameter. A fund's predicted excess = its fifth's average next-year excess over the "
                       f"years before Y only ({SP.MIN_PAST_YEARS}+ needed; Quintile_History). Call: 'beats the Nifty 50 by "
                       f"{T:g}%+' if that is >= {T:g}%, otherwise not. Right if the fund actually did / did not. "
                       "Hit ratio = right calls / all funds."),
        ("Naive call", f"The same call for every fund from the group's own average excess in the years before Y "
                       f"(Group_Yearly_Excess). A parameter must beat this, otherwise it only repeats the group's base rate "
                       f"(e.g. 'no Large Cap fund beats by {T:g}%')."),
        ("4 Feasible", f"Hit ratio above {cut:.0%} on {SP.MIN_CALLS}+ calls AND more right calls than the naive call."),
        ("5 Prediction", f"Each feasible parameter places the fund in a fifth of its group's {ly} funds; that fifth's average "
                         f"next-year excess over all years is the parameter's prediction; weighted by |t|. Call for {ty}: "
                         f"beats the Nifty 50 by {T:g}%+ if the prediction is >= {T:g}%."),
        ("Live check", f"{ly} -> {R['live_label']} (nine months only): the same call against the actual excess so far."),
        ("Caution", "Candidates come from the Statistical analysis on all years, so they were chosen knowing the backtest years. "
                    "The backtest's predictions use no future data."),
        ("Sheets", None),
        ("Group_Summary", "Every group: candidates, unique, best backtest result vs naive, feasible, predictions."),
        ("Fund_Data", "Every fund-year: return, Nifty 50, excess (formula) and the candidate parameters' values."),
        ("Statistical_Analysis", "The Statistical analysis results for every group x parameter (where the candidates come from)."),
        ("Shortlist", "The Robust candidates, unique or folded into another; backtest, naive, precision and Feasible? are formulas."),
        ("Group_Yearly_Excess", "Each group's average excess and share beating by 3%+ per year (the naive call's input)."),
        ("Quintile_History", "Each unique candidate: every year's average next-year excess of each fifth (the prediction's input)."),
        ("Backtest", "By parameter and year: the fifth averages known before the year, calls, right, naive right (formulas)."),
        ("Backtest_Calls", "Every backtest call: fund, fifth, predicted excess (formula over earlier years), call, actual, right."),
        ("Prediction_Weights", "Feasible parameters: weight and the fifth averages over all years (formulas)."),
        ("Fund_Placement", f"Every fund x feasible parameter: {ly} fifth, that fifth's average, weight, contribution (formulas)."),
        ("Fund_Predictions", f"Every fund: {ty} predicted excess (formula), the 3%+ call, and the actual {R['live_label']} figures."),
        ("Live_Check", f"Every unique candidate's call for {ly} -> {R['live_label']}, right / naive right (formulas)."),
    ]
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 120
    for i, (k, v) in enumerate(lines, 1):
        sheet.cell(row=i, column=1, value=k).font = TITLE_FONT if v is None else Font(bold=True)
        if v:
            sheet.cell(row=i, column=2, value=v).alignment = Alignment(wrap_text=True, vertical="top")
            sheet.row_dimensions[i].height = 30

    groups = R["groups"]
    feas_of = {g["name"]: SP.predict(g, cut) for g in groups}
    kept_of = {g["name"]: [r for r in g["params"] if r["status"][0] == 0] for g in groups}

    # ---- Group_Summary
    summary = []
    for g in groups:
        feas, weights, preds = feas_of[g["name"]]
        kept = kept_of[g["name"]]
        best = max((r for r in kept if r["backtest"]["calls"]), key=lambda r: r["backtest"]["hits"] / r["backtest"]["calls"], default=None)
        vals = np.array([v for v, _ in preds.values()], dtype=float)
        summary.append({"Group": g["name"], "Funds": g["funds"], "Fund-years": g["obs"],
                        "Significant (p <= 0.05)": g["significant"], "Robust": g["robust"], "Candidates": g["candidates"],
                        "Candidates are": g["tier"], "Unique": len(kept),
                        "Best backtest parameter": best and best["parameter"],
                        "Its hit ratio": best and best["backtest"]["hits"] / best["backtest"]["calls"],
                        "Naive hit ratio": best and best["backtest"]["naive"] / best["backtest"]["calls"],
                        f"Feasible (> {cut:.0%} and > naive)": len(feas),
                        "Feasible parameters": ", ".join(r["parameter"] for r in feas) or "none",
                        "Funds predicted": len(preds) or None,
                        f"Predicted to beat Nifty by {T:g}%+": int((vals >= T).sum()) if len(vals) else None})
    write_table(book.create_sheet("Group_Summary"), pd.DataFrame(summary),
                title=f"Every group: Statistical analysis candidates -> unique -> backtest on 'beats the Nifty 50 by {T:g}%+' "
                      f"-> feasible (> {cut:.0%} and better than naive) -> {ty} predictions",
                widths=[20, 7, 10, 11, 8, 10, 24, 8, 36, 9, 9, 12, 40, 10, 12],
                formats={"Its hit ratio": "0.0%", "Naive hit ratio": "0.0%"})

    # ---- Fund_Data
    cand_params = {r["parameter"] for g in groups for r in g["params"]}
    cand_params = [p for p in data.parameters if p in cand_params]
    pan = data.panel.sort_values(["category", "scheme_name", "param_year"])
    fd = pd.DataFrame({"Fund": pan["scheme_name"], "Category": pan["category"], "Parameter year": pan["param_year"],
                       "Return year": pan["return_year"], "Fund return next year %": pan["fund_return"],
                       "Nifty 50 next year %": pan["nifty_return"].where(pan["param_year"] != ly, data.nifty_partial),
                       "Excess %": None})
    for p in cand_params:
        fd[p] = pan[p].values
    sh = book.create_sheet("Fund_Data")
    write_table(sh, fd, title=f"Every fund-year: parameters in year T, return in T+1 vs the Nifty 50 (excess = formula). "
                              f"{ly} -> {R['live_label']} is the live period. Columns after Excess: every candidate parameter.",
                widths=[40, 16, 9, 9, 11, 11, 10] + [11] * len(cand_params),
                formats={"Fund return next year %": "0.00", "Nifty 50 next year %": "0.00", **{p: "0.000" for p in cand_params}})
    put_formulas(sh, 4, len(fd), 7, '=IF(OR(E{r}="",F{r}=""),"",E{r}-F{r})')
    for r in range(4, 4 + len(fd)):
        sh.cell(row=r, column=7).number_format = "0.00"

    # ---- Statistical_Analysis
    u = univariate[~univariate["group"].str.startswith("All Funds,")].copy()
    stat = pd.DataFrame({"Group": u["group"], "Parameter": u["parameter"], "Fund-years": u["fund_years"],
                         "Years": u["years"], "Slope (pts per 1 SD)": u["slope"], "SE": u["se"], "t": u["t"], "p": u["p"],
                         "q": u["q"], "95% CI low": u["ci_low"], "95% CI high": u["ci_high"], "Rank IC": u["ic"],
                         "Years slope > 0": u["share_positive"], "First half slope": u["first_half"],
                         "Second half slope": u["second_half"], "Stable": u["stable"].map({True: "Yes", False: "No"}),
                         "Verdict": u["verdict"]})
    write_table(book.create_sheet("Statistical_Analysis"), stat,
                title="Statistical analysis (Fama-MacBeth, Newey-West SE, BH q-values within each group): every group x parameter",
                widths=[18, 40, 9, 7, 11, 8, 7, 9, 9, 10, 10, 9, 10, 10, 10, 7, 22],
                formats={c: "0.000" for c in ["Slope (pts per 1 SD)", "SE", "95% CI low", "95% CI high", "Rank IC",
                                               "First half slope", "Second half slope"]} | {"t": "0.00", "p": "0.0000",
                                                                                            "q": "0.0000", "Years slope > 0": "0%"})

    # ---- Group_Yearly_Excess
    gy = []
    for g in groups:
        for y, fr in g["rows"].groupby("param_year"):
            gy.append({"Group": g["name"], "Parameter year": int(y), "Return year": int(y) + 1, "Funds": len(fr),
                       "Avg excess %": fr["excess"].mean(), f"Share beating by {T:g}%+": (fr["excess"] >= T).mean()})
    gyd = pd.DataFrame(gy)
    write_table(book.create_sheet("Group_Yearly_Excess"), gyd,
                title="Each group's average excess over the Nifty 50 per year (the naive call: the average of the years before)",
                widths=[18, 9, 9, 7, 11, 13], formats={"Avg excess %": "0.00", f"Share beating by {T:g}%+": "0%"})
    n_gy = len(gyd) + 3
    gr = lambda c: f"Group_Yearly_Excess!${c}$4:${c}${n_gy}"

    # ---- Quintile_History (every unique candidate)
    qh = []
    for g in groups:
        for r in kept_of[g["name"]]:
            for y, fr in SP.fifth_history(g["rows"], r["parameter"]).items():
                avg = fr.groupby("fifth")["excess"].mean()
                qh.append({"Group": g["name"], "Parameter": r["parameter"], "Parameter year": y, "Return year": y + 1,
                           "Funds": len(fr), **{f"Q{q} avg excess %": avg.get(q) for q in range(1, 6)}})
    qhd = pd.DataFrame(qh)
    write_table(book.create_sheet("Quintile_History"), qhd,
                title="Every unique candidate: each year the group's funds split into fifths (Q1 = lowest values); each fifth's "
                      "average excess over the Nifty 50 the next year",
                widths=[18, 40, 9, 9, 7] + [12] * 5, formats={f"Q{q} avg excess %": "0.00" for q in range(1, 6)})
    n_qh = len(qhd) + 3
    qr = lambda c: f"Quintile_History!${c}$4:${c}${n_qh}"

    # ---- Backtest_Calls
    calls = []
    for g in groups:
        for r in kept_of[g["name"]]:
            for c in r["backtest"]["detail"]:
                calls.append({"Group": g["name"], "Parameter": r["parameter"], "Parameter year": c["year"],
                              "Return year": c["year"] + 1, "Fund": c["fund"], "Value": c["value"], "Fifth": c["fifth"],
                              "Predicted excess %": None, "Call": None, "Actual excess %": c["excess"],
                              f"Actually beat {T:g}%+": None, "Right": None, "Group past avg %": None,
                              "Naive call": None, "Naive right": None, "Miss (|actual - predicted|)": None,
                              "Within tolerance": None, "Actual >= predicted": None, "Naive miss": None,
                              "Naive within tolerance": None, "Naive: actual >= predicted": None,
                              "Deviation (actual - predicted)": None, "Naive deviation": None, "Basket (predicted excess)": None})
    cd = pd.DataFrame(calls)
    shc = book.create_sheet("Backtest_Calls")
    write_table(shc, cd, title=f"Every backtest call, returns {a + 1}-{b + 1}: predicted excess = the fund's fifth's average over the "
                               f"years before (Quintile_History); call 'Beat {T:g}%+' if >= {T:g}; naive = the group's past average",
                widths=[18, 36, 9, 9, 40, 10, 6, 11, 10, 11, 10, 7, 11, 10, 8, 10, 9, 9, 9, 9, 10],
                formats={"Value": "0.000", "Actual excess %": "0.00"})
    qcols = ",".join(qr(col(5 + q)) for q in range(1, 6))
    put_formulas(shc, 4, len(cd), 8, f'=AVERAGEIFS(CHOOSE(G{{r}},{qcols}),{qr("A")},A{{r}},{qr("B")},B{{r}},{qr("C")},"<"&C{{r}})')
    put_formulas(shc, 4, len(cd), 9, f'=IF(H{{r}}>={T:g},"Beat {T:g}%+","No")')
    put_formulas(shc, 4, len(cd), 11, f'=IF(J{{r}}>={T:g},"Yes","No")')
    put_formulas(shc, 4, len(cd), 12, f'=IF((H{{r}}>={T:g})=(J{{r}}>={T:g}),1,0)')
    put_formulas(shc, 4, len(cd), 13, f'=AVERAGEIFS({gr("E")},{gr("A")},A{{r}},{gr("B")},"<"&C{{r}})')
    put_formulas(shc, 4, len(cd), 14, f'=IF(M{{r}}>={T:g},"Beat {T:g}%+","No")')
    put_formulas(shc, 4, len(cd), 15, f'=IF((M{{r}}>={T:g})=(J{{r}}>={T:g}),1,0)')
    TOL = "Shortlist!$Z$2"                      # the tolerance (points), one cell
    put_formulas(shc, 4, len(cd), 16, "=ABS(J{r}-H{r})")
    put_formulas(shc, 4, len(cd), 17, f"=IF(P{{r}}<={TOL},1,0)")
    put_formulas(shc, 4, len(cd), 18, "=IF(J{r}>=H{r},1,0)")
    put_formulas(shc, 4, len(cd), 19, "=ABS(J{r}-M{r})")
    put_formulas(shc, 4, len(cd), 20, f"=IF(S{{r}}<={TOL},1,0)")
    put_formulas(shc, 4, len(cd), 21, "=IF(J{r}>=M{r},1,0)")
    for r in range(4, 4 + len(cd)):
        shc.cell(row=r, column=22, value=f"=J{r}-H{r}").number_format = "0.00"
        shc.cell(row=r, column=23, value=f"=J{r}-M{r}").number_format = "0.00"
        shc.cell(row=r, column=24, value=BASKET_F.format(c=f"H{r}"))
    for r in range(4, 4 + len(cd)):
        shc.cell(row=r, column=16).number_format = "0.00"
        shc.cell(row=r, column=19).number_format = "0.00"
    for r in range(4, 4 + len(cd)):
        shc.cell(row=r, column=8).number_format = "0.00"
        shc.cell(row=r, column=13).number_format = "0.00"
    n_c = len(cd) + 3
    cr = lambda c: f"Backtest_Calls!${c}$4:${c}${n_c}"

    # ---- Backtest by year
    bt = []
    for g in groups:
        for r in kept_of[g["name"]]:
            for t in r["backtest"]["years"]:
                bt.append({"Group": g["name"], "Parameter": r["parameter"], "Parameter year": t["year"],
                           "Return year": t["year"] + 1, "Years before": t["past_years"],
                           **{f"Q{q} avg before %": t["fifth_avg"][q - 1] for q in range(1, 6)},
                           "Group avg before %": t["naive_avg"], "Funds": None, f"Called beat {T:g}%+": None,
                           f"Actually beat {T:g}%+": None, "Right": None, "Naive right": None, "Hit ratio": None,
                           "Naive hit ratio": None})
    btd = pd.DataFrame(bt)
    shb = book.create_sheet("Backtest")
    write_table(shb, btd, title="Backtest by parameter and year: the fifth averages and group average known before the year; "
                                "calls and results counted from Backtest_Calls (formulas)",
                widths=[18, 36, 9, 9, 8] + [10] * 5 + [11, 7, 10, 10, 7, 8, 9, 9],
                formats={**{f"Q{q} avg before %": "0.00" for q in range(1, 6)}, "Group avg before %": "0.00"})
    key = lambda r: f'{cr("A")},A{r},{cr("B")},B{r},{cr("C")},C{r}'
    for i in range(len(btd)):
        r = 4 + i
        shb.cell(row=r, column=12, value=f"=COUNTIFS({key(r)})")
        shb.cell(row=r, column=13, value=f'=COUNTIFS({key(r)},{cr("I")},"Beat {T:g}%+")')
        shb.cell(row=r, column=14, value=f'=COUNTIFS({key(r)},{cr("K")},"Yes")')
        shb.cell(row=r, column=15, value=f'=SUMIFS({cr("L")},{key(r)})')
        shb.cell(row=r, column=16, value=f'=SUMIFS({cr("O")},{key(r)})')
        shb.cell(row=r, column=17, value=f"=IF(L{r}>0,O{r}/L{r},\"\")").number_format = "0.0%"
        shb.cell(row=r, column=18, value=f"=IF(L{r}>0,P{r}/L{r},\"\")").number_format = "0.0%"

    # ---- Live_Check (every unique candidate)
    lc = []
    for g in groups:
        for r in kept_of[g["name"]]:
            for c in (r.get("live") or {}).get("detail", []):
                lc.append({"Group": g["name"], "Parameter": r["parameter"], "Fund": c["fund"], f"{ly} value": c["value"],
                           "Fifth": c["fifth"], "Predicted excess %": c["pred"], "Call": None,
                           f"Actual excess {R['live_label']} %": c["excess"], f"Beat {T:g}%+ so far": None, "Right": None,
                           "Group avg %": g["group_avg"], "Naive right": None})
    lcd = pd.DataFrame(lc)
    shl = book.create_sheet("Live_Check")
    write_table(shl, lcd, title=f"Live check, {ly} -> {R['live_label']} (nine months): each unique candidate's call against the "
                                "actual excess so far; naive = the group's average over all years",
                widths=[18, 36, 40, 10, 6, 11, 10, 13, 10, 7, 10, 8],
                formats={f"{ly} value": "0.000", "Predicted excess %": "0.00", f"Actual excess {R['live_label']} %": "0.00",
                         "Group avg %": "0.00"})
    put_formulas(shl, 4, len(lcd), 7, f'=IF(F{{r}}>={T:g},"Beat {T:g}%+","No")')
    put_formulas(shl, 4, len(lcd), 9, f'=IF(H{{r}}>={T:g},"Yes","No")')
    put_formulas(shl, 4, len(lcd), 10, f'=IF((F{{r}}>={T:g})=(H{{r}}>={T:g}),1,0)')
    put_formulas(shl, 4, len(lcd), 12, f'=IF((K{{r}}>={T:g})=(H{{r}}>={T:g}),1,0)')
    n_l = len(lcd) + 3
    lr = lambda c: f"Live_Check!${c}$4:${c}${n_l}"

    # ---- Shortlist
    short_rows = []
    for g in groups:
        for r in g["params"]:
            st, other = r["status"]
            short_rows.append({"Group": g["name"], "Parameter": r["parameter"], "Slope (pts per 1 SD)": r["slope"],
                               "t": r["t"], "p": r["p"], "q": r["q"], "Status": SP.STATUS[st] + (f" {other}" if other else ""),
                               "Backtest calls": None, "Right": None, "Hit ratio": None, "Naive right": None,
                               "Naive hit ratio": None, f"Called beat {T:g}%+": None, "Of those, beat": None,
                               "Precision": None, "Feasible": None, "Live calls": None, "Live right": None,
                               "Live naive right": None,
                               **{f"Q{k + 1} avg excess % (all years)": (r["quintiles"] or [None] * 5)[k] for k in range(5)},
                               "Within tolerance: right": None, "Within tolerance: hit ratio": None,
                               "Within tolerance: naive right": None, "Within tolerance: naive hit ratio": None,
                               "Actual >= predicted: right": None, "Actual >= predicted: hit ratio": None,
                               "Actual >= predicted: naive right": None, "Actual >= predicted: naive hit ratio": None,
                               "Average miss (pts)": None, "Naive average miss (pts)": None, "Candidates are": g["tier"],
                               "Average deviation (actual - predicted)": None, "Naive average deviation": None})
    sdf = pd.DataFrame(short_rows)
    shs = book.create_sheet("Shortlist")
    write_table(shs, sdf, title=f"The shortlist: every candidate (the Robust parameters; where a category has none, its significant ones - see 'Candidates are'), unique or not; backtest on 'beats the Nifty 50 by {T:g}%+' "
                                f"(formulas over Backtest_Calls); Feasible = > {cut:.0%}, {SP.MIN_CALLS}+ calls and more right than naive",
                widths=[18, 40, 11, 7, 9, 9, 40, 9, 7, 9, 9, 9, 10, 9, 9, 9, 8, 8, 9] + [11] * 5 + [10] * 10 + [30],
                formats={"Slope (pts per 1 SD)": "0.000", "t": "0.00", "p": "0.0000", "q": "0.0000",
                         **{f"Q{k + 1} avg excess % (all years)": "0.00" for k in range(5)}})
    for i, row in enumerate(short_rows):
        r = 4 + i
        if row["Status"] != "Unique":
            continue
        k2 = f'{cr("A")},A{r},{cr("B")},B{r}'
        shs.cell(row=r, column=8, value=f"=COUNTIFS({k2})")
        shs.cell(row=r, column=9, value=f'=SUMIFS({cr("L")},{k2})')
        shs.cell(row=r, column=10, value=f'=IF(H{r}>0,I{r}/H{r},"")').number_format = "0.0%"
        shs.cell(row=r, column=11, value=f'=SUMIFS({cr("O")},{k2})')
        shs.cell(row=r, column=12, value=f'=IF(H{r}>0,K{r}/H{r},"")').number_format = "0.0%"
        shs.cell(row=r, column=13, value=f'=COUNTIFS({k2},{cr("I")},"Beat {T:g}%+")')
        shs.cell(row=r, column=14, value=f'=COUNTIFS({k2},{cr("I")},"Beat {T:g}%+",{cr("K")},"Yes")')
        shs.cell(row=r, column=15, value=f'=IF(M{r}>0,N{r}/M{r},"")').number_format = "0.0%"
        shs.cell(row=r, column=16, value=f'=IF(AND(H{r}>={SP.MIN_CALLS},J{r}>{cut},I{r}>K{r}),"Yes","no")')
        l2 = f'{lr("A")},A{r},{lr("B")},B{r}'
        shs.cell(row=r, column=17, value=f"=COUNTIFS({l2})")
        shs.cell(row=r, column=18, value=f'=SUMIFS({lr("J")},{l2})')
        shs.cell(row=r, column=19, value=f'=SUMIFS({lr("L")},{l2})')
        for c, src, pct in ((25, "Q", None), (27, "T", None), (29, "R", None), (31, "U", None)):
            shs.cell(row=r, column=c, value=f'=SUMIFS({cr(src)},{k2})')
            shs.cell(row=r, column=c + 1, value=f'=IF($H{r}>0,{col(c)}{r}/$H{r},"")').number_format = "0.0%"
        shs.cell(row=r, column=33, value=f'=IF($H{r}>0,SUMIFS({cr("P")},{k2})/$H{r},"")').number_format = "0.00"
        shs.cell(row=r, column=34, value=f'=IF($H{r}>0,SUMIFS({cr("S")},{k2})/$H{r},"")').number_format = "0.00"
        shs.cell(row=r, column=36, value=f'=IF($H{r}>0,SUMIFS({cr("V")},{k2})/$H{r},"")').number_format = "0.00"
        shs.cell(row=r, column=37, value=f'=IF($H{r}>0,SUMIFS({cr("W")},{k2})/$H{r},"")').number_format = "0.00"
    shs.cell(row=2, column=25, value="Tolerance (points) for 'within tolerance' - change it and every count updates:").font = Font(bold=True)
    shs.cell(row=2, column=26, value=SP.TOLERANCE).font = Font(bold=True, color="C00000")

    # ---- Prediction_Weights / Fund_Placement / Fund_Predictions
    feasible_any = any(feas_of[g["name"]][0] for g in groups)
    msg = (f"No parameter is feasible at {cut:.0%}: none beats the cut-off and the naive call on 'beats the Nifty 50 by "
           f"{T:g}%+'. So there is no {ty} prediction. See Shortlist / Group_Summary for how close each came.")
    shw = book.create_sheet("Prediction_Weights")
    pw = []
    for g in groups:
        feas, weights, _ = feas_of[g["name"]]
        for r in feas:
            pw.append({"Group": g["name"], "Parameter": r["parameter"], "Backtest hit": r["backtest"]["hits"] / r["backtest"]["calls"],
                       "Naive": r["backtest"]["naive"] / r["backtest"]["calls"], "t": r["t"], "|t|": abs(r["t"]), "Weight": None,
                       **{f"Q{q} avg excess %": None for q in range(1, 6)},
                       **{f"{ly} Q{q} values": f"{lo:.3f} to {hi:.3f} ({n} funds)" for q, (lo, hi, n) in enumerate(r["latest_bounds"], 1)}})
    if pw:
        pwd = pd.DataFrame(pw)
        write_table(shw, pwd, title="Feasible parameters: weight = |t| / sum of |t| in the group; each fifth's average next-year "
                                    "excess = average over all years in Quintile_History (formulas)",
                    widths=[18, 40, 9, 8, 7, 7, 8] + [11] * 5 + [26] * 5,
                    formats={"Backtest hit": "0.0%", "Naive": "0.0%", "t": "0.00", "|t|": "0.00"})
        n_pw = len(pwd) + 3
        put_formulas(shw, 4, len(pwd), 7, f'=F{{r}}/SUMIFS($F$4:$F${n_pw},$A$4:$A${n_pw},A{{r}})')
        for q in range(1, 6):
            put_formulas(shw, 4, len(pwd), 7 + q, f'=AVERAGEIFS({qr(col(5 + q))},{qr("A")},A{{r}},{qr("B")},B{{r}})')
        for r in range(4, 4 + len(pwd)):
            shw.cell(row=r, column=7).number_format = "0.0%"
            for q in range(1, 6):
                shw.cell(row=r, column=7 + q).number_format = "0.00"
    else:
        shw.cell(row=1, column=1, value="Feasible parameters and their weights").font = TITLE_FONT
        note(shw, 3, msg)
        n_pw = 3

    shp = book.create_sheet("Fund_Placement")
    fp = []
    for g in groups:
        for r in feas_of[g["name"]][0]:
            vals = sorted(v for v, _ in r["latest"].values())
            names = dict(zip(g["members"]["scheme_id"], g["members"]["scheme_name"]))
            for sid, (v, q) in r["latest"].items():
                fp.append({"Group": g["name"], "Fund": names[sid], "Parameter": r["parameter"], f"{ly} value": v,
                           "Rank (lowest = 1)": sum(1 for x in vals if x < v) + 1, "Of funds": len(vals), "Fifth": q,
                           "Fifth avg excess %": None, "|t|": abs(r["t"]), "Weight (re-scaled)": None, "Contribution %": None})
    if fp:
        fpd = pd.DataFrame(fp).sort_values(["Group", "Fund", "Parameter"])
        write_table(shp, fpd, title=f"Every fund x feasible parameter: its {ly} fifth, that fifth's average next-year excess, "
                                    "weight = |t| / the fund's total |t|, contribution = weight x average (formulas)",
                    widths=[18, 40, 40, 10, 9, 8, 6, 11, 7, 10, 11], formats={f"{ly} value": "0.000"})
        n_fp = len(fpd) + 3
        pwr = lambda c: f"Prediction_Weights!${c}$4:${c}${n_pw}"
        put_formulas(shp, 4, len(fpd), 8, f'=INDEX(CHOOSE(G{{r}},{pwr("H")},{pwr("I")},{pwr("J")},{pwr("K")},{pwr("L")}),'
                                          f'MATCH(1,INDEX(({pwr("A")}=A{{r}})*({pwr("B")}=C{{r}}),0),0))')
        put_formulas(shp, 4, len(fpd), 10, f'=I{{r}}/SUMIFS($I$4:$I${n_fp},$A$4:$A${n_fp},A{{r}},$B$4:$B${n_fp},B{{r}})')
        put_formulas(shp, 4, len(fpd), 11, "=J{r}*H{r}")
        for r in range(4, 4 + len(fpd)):
            for c, f_ in ((8, "0.00"), (10, "0.0%"), (11, "0.00")):
                shp.cell(row=r, column=c).number_format = f_
    else:
        shp.cell(row=1, column=1, value="Fund placement").font = TITLE_FONT
        note(shp, 3, msg)
        n_fp = 3

    members = data.panel[data.panel["param_year"] == ly].sort_values(["category", "scheme_name"])
    fpr = pd.DataFrame({"Fund": members["scheme_name"], "Category": members["category"],
                        f"Category model: predicted excess {ty} %": None, f"Category model: beats Nifty by {T:g}%+?": None,
                        f"All-funds model: predicted excess {ty} %": None, f"All-funds model: beats Nifty by {T:g}%+?": None,
                        f"Actual {R['live_label']} fund return %": members["fund_return"],
                        f"Nifty 50 {R['live_label']} %": data.nifty_partial, f"Actual excess {R['live_label']} %": None})
    shf = book.create_sheet("Fund_Predictions")
    write_table(shf, fpr, title=f"Every fund's {ty} prediction = sum of its contributions in Fund_Placement (formula) and the "
                                f"{T:g}%+ call; and what actually happened so far" + ("" if feasible_any else " - " + msg),
                widths=[44, 18, 14, 12, 14, 12, 13, 12, 13], formats={c: "0.00" for c in fpr.columns if c.endswith("%")})
    fpc = lambda c: f"Fund_Placement!${c}$4:${c}${max(n_fp, 4)}"
    put_formulas(shf, 4, len(fpr), 3, f'=IF(COUNTIFS({fpc("A")},B{{r}},{fpc("B")},A{{r}})=0,"",SUMIFS({fpc("K")},{fpc("A")},B{{r}},{fpc("B")},A{{r}}))')
    put_formulas(shf, 4, len(fpr), 4, f'=IF(C{{r}}="","",IF(C{{r}}>={T:g},"Yes","No"))')
    put_formulas(shf, 4, len(fpr), 5, f'=IF(COUNTIFS({fpc("A")},"All Funds",{fpc("B")},A{{r}})=0,"",SUMIFS({fpc("K")},{fpc("A")},"All Funds",{fpc("B")},A{{r}}))')
    put_formulas(shf, 4, len(fpr), 6, f'=IF(E{{r}}="","",IF(E{{r}}>={T:g},"Yes","No"))')
    put_formulas(shf, 4, len(fpr), 9, '=IF(G{r}="","",G{r}-H{r})')
    for r in range(4, 4 + len(fpr)):
        for c in (3, 5, 9):
            shf.cell(row=r, column=c).number_format = "0.00"

    # ---- Baskets: predictions grouped by predicted excess (formulas over Backtest_Calls)
    brows = []
    for g in groups:
        kept = [r for r in kept_of[g["name"]] if r["backtest"]["calls"]]
        if not kept:
            continue
        for pname in ["(all unique candidates)"] + [r["parameter"] for r in kept]:
            for lo, hi in zip(SP.BASKETS[:-1], SP.BASKETS[1:]):
                brows.append({"Group": g["name"], "Parameter": pname, "Basket (predicted excess)": SP.basket_label(lo, hi),
                              "Predictions": None, "Average predicted %": None, "Average actual %": None,
                              "Average deviation (actual - predicted)": None, "Average miss |actual - predicted|": None,
                              f"Actually beat {T:g}%+": None, "Share that beat": None})
    bdf = pd.DataFrame(brows)
    sbk = book.create_sheet("Baskets")
    write_table(sbk, bdf, title=f"Backtest predictions grouped by predicted excess (returns {a + 1}-{b + 1}): what each basket actually "
                                "delivered. Formulas over Backtest_Calls; '(all unique candidates)' pools every unique candidate of the group.",
                widths=[18, 40, 16, 10, 10, 10, 12, 12, 10, 9])
    for i, row in enumerate(brows):
        r = 4 + i
        k = f'{cr("A")},$A{r},{cr("X")},$C{r}' + ("" if row["Parameter"].startswith("(") else f',{cr("B")},$B{r}')
        sbk.cell(row=r, column=4, value=f"=COUNTIFS({k})")
        for c, src in ((5, "H"), (6, "J"), (7, "V"), (8, "P")):
            sbk.cell(row=r, column=c, value=f'=IF($D{r}>0,AVERAGEIFS({cr(src)},{k}),"")').number_format = "0.00"
        sbk.cell(row=r, column=9, value=f'=COUNTIFS({k},{cr("K")},"Yes")')
        sbk.cell(row=r, column=10, value=f'=IF($D{r}>0,I{r}/D{r},"")').number_format = "0%"

    write_guide(book, R, data, cut)
    for ws in book.worksheets:
        if ws.title not in ("Read_Me", "Method") and ws.max_row > 3 and ws.cell(row=3, column=1).value:
            ws.auto_filter.ref = f"A3:{col(ws.max_column)}{ws.max_row}"
    order = ["Read_Me", "Method", "Group_Summary", "Fund_Data", "Statistical_Analysis", "Shortlist", "Group_Yearly_Excess",
             "Quintile_History", "Backtest", "Backtest_Calls", "Baskets", "Prediction_Weights", "Fund_Placement", "Fund_Predictions",
             "Live_Check"]
    book._sheets = [book[n] for n in order]
    book.save(WORKBOOK)


def x_baskets(x):
    return x.get("baskets") or SP.baskets([], [])


def write_dashboard(R, data, nifty_avg):
    params = data.parameters
    pi = {p: i for i, p in enumerate(params)}
    members = data.panel[data.panel["param_year"] == R["latest_year"]].sort_values(["category", "scheme_name"])
    fi = {sid: i for i, sid in enumerate(members["scheme_id"])}
    live = members["fund_return"] - data.nifty_partial if data.nifty_partial is not None else members["fund_return"] * np.nan

    def r(v, n=3):
        v = clean(v)
        return None if v is None else round(float(v), n)

    groups = []
    for g in R["groups"]:
        rows = []
        for x in g["params"]:
            st, other = x["status"]
            b_ = x.get("backtest")
            lv = x.get("live")
            rows.append([pi[x["parameter"]], st, pi[other] if other else None, r(x["slope"]), r(x["se"]), r(x["t"], 2),
                         r(x["p"], 6), r(x["q"], 6), r(x["ic"]), r(x["share_positive"]), r(x["first_half"]), r(x["second_half"]),
                         x["years"], [r(v, 4) for v in x["quintiles"]] if x["quintiles"] else None, x["quintile_years"],
                         None if not b_ else {k: (r(b_[k], 2) if isinstance(b_[k], float) else b_[k])
                                              for k in ("calls", "hits", "naive", "called", "called_right", "beat") + tuple(SP.OTHER_KEYS)} | {
                             "baskets": [[x["n"], r(x["sum_pred"], 2), r(x["sum_actual"], 2), x["beat"], r(x["abs_dev"], 2)]
                                         for x in x_baskets(x)],
                             "years": [[t["year"], t["past_years"], [r(v, 2) for v in t["fifth_avg"]], r(t["naive_avg"], 2), t["funds"],
                                        t["called"], t["beat"], t["hits"], t["naive_hits"], t["called_right"]] for t in b_["years"]]},
                         None if not lv else [lv["calls"], lv["hits"], lv["naive"], lv["called"], lv["called_right"], lv["beat"],
                                              r(lv["group_avg"], 2), {k: (r(lv[k], 2) if isinstance(lv[k], float) else lv[k])
                                                                      for k in SP.OTHER_KEYS}],
                         None if not x.get("latest_bounds") else [[r(lo, 4), r(hi, 4), n] for lo, hi, n in x["latest_bounds"]],
                         None if not x.get("latest") else [[fi[sid], r(v, 4), q] for sid, (v, q) in x["latest"].items() if sid in fi]])
        groups.append({"name": g["name"], "groupAvg": r(g["group_avg"], 2), "robust": g["robust"], "candidates": g["candidates"], "tier": g["tier"], "significant": g["significant"], "funds": g["funds"],
                       "obs": g["obs"], "members": len(g["members"]), "params": rows})
    payload = {
        "parameters": params, "latestYear": R["latest_year"], "targetYear": R["target_year"], "test": list(R["test"]),
        "liveLabel": R["live_label"], "niftyAverage": r(nifty_avg, 2), "niftyPartial": r(data.nifty_partial, 2),
        "settings": {"cuts": list(SP.CUTS), "cut": SP.HIT_RATIO, "minCalls": SP.MIN_CALLS, "target": SP.TARGET,
                     "tolerances": list(SP.TOLERANCES), "tolerance": SP.TOLERANCE,
                     "baskets": [SP.basket_label(lo, hi) for lo, hi in zip(SP.BASKETS[:-1], SP.BASKETS[1:])],
                     "basketEdges": [lo if np.isfinite(lo) else None for lo in SP.BASKETS[:-1]], "uniqueRho": SP.UNIQUE_RHO,
                     "minPastYears": SP.MIN_PAST_YEARS, "status": SP.STATUS},
        "groups": groups,
        "funds": [{"id": m.scheme_id, "name": m.scheme_name, "category": m.category, "live": r(lv_, 2)}
                  for m, lv_ in zip(members.itertuples(), live)],
    }
    DATA.write_text("window.PREDICTION = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                                                       default=clean) + ";\n")


def main():
    data = S.load()
    univariate = pickle.loads(CACHE.read_bytes())["univariate"]
    R = SP.run(data, univariate)
    years = [y + 1 for y in data.full_years]
    nifty_avg = float(data.nifty.reindex(years).mean())
    write_workbook(R, data, univariate, nifty_avg)
    write_dashboard(R, data, nifty_avg)
    for g in R["groups"]:
        feas, _, preds = SP.predict(g)
        kept = [r for r in g["params"] if r["status"][0] == 0]
        best = max(kept, key=lambda r: r["backtest"]["hits"] / max(r["backtest"]["calls"], 1), default=None)
        print(f"{g['name'][:18]:18} {g['tier'][:11]:11} candidates {g['candidates']:3}  unique {len(kept):2}  feasible {len(feas)}"
              + (f"  best {best['parameter']} {best['backtest']['hits']}/{best['backtest']['calls']} (naive {best['backtest']['naive']})" if best else ""))


if __name__ == "__main__":
    main()
