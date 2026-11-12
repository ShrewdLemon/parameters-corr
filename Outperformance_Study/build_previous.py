"""Previous parameters tab: the nine parameters from the earlier correlation study, put through the
same backtest as Testing & prediction (fifths, past-only averages, three hit ratios vs the naive
call, deviation, predicted-excess baskets) in every group.

    python build.py              # once: the Statistical analysis cache
    python build_previous.py

Outputs:
    Previous_Parameters.xlsx     the working (calls, checks, deviations and baskets are formulas)
    dashboard/previous.js        data for the dashboard's Previous parameters tab
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
from build import CACHE, TITLE_FONT, clean, header, write_table

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Previous_Parameters.xlsx"
DATA = HERE / "dashboard" / "previous.js"
col = get_column_letter
DISPLAY = {c: (name, corr) for name, c, corr in SP.PREVIOUS}
BASKET_F = '=IF({c}="","",IF({c}<0,"below 0%",IF({c}>=10,"10% and above",INT({c})&"-"&(INT({c})+1)&"%")))'


def short(name):
    return name.replace(" Funds", "").replace(" Fund", "").replace("Small cap", "Small Cap")


def put(sheet, first, n, column, template, fmt=None):
    for r in range(first, first + n):
        c = sheet.cell(row=r, column=column, value=template.format(r=r))
        if fmt:
            c.number_format = fmt


def feasible(b, how="call", tol=SP.TOLERANCE, cut=SP.HIT_RATIO):
    if not b or b["calls"] < SP.MIN_CALLS:
        return False
    right, naive = SP.measure(b, how, tol)
    return right / b["calls"] > cut and right > naive


def write_workbook(R):
    T, ly, ty = SP.TARGET, R["latest_year"], R["target_year"]
    a, b = R["test"]
    book = Workbook()
    book.calculation.fullCalcOnLoad = True

    # ---- Backtest_Calls
    calls = []
    for g in R["groups"]:
        for r in g["params"]:
            for c in r["backtest"]["detail"]:
                calls.append({"Group": g["name"], "Parameter": DISPLAY[r["parameter"]][0], "Parameter year": c["year"],
                              "Return year": c["year"] + 1, "Fund": c["fund"], "Value": c["value"], "Fifth": c["fifth"],
                              "Predicted excess %": c["pred"], "Call": None, "Actual excess %": c["excess"],
                              f"Actually beat {T:g}%+": None, "Right": None, "Group past avg % (naive)": c["naive_avg"],
                              "Naive right": None, "Miss": None, "Within tolerance": None, "Actual >= predicted": None,
                              "Naive miss": None, "Naive within tolerance": None, "Naive: actual >= predicted": None,
                              "Deviation (actual - predicted)": None, "Naive deviation": None, "Basket (predicted excess)": None})
    cd = pd.DataFrame(calls)
    sc = book.active
    sc.title = "Backtest_Calls"
    write_table(sc, cd, title=f"Every backtest prediction, returns {a + 1}-{b + 1}: the fund's fifth that year -> that fifth's average "
                              f"next-year excess over the years before (predicted); call 'Beat {T:g}%+' if >= {T:g}; checks and "
                              "deviation are formulas; naive = the group's past average",
                widths=[16, 26, 9, 9, 40, 10, 6, 11, 10, 11, 10, 6, 11, 8, 8, 9, 9, 8, 9, 9, 11, 9, 13],
                formats={"Value": "0.000", "Predicted excess %": "0.00", "Actual excess %": "0.00", "Group past avg % (naive)": "0.00"})
    n = len(cd)
    TOL = "Results!$B$2"
    put(sc, 4, n, 9, f'=IF(H{{r}}>={T:g},"Beat {T:g}%+","No")')
    put(sc, 4, n, 11, f'=IF(J{{r}}>={T:g},"Yes","No")')
    put(sc, 4, n, 12, f"=IF((H{{r}}>={T:g})=(J{{r}}>={T:g}),1,0)")
    put(sc, 4, n, 14, f"=IF((M{{r}}>={T:g})=(J{{r}}>={T:g}),1,0)")
    put(sc, 4, n, 15, "=ABS(J{r}-H{r})", "0.00")
    put(sc, 4, n, 16, f"=IF(O{{r}}<={TOL},1,0)")
    put(sc, 4, n, 17, "=IF(J{r}>=H{r},1,0)")
    put(sc, 4, n, 18, "=ABS(J{r}-M{r})", "0.00")
    put(sc, 4, n, 19, f"=IF(R{{r}}<={TOL},1,0)")
    put(sc, 4, n, 20, "=IF(J{r}>=M{r},1,0)")
    put(sc, 4, n, 21, "=J{r}-H{r}", "0.00")
    put(sc, 4, n, 22, "=J{r}-M{r}", "0.00")
    for r in range(4, 4 + n):
        sc.cell(row=r, column=23, value=BASKET_F.format(c=f"H{r}"))
    last = n + 3
    C = lambda c: f"Backtest_Calls!${c}$4:${c}${last}"

    # ---- Results
    res = book.create_sheet("Results", 0)
    res.cell(row=1, column=1, value=f"The previous parameters in every group, returns {a + 1}-{b + 1}: three hit ratios vs the naive call, "
                                    "deviation and average miss (formulas over Backtest_Calls)").font = TITLE_FONT
    res.cell(row=2, column=1, value="Tolerance (points):").font = Font(bold=True)
    res.cell(row=2, column=2, value=SP.TOLERANCE).font = Font(bold=True, color="C00000")
    heads = ["Group", "Parameter", "Morningstar name", "Earlier correlation", "Statistical analysis", "Slope (pts per 1 SD)", "t",
             "Predictions", f"{T:g}% call right", "Hit ratio", "Naive right", "Naive hit ratio", "Within tolerance", "Hit ratio",
             "Naive within", "Naive hit ratio", "Actual >= predicted", "Hit ratio", "Naive", "Naive hit ratio",
             "Average deviation (actual - predicted)", "Naive average deviation", "Average miss", "Naive average miss",
             f"Feasible ({T:g}% call: > {SP.HIT_RATIO:.0%} and > naive)"]
    header(res, 4, heads, [16, 24, 30, 9, 18, 10, 7, 9, 9, 8, 9, 8, 9, 8, 9, 8, 9, 8, 8, 8, 12, 11, 9, 10, 14])
    r = 5
    for g in R["groups"]:
        for x in g["params"]:
            name, corr = DISPLAY[x["parameter"]]
            k = f'{C("A")},$A{r},{C("B")},$B{r}'
            vals = [g["name"], name, x["parameter"], corr, x["verdict"], clean(x["slope"]), clean(x["t"]), f"=COUNTIFS({k})"]
            for c, v in enumerate(vals, 1):
                res.cell(row=r, column=c, value=v)
            for c0, src in ((9, "L"), (11, "N"), (13, "P"), (15, "S"), (17, "Q"), (19, "T")):
                res.cell(row=r, column=c0, value=f"=SUMIFS({C(src)},{k})")
                res.cell(row=r, column=c0 + 1, value=f'=IF($H{r}>0,{col(c0)}{r}/$H{r},"")').number_format = "0.0%"
            for c0, src in ((21, "U"), (22, "V"), (23, "O"), (24, "R")):
                res.cell(row=r, column=c0, value=f'=IF($H{r}>0,SUMIFS({C(src)},{k})/$H{r},"")').number_format = "0.00"
            res.cell(row=r, column=25, value=f'=IF(AND($H{r}>={SP.MIN_CALLS},J{r}>{SP.HIT_RATIO},I{r}>K{r}),"Yes","no")')
            res.cell(row=r, column=6).number_format = "0.000"
            res.cell(row=r, column=7).number_format = "0.00"
            r += 1
    res.freeze_panes = "C5"
    res.auto_filter.ref = f"A4:{col(len(heads))}{r - 1}"

    # ---- Baskets
    brows = []
    for g in R["groups"]:
        for pname in ["(all nine)"] + [DISPLAY[x["parameter"]][0] for x in g["params"]]:
            for lo, hi in zip(SP.BASKETS[:-1], SP.BASKETS[1:]):
                brows.append({"Group": g["name"], "Parameter": pname, "Basket (predicted excess)": SP.basket_label(lo, hi),
                              "Predictions": None, "Average predicted %": None, "Average actual %": None,
                              "Average deviation (actual - predicted)": None, "Average miss": None,
                              f"Actually beat {T:g}%+": None, "Share that beat": None})
    sb = book.create_sheet("Baskets")
    write_table(sb, pd.DataFrame(brows), title="Backtest predictions grouped by predicted excess: what each basket actually delivered "
                                               "(formulas over Backtest_Calls)", widths=[16, 26, 16, 10, 10, 10, 12, 9, 10, 9])
    for i, row in enumerate(brows):
        r = 4 + i
        k = f'{C("A")},$A{r},{C("W")},$C{r}' + ("" if row["Parameter"].startswith("(") else f',{C("B")},$B{r}')
        sb.cell(row=r, column=4, value=f"=COUNTIFS({k})")
        for c, src in ((5, "H"), (6, "J"), (7, "U"), (8, "O")):
            sb.cell(row=r, column=c, value=f'=IF($D{r}>0,AVERAGEIFS({C(src)},{k}),"")').number_format = "0.00"
        sb.cell(row=r, column=9, value=f'=COUNTIFS({k},{C("K")},"Yes")')
        sb.cell(row=r, column=10, value=f'=IF($D{r}>0,I{r}/D{r},"")').number_format = "0%"

    # ---- Predictions for the next year
    pr = []
    for g in R["groups"]:
        names = dict(zip(g["members"]["scheme_id"], g["members"]["scheme_name"]))
        live = dict(zip(g["members"]["scheme_id"], g["members"]["live_excess"]))
        for x in g["params"]:
            if not x["quintiles"]:
                continue
            for sid, (v, f) in x["latest"].items():
                pr.append({"Group": g["name"], "Parameter": DISPLAY[x["parameter"]][0], "Fund": names[sid], f"{ly} value": v,
                           "Fifth": f, f"Predicted excess {ty} %": x["quintiles"][f - 1], "Basket": None,
                           f"Beats the Nifty by {T:g}%+?": None, f"Actual so far ({R['live_label']}) %": live.get(sid)})
    pdf = pd.DataFrame(pr).sort_values(["Group", "Parameter", f"Predicted excess {ty} %"], ascending=[True, True, False])
    sp = book.create_sheet(f"Predictions_{ty}")
    write_table(sp, pdf, title=f"{ty}: each fund's {ly} fifth by each previous parameter -> that fifth's average next-year excess over all "
                               "years (the prediction), its basket and the 3%+ call. None of these parameters passed the backtest, so "
                               "treat them as illustration.", widths=[16, 26, 40, 10, 6, 12, 13, 12, 13],
                formats={f"{ly} value": "0.000", f"Predicted excess {ty} %": "0.00", f"Actual so far ({R['live_label']}) %": "0.00"})
    for r in range(4, 4 + len(pdf)):
        sp.cell(row=r, column=7, value=BASKET_F.format(c=f"F{r}"))
        sp.cell(row=r, column=8, value=f'=IF(F{r}>={T:g},"Yes","No")')

    write_guide(book, R)
    for ws in book.worksheets:
        if ws.title not in ("Read_Me", "Results") and ws.max_row > 3:
            ws.auto_filter.ref = f"A3:{col(ws.max_column)}{ws.max_row}"
    book._sheets = [book[x] for x in ["Read_Me", "Results", "Baskets", "Backtest_Calls", f"Predictions_{ty}"]]
    book.save(WORKBOOK)


def write_guide(book, R):
    T, ly, ty = SP.TARGET, R["latest_year"], R["target_year"]
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

    line("READ ME FIRST", title=True)
    row[0] += 1
    line("What these are", "The nine parameters from the earlier correlation study, with the correlation it reported: " +
         "; ".join(f"{n} ({c:+.2f})" for n, _, c in SP.PREVIOUS) + ". Morningstar names: " +
         "; ".join(f"{n} = {m}" for n, m, _ in SP.PREVIOUS) + ".")
    line("How they are tested", f"Exactly as in Testing & prediction, in every group: each year (parameters {a}-{b}, returns {a + 1}-{b + 1}) "
                                "the group's funds are split into 5 equal ranges (fifths) by the parameter; a fund's predicted excess = "
                                "its fifth's average next-year excess over the Nifty 50 in the years before only. Three hit ratios, each "
                                f"vs the naive call (the group's past average for every fund): the {T:g}%+ call; within the tolerance "
                                "(Results!B2); actual >= predicted. Deviation = actual - predicted. Baskets group the predictions by "
                                "predicted excess (below 0%, 0-1%, ..., 5-6%, ..., 10% and above).")
    passed = [(g["name"], DISPLAY[x["parameter"]][0], h) for g in R["groups"] for x in g["params"]
              for h in ("call", "diff", "ge") if feasible(x["backtest"], h)]
    line("The answer", (f"Feasible somewhere: " + "; ".join(f"{short(g)} - {p} ({h})" for g, p, h in passed) + ". " if passed else
                        f"None of the nine passes in any group (hit ratio > {SP.HIT_RATIO:.0%} and better than naive) on any of the three hit ratios. ")
         + "The earlier correlations were pooled across years, so they mostly reflect which years were good for risky funds; "
           "ranked within each year they carry little information about next year.", bold=True)
    g = R["groups"][0]
    for x in g["params"]:
        bt = x["backtest"]
        if bt["calls"]:
            nm = bt["calls"]
            line(f"  {DISPLAY[x['parameter']][0]} (all funds)", f"{T:g}% call {bt['hits'] / nm:.1%} vs naive {bt['naive'] / nm:.1%}; "
                                                                 f"average deviation {bt['dev'] / nm:+.2f}, average miss {bt['abs_err'] / nm:.2f} pts.")
    row[0] += 1
    line("VERIFY BY HAND", title=True)
    row[0] += 1
    x = g["params"][0]
    c = sorted(x["backtest"]["detail"], key=lambda c: (-c["year"], c["fund"]))[0]
    line("One prediction", f"Backtest_Calls, Group = All Funds, Parameter = {DISPLAY[x['parameter']][0]}, {c['fund']}, parameter year {c['year']}: "
                           f"value {c['value']:.3f} -> fifth {c['fifth']} -> predicted {c['pred']:+.2f}% (that fifth's average over the "
                           f"years before {c['year']}); actual {c['excess']:+.2f}% -> deviation {c['excess'] - c['pred']:+.2f}; basket "
                           f"{SP.basket_of(c['pred'])}.")
    line("One basket", "Baskets: filter Group and Parameter; Predictions = COUNTIFS of Backtest_Calls in that basket; average actual = "
                       "AVERAGEIFS of Actual excess; share that beat = Actually beat 3%+ / Predictions.")


def write_dashboard(R, data):
    def r(v, n=3):
        v = clean(v)
        return None if v is None else round(float(v), n)

    members = data.panel[data.panel["param_year"] == R["latest_year"]].sort_values(["category", "scheme_name"])
    fi = {sid: i for i, sid in enumerate(members["scheme_id"])}
    live = members["fund_return"] - data.nifty_partial
    groups = []
    for g in R["groups"]:
        ps = []
        for x in g["params"]:
            b, lv = x["backtest"], x["live"]
            name, corr = DISPLAY[x["parameter"]]
            ps.append({"name": name, "col": x["parameter"], "corr": corr, "verdict": x["verdict"], "slope": r(x["slope"]), "t": r(x["t"], 2),
                       "p": r(x["p"], 5), "quint": [r(v, 3) for v in x["quintiles"]] if x["quintiles"] else None, "qYears": x["quintile_years"],
                       "bt": {k: (r(b[k], 2) if isinstance(b[k], float) else b[k]) for k in ("calls", "hits", "naive", "called", "called_right", "beat") + tuple(SP.OTHER_KEYS)}
                       | {"years": [[t["year"], t["past_years"], [r(v, 2) for v in t["fifth_avg"]], r(t["naive_avg"], 2), t["funds"], t["called"], t["beat"], t["hits"], t["naive_hits"]] for t in b["years"]],
                          "baskets": [[k["n"], r(k["sum_pred"], 2), r(k["sum_actual"], 2), k["beat"], r(k["abs_dev"], 2)] for k in x["baskets"]]},
                       "live": None if not lv else {k: (r(lv[k], 2) if isinstance(lv[k], float) else lv[k]) for k in ("calls", "hits", "naive", "called", "called_right", "beat") + tuple(SP.OTHER_KEYS)},
                       "bounds": [[r(lo, 4), r(hi, 4), n] for lo, hi, n in x["latest_bounds"]],
                       "latest": [[fi[sid], r(v, 4), f] for sid, (v, f) in x["latest"].items() if sid in fi]})
        groups.append({"name": g["name"], "funds": g["funds"], "obs": g["obs"], "groupAvg": r(g["group_avg"], 2), "params": ps})
    payload = {"latestYear": R["latest_year"], "targetYear": R["target_year"], "test": list(R["test"]), "liveLabel": R["live_label"],
               "niftyPartial": r(data.nifty_partial, 2),
               "settings": {"cuts": list(SP.CUTS), "cut": SP.HIT_RATIO, "minCalls": SP.MIN_CALLS, "target": SP.TARGET,
                            "tolerances": list(SP.TOLERANCES), "tolerance": SP.TOLERANCE,
                            "baskets": [SP.basket_label(lo, hi) for lo, hi in zip(SP.BASKETS[:-1], SP.BASKETS[1:])]},
               "groups": groups,
               "funds": [{"id": m.scheme_id, "name": m.scheme_name, "category": m.category, "live": r(lv_, 2)}
                         for m, lv_ in zip(members.itertuples(), live)]}
    DATA.write_text("window.PREVIOUS = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=clean) + ";\n")


def main():
    data = S.load()
    univariate = pickle.loads(CACHE.read_bytes())["univariate"]
    R = SP.run_parameters(data, univariate, [c for _, c, _ in SP.PREVIOUS])
    write_workbook(R)
    write_dashboard(R, data)
    passed = [(g["name"], DISPLAY[x["parameter"]][0], h) for g in R["groups"] for x in g["params"]
              for h in ("call", "diff", "ge") if feasible(x["backtest"], h)]
    print(f"Wrote {WORKBOOK.name} and dashboard/{DATA.name}; feasible: {passed or 'none'}")


if __name__ == "__main__":
    main()
