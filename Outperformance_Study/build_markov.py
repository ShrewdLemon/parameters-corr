"""Markov chain tab: does this year's result predict next year's?

    python build_markov.py

Outputs (separate from every other tab):
    Markov_Chain.xlsx       the working (transition counts, probabilities and predictions are formulas)
    dashboard/markov.js     data for the dashboard's Markov chain tab
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

import pickle

import markov_chain as MC
import stats_prediction as SP
import study as S
from build import CACHE, TITLE_FONT, clean, header, write_table

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Markov_Chain.xlsx"
DATA = HERE / "dashboard" / "markov.js"
col = get_column_letter


def short(name):
    return name.replace(" Fund", "").replace("Small cap", "Small Cap")


def put(sheet, first, n, column, template, fmt=None):
    for r in range(first, first + n):
        c = sheet.cell(row=r, column=column, value=template.format(r=r))
        if fmt:
            c.number_format = fmt


STATE_F = '=IF({c}{{r}}="","",IF({c}{{r}}<-3,1,IF({c}{{r}}<0,2,IF({c}{{r}}<3,3,4))))'


def write_workbook(R, PR, data, nifty_avg):
    T, ty, ly = MC.TARGET, R["target_year"], R["latest_year"]
    a, b = R["test"]
    groups = [MC.ALL] + R["categories"]
    book = Workbook()
    book.calculation.fullCalcOnLoad = True

    # ---- States
    sh = book.active
    sh.title = "States"
    write_table(sh, pd.DataFrame({"State": [1, 2, 3, 4], "Name": MC.STATES,
                                  "Excess over the Nifty 50 that calendar year": ["below -3%", "-3% to 0%", "0% to +3%", "+3% or more"]}),
                title="The four states a fund can be in each calendar year", widths=[7, 18, 34])
    sh.cell(row=9, column=1, value="Blending").font = Font(bold=True)
    sh.cell(row=9, column=2, value=f"Category rows are blended with the all-funds row: P = (count + {MC.SMOOTH:g} x all-funds P) / "
                                   f"(row total + {MC.SMOOTH:g}); state averages the same way.")
    sh.cell(row=10, column=1, value="Smoothing (pseudo-transitions)").font = Font(bold=True)
    sh.cell(row=10, column=2, value=MC.SMOOTH)
    K = "States!$B$10"

    # ---- Transitions (full history: next year a full calendar year)
    t = R["transitions"]
    full = t[t["year"] + 1 <= b]
    tr = pd.DataFrame({"Fund": full["scheme_name"], "Category": full["category"], "Year": full["year"],
                       "Excess that year %": full["x"], "State": None, "Next year": full["year"] + 1,
                       "Excess next year %": full["x_next"], "Next state": None}).sort_values(["Category", "Fund", "Year"])
    st = book.create_sheet("Transitions")
    write_table(st, tr, title="Every fund's pair of consecutive calendar years: its state one year and the next (states = formulas)",
                widths=[40, 16, 7, 12, 6, 9, 12, 9], formats={"Excess that year %": "0.00", "Excess next year %": "0.00"})
    put(st, 4, len(tr), 5, STATE_F.format(c="D"))
    put(st, 4, len(tr), 8, STATE_F.format(c="G"))
    n_t = len(tr) + 3
    TR = lambda c: f"Transitions!${c}$4:${c}${n_t}"

    # ---- Matrix (long format, formulas)
    rows = [{"Group": g, "From state": i + 1, "To state": j + 1, "Count": None, "Row total": None, "All-funds P": None, "P": None}
            for g in groups for i in range(4) for j in range(4)]
    sm = book.create_sheet("Matrix")
    write_table(sm, pd.DataFrame(rows), title=f"Transition probabilities, all transitions up to {b}: P(next state | this state). "
                                              "Count = COUNTIFS over Transitions; categories blended with All funds",
                widths=[18, 9, 9, 8, 9, 10, 9])
    n_m = len(rows) + 3
    for i, row in enumerate(rows):
        r = 4 + i
        cat = "" if row["Group"] == MC.ALL else f',{TR("B")},A{r}'
        sm.cell(row=r, column=4, value=f"=COUNTIFS({TR('E')},B{r},{TR('H')},C{r}{cat})")
        sm.cell(row=r, column=5, value=f"=SUMIFS($D$4:$D${n_m},$A$4:$A${n_m},A{r},$B$4:$B${n_m},B{r})")
        sm.cell(row=r, column=6, value=f'=SUMIFS($D$4:$D${n_m},$A$4:$A${n_m},"{MC.ALL}",$B$4:$B${n_m},B{r},$C$4:$C${n_m},C{r})/'
                                       f'SUMIFS($D$4:$D${n_m},$A$4:$A${n_m},"{MC.ALL}",$B$4:$B${n_m},B{r})').number_format = "0.0%"
        sm.cell(row=r, column=7, value=(f"=F{r}" if row["Group"] == MC.ALL else f"=(D{r}+{K}*F{r})/(E{r}+{K})")).number_format = "0.0%"
    MR = lambda c: f"Matrix!${c}$4:${c}${n_m}"

    # ---- State averages
    srows = [{"Group": g, "State": j + 1, "Fund-years": None, "Sum of excess": None, "All-funds average %": None, "Average %": None}
             for g in groups for j in range(4)]
    sa = book.create_sheet("State_Averages")
    write_table(sa, pd.DataFrame(srows), title="Average excess over the Nifty 50 in each state (from 'next year' of every transition)",
                widths=[18, 6, 10, 12, 12, 10])
    n_s = len(srows) + 3
    for i, row in enumerate(srows):
        r = 4 + i
        cat = "" if row["Group"] == MC.ALL else f',{TR("B")},A{r}'
        sa.cell(row=r, column=3, value=f"=COUNTIFS({TR('H')},B{r}{cat})")
        sa.cell(row=r, column=4, value=f"=SUMIFS({TR('G')},{TR('H')},B{r}{cat})").number_format = "0.00"
        sa.cell(row=r, column=5, value=f'=SUMIFS($D$4:$D${n_s},$A$4:$A${n_s},"{MC.ALL}",$B$4:$B${n_s},B{r})/'
                                       f'SUMIFS($C$4:$C${n_s},$A$4:$A${n_s},"{MC.ALL}",$B$4:$B${n_s},B{r})').number_format = "0.00"
        sa.cell(row=r, column=6, value=(f"=E{r}" if row["Group"] == MC.ALL else f"=(D{r}+{K}*E{r})/(C{r}+{K})")).number_format = "0.00"
    SR = lambda c: f"State_Averages!${c}$4:${c}${n_s}"

    # ---- Backtest calls (walk-forward probabilities as values; calls and checks as formulas)
    calls = []
    for g in groups:
        for c in R["groups"][g]["calls"]:
            calls.append({"Group": g, "Fund": c["fund"], "Category": c["category"], "Predicted year": c["year"],
                          "State last year": c["state"] + 1, **{f"P(state {j + 1})": c["probs"][j] for j in range(4)},
                          "Expected excess %": c["expected"], f"Call: beat {T:g}%+": None, "Actual excess %": c["actual"],
                          f"Right ({T:g}% call)": None, "Group past avg % (naive)": c["naive"], "Naive right": None,
                          "Miss": None, "Within tolerance": None, "Actual >= expected": None, "Naive miss": None,
                          "Naive within tolerance": None, "Naive: actual >= predicted": None})
    cd = pd.DataFrame(calls)
    sb = book.create_sheet("Backtest_Calls")
    write_table(sb, cd, title=f"Every backtest prediction, returns {a}-{b}: the matrix from the years before only; call 'beat' if "
                              f"P(state 4) >= 50%; the three hit ratios and the naive call (formulas)",
                widths=[16, 38, 16, 9, 8, 9, 9, 9, 9, 10, 9, 10, 8, 11, 8, 8, 8, 9, 9, 9, 10],
                formats={**{f"P(state {j + 1})": "0.0%" for j in range(4)}, "Expected excess %": "0.00", "Actual excess %": "0.00",
                         "Group past avg % (naive)": "0.00"})
    TOL = "Results!$B$2"
    n = len(cd)
    put(sb, 4, n, 11, '=IF(I{r}>=0.5,"Yes","No")')
    put(sb, 4, n, 13, f"=IF((I{{r}}>=0.5)=(L{{r}}>={T:g}),1,0)")
    put(sb, 4, n, 15, f"=IF((N{{r}}>={T:g})=(L{{r}}>={T:g}),1,0)")
    put(sb, 4, n, 16, "=ABS(L{r}-J{r})", "0.00")
    put(sb, 4, n, 17, f"=IF(P{{r}}<={TOL},1,0)")
    put(sb, 4, n, 18, "=IF(L{r}>=J{r},1,0)")
    put(sb, 4, n, 19, "=ABS(L{r}-N{r})", "0.00")
    put(sb, 4, n, 20, f"=IF(S{{r}}<={TOL},1,0)")
    put(sb, 4, n, 21, "=IF(L{r}>=N{r},1,0)")
    n_b = n + 3
    BR = lambda c: f"Backtest_Calls!${c}$4:${c}${n_b}"

    # ---- Results (formulas over Backtest_Calls)
    res = book.create_sheet("Results", 1)
    res.cell(row=1, column=1, value=f"Backtest results, returns {a}-{b}: each group's three hit ratios vs the naive call "
                                    f"(formulas over Backtest_Calls)").font = TITLE_FONT
    res.cell(row=2, column=1, value="Tolerance (points):").font = Font(bold=True)
    res.cell(row=2, column=2, value=MC.TOLERANCE).font = Font(bold=True, color="C00000")
    heads = ["Group", "Predictions", f"{T:g}% call right", "Hit ratio", "Naive right", "Naive hit ratio", "Within tolerance",
             "Hit ratio", "Naive within", "Naive hit ratio", "Actual >= expected", "Hit ratio", "Naive", "Naive hit ratio",
             "Average miss", "Naive average miss", f"Feasible ({T:g}% call)", "Feasible (tolerance)", "Feasible (actual >= expected)"]
    header(res, 4, heads, [18] + [10] * 18)
    for i, g in enumerate(groups):
        r = 5 + i
        res.cell(row=r, column=1, value=g)
        k = f'{BR("A")},A{r}'
        res.cell(row=r, column=2, value=f"=COUNTIFS({k})")
        for c0, src in ((3, "M"), (5, "O"), (7, "Q"), (9, "T"), (11, "R"), (13, "U")):
            res.cell(row=r, column=c0, value=f"=SUMIFS({BR(src)},{k})")
            res.cell(row=r, column=c0 + 1, value=f'=IF($B{r}>0,{col(c0)}{r}/$B{r},"")').number_format = "0.0%"
        res.cell(row=r, column=15, value=f'=IF($B{r}>0,SUMIFS({BR("P")},{k})/$B{r},"")').number_format = "0.00"
        res.cell(row=r, column=16, value=f'=IF($B{r}>0,SUMIFS({BR("S")},{k})/$B{r},"")').number_format = "0.00"
        for c0, (rc, nc) in zip((17, 18, 19), (("C", "E"), ("G", "I"), ("K", "M"))):
            res.cell(row=r, column=c0, value=f'=IF(AND($B{r}>={MC.MIN_CALLS},{rc}{r}/$B{r}>{MC.HIT_RATIO},{rc}{r}>{nc}{r}),"Yes","no")')
    res.freeze_panes = "B5"

    # ---- By year (values)
    yr = []
    for g in groups:
        for y in R["groups"][g]["years"]:
            yr.append({"Group": g, "Predicted year": y["year"], "Predictions": y["n"], "Called beat": y["called"],
                       "Actually beat": y["beat"], f"{T:g}% call right": y["hits"], "Naive right": y["naive"],
                       "Group past avg % (naive)": y["naive_avg"], "Average miss": y["abs_err"] / y["n"],
                       "Naive average miss": y["naive_abs_err"] / y["n"]})
    write_table(book.create_sheet("By_Year"), pd.DataFrame(yr), title="The backtest by group and predicted year",
                widths=[18, 9, 10, 9, 9, 10, 9, 12, 9, 10],
                formats={"Group past avg % (naive)": "0.00", "Average miss": "0.00", "Naive average miss": "0.00"})

    # ---- Category chain
    cc = R["category_chain"]
    ser = cc["series"].rename(columns={"category": "Category", "year": "Year", "x": "Category avg excess %"})
    ser["State"] = None
    scs = book.create_sheet("Category_Chain")
    write_table(scs, ser[["Category", "Year", "Category avg excess %", "State"]],
                title="The category chain: each category's average excess over the Nifty 50 per year and its state (formula)",
                widths=[18, 7, 13, 6], formats={"Category avg excess %": "0.00"})
    put(scs, 4, len(ser), 4, STATE_F.format(c="C"))
    cr = pd.DataFrame([{"Category": x["category"], "Predicted year": x["year"], "State last year": x["state"] + 1,
                        **{f"P(state {j + 1})": x["probs"][j] for j in range(4)}, "Expected %": x["expected"],
                        "Actual %": x["actual"], "Past average % (naive)": x["naive"], f"Call {T:g}%+": None, "Right": None,
                        "Naive right": None} for x in cc["rows"]])
    scb = book.create_sheet("Category_Chain_Backtest")
    write_table(scb, cr, title=f"Category chain backtest, returns {a}-{b}: pooled matrix from the years before; does the category beat "
                               f"the Nifty 50 by {T:g}%+?", widths=[18, 9, 8, 9, 9, 9, 9, 10, 9, 12, 8, 7, 8],
                formats={**{f"P(state {j + 1})": "0.0%" for j in range(4)}, "Expected %": "0.00", "Actual %": "0.00",
                         "Past average % (naive)": "0.00"})
    put(scb, 4, len(cr), 11, '=IF(G{r}>=0.5,"Yes","No")')
    put(scb, 4, len(cr), 12, f"=IF((G{{r}}>=0.5)=(I{{r}}>={T:g}),1,0)")
    put(scb, 4, len(cr), 13, f"=IF((J{{r}}>={T:g})=(I{{r}}>={T:g}),1,0)")

    # ---- Predictions (formulas over Matrix and State_Averages)
    pr = R["groups"][MC.ALL]["pred"]
    members = data.panel[data.panel["param_year"] == ly].set_index("scheme_id")
    live = (members["fund_return"] - data.nifty_partial)
    pp = pd.DataFrame({"Fund": pr["scheme_name"], "Category": pr["category"], f"Excess {b} %": pr["x"], f"State in {b}": None,
                       **{f"P(state {j + 1})": None for j in range(4)}, f"Expected excess {ty} %": None,
                       f"Beats the Nifty by {T:g}%+? (P(state 4) >= 50%)": None,
                       "Validated (category passes the 3% call test)": None,
                       f"Actual so far ({R['live_label']}) %": pr["scheme_id"].map(live)}).sort_values(["Category", "Fund"])
    sp = book.create_sheet("Predictions")
    write_table(sp, pp, title=f"{ty} prediction for every fund from its {b} state, with its category's matrix (formulas: SUMIFS over "
                              "Matrix and State_Averages)", widths=[40, 16, 10, 8, 9, 9, 9, 9, 11, 14, 14, 13],
                formats={f"Excess {b} %": "0.00", f"Actual so far ({R['live_label']}) %": "0.00"})
    n_p = len(pp)
    put(sp, 4, n_p, 4, STATE_F.format(c="C"))
    for j in range(4):
        put(sp, 4, n_p, 5 + j, f"=SUMIFS({MR('G')},{MR('A')},$B{{r}},{MR('B')},$D{{r}},{MR('C')},{j + 1})", "0.0%")
    put(sp, 4, n_p, 9, "=" + "+".join(f"{col(5 + j)}{{r}}*SUMIFS({SR('F')},{SR('A')},$B{{r}},{SR('B')},{j + 1})" for j in range(4)), "0.00")
    put(sp, 4, n_p, 10, '=IF(H{r}>=0.5,"Yes","No")')
    put(sp, 4, n_p, 11, f'=IFERROR(INDEX(Results!$Q$5:$Q${4 + len(groups)},MATCH(B{{r}},Results!$A$5:$A${4 + len(groups)},0)),"")')

    write_param_sheets(book, R, PR, data)
    write_guide(book, R, groups)
    for ws in book.worksheets:
        if ws.title not in ("Read_Me", "Results", "States") and ws.max_row > 3:
            ws.auto_filter.ref = f"A3:{col(ws.max_column)}{ws.max_row}"
    order = ["Read_Me", "Results", "States", "Transitions", "Matrix", "State_Averages", "Backtest_Calls", "By_Year",
             "Category_Chain", "Category_Chain_Backtest", "Predictions", "Param_Results", "Param_Matrix", "Param_State_Averages",
             "Param_Predictions"]
    book._sheets = [book[n] for n in order]
    book.save(WORKBOOK)


def state_label(variant, i):
    if variant == "param":
        return MC.THIRDS[i]
    return f"{MC.STATES[i // 3]} & {MC.THIRDS[i % 3].lower()}"


def write_param_sheets(book, R, PR, data):
    """Parameter-based chains: results, matrices (formulas), state averages, predictions (formulas)."""
    T, ty = MC.TARGET, R["target_year"]
    a, b = R["test"]
    rows = []
    for g, models in PR.items():
        base = R["groups"][g]["overall"]
        if base:
            rows.append({"Group": g, "Parameter": "(last year's return only)", "Model": "Return only", **res_cols(base)})
        for (param, variant), m in models.items():
            if m["overall"]:
                rows.append({"Group": g, "Parameter": param, "Model": MC.VARIANTS[variant], **res_cols(m["overall"])})
    df = pd.DataFrame(rows)
    sh = book.create_sheet("Param_Results")
    write_table(sh, df, title=f"Parameter-based chains vs the return-only chain, returns {a}-{b}: each model's three hit ratios vs the "
                              f"naive call. Feasible = > {MC.HIT_RATIO:.0%}, better than naive, {MC.MIN_CALLS}+ predictions. "
                              "Many models are tried per group, so a narrow pass is likely luck.",
                widths=[18, 38, 26, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9],
                formats={c: "0.0%" for c in df.columns if "ratio" in c} | {"Average miss": "0.00", "Naive average miss": "0.00"})
    # matrices (long, formulas)
    mrows = []
    for g, models in PR.items():
        for (param, variant), m in models.items():
            k = 3 if variant == "param" else 12
            for i in range(k):
                for j in range(4):
                    mrows.append({"Group": g, "Parameter": param, "Model": MC.VARIANTS[variant], "From state": i + 1,
                                  "From (meaning)": state_label(variant, i), "To state": j + 1, "Count": int(m["counts"][i, j]),
                                  "All-funds count": int(m["pooled_counts"][i, j]), "Row total": None, "All-funds P": None, "P": None})
    md = pd.DataFrame(mrows)
    sm = book.create_sheet("Param_Matrix")
    write_table(sm, md, title="Parameter-based transition matrices (all transitions up to the last full year): the group's counts and the "
                              "all-funds counts for the same parameter; P = (count + States!B10 x all-funds P) / (row total + States!B10) as formulas",
                widths=[16, 34, 26, 7, 34, 7, 7, 9, 8, 10, 8])
    n = len(md) + 3
    R_ = lambda c: f"${c}$4:${c}${n}"
    for i, row in enumerate(mrows):
        r = 4 + i
        same = f"{R_('A')},A{r},{R_('B')},B{r},{R_('C')},C{r},{R_('D')},D{r}"
        sm.cell(row=r, column=9, value=f"=SUMIFS({R_('G')},{same})")
        sm.cell(row=r, column=10, value=f"=IFERROR(H{r}/SUMIFS({R_('H')},{same}),0.25)").number_format = "0.0%"
        sm.cell(row=r, column=11, value=(f"=J{r}" if row["Group"] == MC.ALL else f"=(G{r}+States!$B$10*J{r})/(I{r}+States!$B$10)")).number_format = "0.0%"
    PM = lambda c: f"Param_Matrix!${c}$4:${c}${n}"
    # state averages (values, from the model fit)
    sa = pd.DataFrame([{"Group": g, "Parameter": param, "Model": MC.VARIANTS[variant], "State": j + 1, "Average excess %": m["means"][j]}
                       for g, models in PR.items() for (param, variant), m in models.items() for j in range(4)])
    write_table(book.create_sheet("Param_State_Averages"), sa, title="Average excess in each next-year state, per model (blended as in State_Averages)",
                widths=[16, 34, 26, 6, 11], formats={"Average excess %": "0.00"})
    ns = len(sa) + 3
    SA = lambda c: f"Param_State_Averages!${c}$4:${c}${ns}"
    # predictions (formulas)
    names = dict(zip(data.panel["scheme_id"], data.panel["scheme_name"]))
    prow = []
    for g, models in PR.items():
        for (param, variant), m in models.items():
            for x in m["pred"].itertuples():
                st = int(x.third) if variant == "param" else int(x.js)
                prow.append({"Group": g, "Parameter": param, "Model": MC.VARIANTS[variant], "Fund": names.get(x.scheme_id, x.scheme_name),
                             f"Excess {b} %": x.x, f"Return state {b}": int(x.s) + 1, "Parameter value": x.v,
                             "Third in category": int(x.third) + 1, "From state": st + 1,
                             **{f"P(state {j + 1})": None for j in range(4)}, f"Expected excess {ty} %": None,
                             f"Beats by {T:g}%+?": None})
    pdf = pd.DataFrame(prow)
    sp = book.create_sheet("Param_Predictions")
    write_table(sp, pdf, title=f"{ty} predictions from every parameter-based model (P and expected excess are formulas over "
                               "Param_Matrix and Param_State_Averages). Only a model that passed in Param_Results deserves weight.",
                widths=[16, 34, 26, 40, 9, 8, 10, 8, 7, 9, 9, 9, 9, 10, 9],
                formats={f"Excess {b} %": "0.00", "Parameter value": "0.000"})
    npr = len(pdf)
    key = lambda r: f"{PM('A')},$A{r},{PM('B')},$B{r},{PM('C')},$C{r},{PM('D')},$I{r}"
    for i in range(npr):
        r = 4 + i
        for j in range(4):
            sp.cell(row=r, column=10 + j, value=f"=SUMIFS({PM('K')},{key(r)},{PM('F')},{j + 1})").number_format = "0.0%"
        sp.cell(row=r, column=14, value="=" + "+".join(
            f"{get_column_letter(10 + j)}{r}*SUMIFS({SA('E')},{SA('A')},$A{r},{SA('B')},$B{r},{SA('C')},$C{r},{SA('D')},{j + 1})"
            for j in range(4))).number_format = "0.00"
        sp.cell(row=r, column=15, value=f'=IF(M{r}>=0.5,"Yes","No")')


def res_cols(o):
    t = MC.TOLERANCE
    return {"Predictions": o["n"], f"{MC.TARGET:g}% call ratio": o["hits"] / o["n"], f"{MC.TARGET:g}% call naive ratio": o["naive"] / o["n"],
            f"Within ±{t} ratio": o[f"tol{t}"] / o["n"], f"Within ±{t} naive ratio": o[f"naive_tol{t}"] / o["n"],
            "Actual >= expected ratio": o["ge"] / o["n"], "Actual >= expected naive ratio": o["naive_ge"] / o["n"],
            "Average miss": o["abs_err"] / o["n"], "Naive average miss": o["naive_abs_err"] / o["n"],
            f"Feasible ({MC.TARGET:g}% call)": "Yes" if MC.feasible(o) else "no",
            f"Feasible (±{t})": "Yes" if MC.feasible(o, "diff", t) else "no",
            "Feasible (actual >= expected)": "Yes" if MC.feasible(o, "ge") else "no"}



def write_guide(book, R, groups):
    T, ty, ly = MC.TARGET, R["target_year"], R["latest_year"]
    a, b = R["test"]
    sh = book.create_sheet("Read_Me", 0)
    sh.column_dimensions["A"].width = 28
    sh.column_dimensions["B"].width = 118
    row = [1]

    def line(k, v=None, title=False, bold=False):
        sh.cell(row=row[0], column=1, value=k).font = TITLE_FONT if title else Font(bold=True)
        if v is not None:
            c = sh.cell(row=row[0], column=2, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if bold:
                c.font = Font(bold=True)
            sh.row_dimensions[row[0]].height = max(15, 15 * (len(v) // 114 + 1))
        row[0] += 1

    G = R["groups"][MC.ALL]
    P, c = G["P"], G["counts"]
    o = G["overall"]
    line("READ ME FIRST", title=True)
    row[0] += 1
    line("The idea", "A Markov chain asks: does where a fund is this year (its state) tell us where it will be next year? "
                     "States: " + "; ".join(f"{i + 1} = {s}" for i, s in enumerate(MC.STATES)) + " (excess over the Nifty 50 "
                     "in the calendar year). The transition matrix counts, for funds in each state one year, which state they "
                     "were in the next.")
    line("The answer", f"No. For all funds, a fund that beat the Nifty by {T:g}%+ had a {P[3, 3]:.0%} chance of doing it again; one that "
                       f"lagged by {T:g}%+ had {P[0, 3]:.0%}. Next year's state hardly depends on this year's, so the chain's "
                       f"P(beat by {T:g}%+) stays near the base rate and its calls are no better than the naive call "
                       f"({o['hits'] / o['n']:.0%} vs {o['naive'] / o['n']:.0%} on the {T:g}% call, returns {a}-{b}). No group passes.",
         bold=True)
    line("What it does show", f"Extremes repeat in either direction: from 'lagged by {T:g}%+', {P[0, 0]:.0%} lag again and "
                              f"{P[0, 3]:.0%} beat; from 'beat by {T:g}%+', {P[3, 0]:.0%} lag next. That is volatility (high-risk "
                              "funds swing both ways), not skill.")
    cco = R["category_chain"]["overall"]
    line("The category chain", f"Same idea for each category's average: right {cco['hits'] / cco['n']:.0%} vs naive "
                               f"{cco['naive'] / cco['n']:.0%} on '{T:g}%+' ({cco['n']} category-years).")
    row[0] += 1
    line("HOW TO READ", title=True)
    row[0] += 1
    for k, v in [("Results", "Each group's three hit ratios vs naive (formulas over Backtest_Calls); tolerance in cell B2."),
                 ("States", f"The four states; the blending weight ({MC.SMOOTH:g}) in cell B10."),
                 ("Transitions", "Every fund's consecutive pair of years with its states (formulas)."),
                 ("Matrix", "Counts (COUNTIFS over Transitions), row totals and probabilities (formulas), for all funds and each category."),
                 ("State_Averages", "The average excess in each state: used for the expected excess."),
                 ("Backtest_Calls", f"Every backtest prediction for returns {a}-{b}, with the matrix of the years before (values) and the "
                                    "calls and checks (formulas)."),
                 ("Category_Chain ...", "The same for category averages."),
                 ("Predictions", f"{ty}: each fund's {b} state -> its category's matrix row -> P(beat) and expected excess (formulas).")]:
        line(k, v)
    row[0] += 1
    line("VERIFY BY HAND", title=True)
    row[0] += 1
    tot = c[3].sum()
    line("1. One probability", f"Transitions: filter State = 4 (all funds): {int(tot)} rows. Of those, Next state = 4: {int(c[3, 3])}. "
                               f"P(4 -> 4) = {int(c[3, 3])} / {int(tot)} = {c[3, 3] / tot:.1%} (Matrix: Group = All funds, From 4, To 4).")
    pr = G["pred"].sort_values("expected", ascending=False).iloc[0]
    cat = pr["category"]
    Pc, mc = R["groups"][cat]["P"], R["groups"][cat]["means"]
    s = int(pr["s"])
    line("2. One prediction", f"{pr['scheme_name']} ({short(cat)}): excess {pr['x']:+.2f}% in {b} -> state {s + 1}. Matrix rows for "
                              f"{short(cat)}, from state {s + 1}: " + ", ".join(f"to {j + 1}: {Pc[s, j]:.1%}" for j in range(4))
                              + ". State_Averages for " + short(cat) + ": " + ", ".join(f"{j + 1}: {mc[j]:+.2f}" for j in range(4))
                              + f". Expected = " + " + ".join(f"{Pc[s, j]:.3f} x {mc[j]:+.2f}" for j in range(4))
                              + f" = {float(Pc[s] @ mc):+.2f}%. P(state 4) = {Pc[s, 3]:.1%} -> "
                              + ("beats" if Pc[s, 3] >= 0.5 else "does not beat") + f" the Nifty by {T:g}%+ (Predictions sheet).")
    line("Parameter-based chains", "Param_Results / Param_Matrix / Param_Predictions: the state also uses the fund's parameter - its third "
                                   "of the category this year (3 states), or that third x last year's return state (12 states). Same "
                                   "backtest and checks; compared with the return-only chain on the same sheet.")
    line("3. Category blending", f"A category's row = (its own count + {MC.SMOOTH:g} x the all-funds probability) / (its row total + "
                                 f"{MC.SMOOTH:g}); e.g. Matrix column G = (D + States!B10 x F) / (E + States!B10).")


def write_dashboard(R, PR, data, nifty_avg):
    def r(v, n=4):
        v = clean(v)
        return None if v is None else round(float(v), n)

    def res(x):
        return None if not x else {k: (r(v, 3) if isinstance(v, float) else v) for k, v in x.items()}

    ly = R["latest_year"]
    members = data.panel[data.panel["param_year"] == ly].sort_values(["category", "scheme_name"])
    fi = {sid: i for i, sid in enumerate(members["scheme_id"])}
    t = R["transitions"]
    full = t[t["year"] + 1 <= R["test"][1]]
    groups = []
    for g in [MC.ALL] + R["categories"]:
        G = R["groups"][g]
        tg = full if g == MC.ALL else full[full["category"] == g]
        n_to = tg.groupby("s_next").size().reindex(range(4)).fillna(0)
        s_to = tg.groupby("s_next")["x_next"].sum().reindex(range(4)).fillna(0)
        pred = [[fi[x.scheme_id], r(x.x, 3), int(x.s), *[r(getattr(x, f"p{j}")) for j in range(4)], r(x.expected, 4)]
                for x in G["pred"].itertuples() if x.scheme_id in fi]
        groups.append({"name": g, "overall": res(G["overall"]), "live": res(G["live"]),
                       "years": [res(y) for y in G["years"]], "P": [[r(v) for v in row] for row in G["P"]],
                       "means": [r(v, 3) for v in G["means"]], "counts": [[int(v) for v in row] for row in G["counts"]],
                       "nTo": [int(v) for v in n_to], "sumTo": [r(v, 2) for v in s_to], "transitions": G["transitions_n"],
                       "naiveAll": r(G["naive_all"], 3), "pred": pred})
    gi_of = {g["name"]: i for i, g in enumerate(groups)}
    for g, models in PR.items():
        ms = []
        for (param, variant), m in models.items():
            ms.append({"param": param, "variant": variant, "overall": res(m["overall"]), "live": res(m["live"]),
                       "P": [[r(v) for v in row] for row in m["P"]], "means": [r(v, 3) for v in m["means"]],
                       "counts": [[int(v) for v in row] for row in m["counts"]],
                       "pooled": [[int(v) for v in row] for row in m["pooled_counts"]],
                       "pred": [[fi[x.scheme_id], r(x.x, 3), int(x.s), int(x.third), r(x.v, 4)] for x in m["pred"].itertuples() if x.scheme_id in fi]})
        groups[gi_of[g]]["models"] = ms
    cc = R["category_chain"]
    payload = {"latestYear": ly, "targetYear": R["target_year"], "test": list(R["test"]), "liveLabel": R["live_label"],
               "states": MC.STATES, "thirds": MC.THIRDS, "variants": MC.VARIANTS, "target": MC.TARGET, "smooth": MC.SMOOTH, "hitRatio": MC.HIT_RATIO, "minCalls": MC.MIN_CALLS,
               "tolerances": list(MC.TOLERANCES), "tolerance": MC.TOLERANCE, "niftyAverage": r(nifty_avg, 2),
               "niftyPartial": r(data.nifty_partial, 2), "categories": R["categories"], "groups": groups,
               "categoryChain": {"overall": res(cc["overall"]), "P": [[r(v) for v in row] for row in cc["P"]],
                                 "means": [r(v, 3) for v in cc["means"]], "counts": [[int(v) for v in row] for row in cc["counts"]],
                                 "series": [[x.category, int(x.year), r(x.x, 2)] for x in cc["series"].itertuples()],
                                 "pred": [[x.category, r(x.x, 2), int(x.s), *[r(getattr(x, f"p{j}")) for j in range(4)], r(x.expected, 3)]
                                          for x in cc["pred"].itertuples()]},
               "funds": [{"id": m.scheme_id, "name": m.scheme_name, "category": m.category,
                          "live": r(m.fund_return - data.nifty_partial, 2) if m.fund_return == m.fund_return else None}
                         for m in members.itertuples()]}
    DATA.write_text("window.MARKOV = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=clean) + ";\n")


def main():
    data = S.load()
    R = MC.run(data)
    spr = SP.run(data, pickle.loads(CACHE.read_bytes())["univariate"])
    PR = MC.run_params(data, R, spr)
    nifty_avg = float(data.nifty.reindex([y + 1 for y in data.full_years]).mean())
    write_workbook(R, PR, data, nifty_avg)
    write_dashboard(R, PR, data, nifty_avg)
    o = R["groups"][MC.ALL]["overall"]
    print(f"Wrote {WORKBOOK.name} and dashboard/{DATA.name}: all funds 3% call {o['hits']}/{o['n']} vs naive {o['naive']}; "
          f"feasible groups: {[g for g, x in R['groups'].items() if MC.feasible(x['overall'])]}")
    for g, models in PR.items():
        f = [(k, h) for k, m in models.items() for h in ("call", "diff", "ge") if MC.feasible(m["overall"], h)]
        print(f"  {g[:16]:16} {len(models):2} parameter models; passing: {f}")


if __name__ == "__main__":
    main()
