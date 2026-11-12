"""Research methods tab: literature methods for predicting excess return, tested on our data.

    python build_research.py

Outputs (separate from every other tab):
    Research_Methods.xlsx      the working
    dashboard/research.js      data for the dashboard's Research methods tab
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

import research_methods as RM
import study as S
from build import TITLE_FONT, clean, write_table

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Research_Methods.xlsx"
DATA = HERE / "dashboard" / "research.js"
WINDOWS = [("recent", 2020), ("long", 2010)]
REFERENCES = [
    ("Carhart (1997), On Persistence in Mutual Fund Performance, Journal of Finance",
     "https://www.trustnet.com/investing/13435101/the-lessons-of-mark-carharts-on-persistence-in-mutual-fund-performance"),
    ("Amihud & Goyenko (2013), Mutual Fund's R2 as Predictor of Performance, Review of Financial Studies",
     "https://archive.nyu.edu/handle/2451/28039"),
    ("Kaniel, Lin, Pelger & Van Nieuwerburgh (2023), Machine-Learning the Skill of Mutual Fund Managers, JFE",
     "https://www.nber.org/index%2Ephp/papers/w29723"),
    ("DeMiguel, Gil-Bazo, Nogales & Santos (2023), Machine learning and fund characteristics help to select mutual funds "
     "with positive alpha, JFE (see the replication note on look-ahead bias)", "https://data.mendeley.com/datasets/rpgb99m5zy"),
    ("Guha Deb, Banerjee & Chakrabarti (2008), Persistence in Performance of Indian Equity Mutual Funds, IIMB Management Review",
     "https://www.iimb.ac.in/imr/previous-issues/persistence-in-performance-june-2008.php"),
    ("Persistence in Performance of Actively Managed Equity Mutual Funds: New Indian Evidence (2019), IIMB Management Review",
     "https://www.iimb.ac.in/imr/previous-issues/persistence-june-2019.php"),
]


def short(name):
    return name.replace(" Fund", "").replace("Small cap", "Small Cap")


def ratio(a, b):
    return a / b if b else None


def put(sheet, first, n, column, template, fmt=None):
    for r in range(first, first + n):
        c = sheet.cell(row=r, column=column, value=template.format(r=r))
        if fmt:
            c.number_format = fmt


def result_row(label, res, extra=None):
    if not res:
        return {"Method": label, **(extra or {})}
    return {"Method": label, **(extra or {}), "Fund-years": res["n"], "Right": res["hits"],
            "Hit ratio": ratio(res["hits"], res["n"]), "Naive right": res["naive"], "Naive hit ratio": ratio(res["naive"], res["n"]),
            "Feasible (> 60% and > naive)": "Yes" if RM.feasible(res) else "no",
            "Called 3%+": res["called"], "Of those, beat": res["called_right"],
            "Precision": ratio(res["called_right"], res["called"]), "Share that beat 3%+": ratio(res["beat"], res["n"]),
            "Top fifth: share beat 3%+": ratio(res["top_beat"], res["top_n"]),
            "Bottom fifth: share beat 3%+": ratio(res["bot_beat"], res["bot_n"]),
            "Top fifth avg vs category %": res["top_rel"], "Bottom fifth avg vs category %": res["bot_rel"],
            "Spread (top - bottom) %": res["spread"], "Years spread > 0": f"{res['spread_years']} of {res['years']}",
            "Rank IC": res["ic"], "Top fifth above median": ratio(res["top_above"], res["top_n"]),
            "Bottom fifth below median": ratio(res["bot_below"], res["bot_n"])}


PCT = {k: "0.0%" for k in ["Hit ratio", "Naive hit ratio", "Precision", "Share that beat 3%+", "Top fifth: share beat 3%+",
                           "Bottom fifth: share beat 3%+", "Top fifth above median", "Bottom fifth below median"]}
NUM = {k: "0.00" for k in ["Top fifth avg vs category %", "Bottom fifth avg vs category %", "Spread (top - bottom) %"]} | {"Rank IC": "0.000"}


def write_workbook(runs, data, nifty_avg):
    R = runs["recent"]
    ly, ty, T = R["latest_year"], R["target_year"], RM.TARGET
    book = Workbook()
    book.calculation.fullCalcOnLoad = True
    labels = {m["key"]: m["label"] for m in R["methods"]}

    # ---- Methods
    sh = book.active
    sh.title = "Methods"
    sh.column_dimensions["A"].width = 30
    sh.column_dimensions["B"].width = 120
    rows = [("Research methods: what the literature uses to predict fund returns, tested on our data", None),
            ("Question", f"Does a fund beat the Nifty 50 by {T:g}%+ in the next calendar year? Same data, same question and same "
                         "rule as the Testing & prediction tab (hit ratio > 60% and better than the naive call)."),
            ("Two-part prediction", "Excess over the Nifty 50 = category part + fund part. Category part = the category's average "
                                    "yearly excess over the Nifty 50 in the years before. Fund part = the fund's expected return "
                                    "relative to its category's average, from one method below."),
            ("Single-signal methods", "Each year the funds of each category are split into fifths by the signal; the fund part is the "
                                      "average relative return of that fifth in the years before (pooled over categories)."),
            ("Walk-forward", "Every number used for year Y comes from the years before Y. Two test windows: parameter years "
                             f"{WINDOWS[0][1]}-{max(data.full_years)} (returns {WINDOWS[0][1] + 1}-{max(data.full_years) + 1}, as in "
                             f"Testing & prediction) and {WINDOWS[1][1]}-{max(data.full_years)} (15 years, for robustness)."),
            ("Methods", None)]
    rows += [(label, text) for _, label, text in RM.METHODS]
    rows += [("Avoid the worst", "Separately: do last year's bottom-fifth funds (by momentum) keep lagging their category?"),
             ("References", None)]
    rows += [(t, u) for t, u in REFERENCES]
    for i, (k, v) in enumerate(rows, 1):
        sh.cell(row=i, column=1, value=k).font = TITLE_FONT if v is None else Font(bold=True)
        if v:
            c = sh.cell(row=i, column=2, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if v.startswith("http"):
                c.hyperlink = v
                c.style = "Hyperlink"
            sh.row_dimensions[i].height = 30

    # ---- Results (recent: counted by formula from Backtest_Detail) and long
    det = []
    for m in R["methods"]:
        d = m["detail"]
        for _, x in d.iterrows():
            det.append({"Method": m["label"], "Fund": x["scheme_name"], "Category": x["category"], "Parameter year": int(x["param_year"]),
                        "Return year": int(x["param_year"]) + 1, "Category part %": x["cat_part"], "Fund part %": x["rel_pred"],
                        "Predicted excess %": None, "Call": None, "Actual excess %": x["target"],
                        f"Actually beat {T:g}%+": None, "Right": None, "Naive right": None})
    dd = pd.DataFrame(det)
    bd = book.create_sheet("Backtest_Detail")
    write_table(bd, dd, title=f"Every backtest prediction, returns {WINDOWS[0][1] + 1}-{max(data.full_years) + 1}: predicted = category part "
                              f"+ fund part (formula); call 'Beat {T:g}%+' if >= {T:g}; naive = the category part alone",
                widths=[28, 40, 16, 9, 9, 11, 10, 11, 10, 11, 10, 7, 8],
                formats={"Category part %": "0.00", "Fund part %": "0.00", "Actual excess %": "0.00"})
    n = len(dd)
    put(bd, 4, n, 8, "=F{r}+G{r}", "0.00")
    put(bd, 4, n, 9, f'=IF(H{{r}}>={T:g},"Beat {T:g}%+","No")')
    put(bd, 4, n, 11, f'=IF(J{{r}}>={T:g},"Yes","No")')
    put(bd, 4, n, 12, f"=IF((H{{r}}>={T:g})=(J{{r}}>={T:g}),1,0)")
    put(bd, 4, n, 13, f"=IF((F{{r}}>={T:g})=(J{{r}}>={T:g}),1,0)")
    last = n + 3
    rr = lambda c: f"Backtest_Detail!${c}$4:${c}${last}"

    for key, title in (("recent", "Results"), ("long", "Results_Long")):
        Rw = runs[key]
        a, b = Rw["test"]
        df = pd.DataFrame([result_row(m["label"], m["overall"]) for m in Rw["methods"]])
        s2 = book.create_sheet(title)
        write_table(s2, df, title=f"Every method, all categories, returns {a + 1}-{b + 1}: the {T:g}%+ call vs naive, and how well it "
                                  "ranks funds within their category" + (" (Fund-years / Right / Naive right are formulas over "
                                                                          "Backtest_Detail)" if key == "recent" else ""),
                    widths=[30, 9, 7, 8, 8, 9, 10, 9, 9, 9, 10, 11, 11, 11, 11, 11, 10, 8, 11, 11], formats=PCT | NUM)
        if key == "recent":
            for i in range(len(df)):
                r = 4 + i
                s2.cell(row=r, column=2, value=f'=COUNTIFS({rr("A")},A{r})')
                s2.cell(row=r, column=3, value=f'=SUMIFS({rr("L")},{rr("A")},A{r})')
                s2.cell(row=r, column=5, value=f'=SUMIFS({rr("M")},{rr("A")},A{r})')
        bc = [result_row(m["label"], res, {"Category": c}) for m in Rw["methods"] for c, res in m["by_cat"].items()]
        bdf = pd.DataFrame(bc)
        write_table(book.create_sheet(title + "_by_Category"), bdf,
                    title=f"Every method x category, returns {a + 1}-{b + 1}", widths=[30, 18] + [9] * 19, formats=PCT | NUM)
        yr = []
        for m in Rw["methods"]:
            for y in m["years"]:
                yr.append(result_row(m["label"], y, {"Parameter year": y["year"], "Return year": y["year"] + 1}))
        write_table(book.create_sheet(title + "_by_Year"), pd.DataFrame(yr),
                    title=f"Every method x year, returns {a + 1}-{b + 1}", widths=[30, 9, 9] + [9] * 19, formats=PCT | NUM)

    # ---- Category part check
    for key, title in (("recent", "Category_Part"), ("long", "Category_Part_Long")):
        cc = runs[key]["category_check"].copy()
        cc = pd.DataFrame({"Category": cc["category"], "Parameter year": cc["year"], "Return year": cc["year"] + 1,
                           "Predicted category excess % (past average)": cc["predicted"],
                           "Actual category excess %": cc["actual"], "Error": None, f"Predicted {T:g}%+": None,
                           f"Actual {T:g}%+": None, "Right": None})
        s3 = book.create_sheet(title)
        write_table(s3, cc, title="The category part alone: the past average vs what the category actually did that year",
                    widths=[18, 9, 9, 16, 13, 9, 10, 9, 7], formats={"Predicted category excess % (past average)": "0.00",
                                                                     "Actual category excess %": "0.00"})
        put(s3, 4, len(cc), 6, "=E{r}-D{r}", "0.00")
        put(s3, 4, len(cc), 7, f'=IF(D{{r}}>={T:g},"Yes","No")')
        put(s3, 4, len(cc), 8, f'=IF(E{{r}}>={T:g},"Yes","No")')
        put(s3, 4, len(cc), 9, "=IF(G{r}=H{r},1,0)")

    # ---- Avoid the worst
    av = []
    for key in ("recent", "long"):
        a, b = runs[key]["test"]
        for sig, x in runs[key]["avoid"].items():
            av.append({"Window": f"returns {a + 1}-{b + 1}", "Signal": labels[sig], "Bottom fifth funds": x["bot_n"],
                       "Bottom fifth below category median": ratio(x["bot_below"], x["bot_n"]),
                       "Bottom fifth avg vs category %": x["bot_rel"], "Top fifth above median": ratio(x["top_above"], x["top_n"]),
                       "Top fifth avg vs category %": x["top_rel"], "Bottom fifth: share beat 3%+": x["bot_beat"],
                       "Everyone else: share beat 3%+": x["rest_beat"], "All: share beat 3%+": x["all_beat"]})
    write_table(book.create_sheet("Avoid_Worst"), pd.DataFrame(av),
                title="Avoid the worst: do last year's bottom-fifth funds keep lagging?", widths=[18, 22, 9, 12, 12, 11, 11, 12, 12, 11],
                formats={"Bottom fifth below category median": "0.0%", "Top fifth above median": "0.0%",
                         "Bottom fifth avg vs category %": "0.00", "Top fifth avg vs category %": "0.00",
                         "Bottom fifth: share beat 3%+": "0.0%", "Everyone else: share beat 3%+": "0.0%", "All: share beat 3%+": "0.0%"})

    # ---- Fund signals (inputs)
    p = R["panel"]
    fs = p[["scheme_name", "category", "param_year", "target", "cat_mean", "rel"] + RM.FEATURES].copy()
    fs.columns = ["Fund", "Category", "Parameter year", f"Excess next year % ({ly}: {R['live_label']})", "Category average %",
                  "Vs category %"] + [labels[f] for f in RM.FEATURES]
    s4 = book.create_sheet("Fund_Signals")
    write_table(s4, fs.sort_values(["Category", "Fund", "Parameter year"]),
                title="Every fund-year: excess next year, the category average that year, the fund vs its category (formula), and each signal",
                widths=[40, 16, 9, 12, 11, 10] + [12] * len(RM.FEATURES),
                formats={c: "0.00" for c in fs.columns[3:]})
    put(s4, 4, len(fs), 6, '=IF(OR(D{r}="",E{r}=""),"",D{r}-E{r})', "0.00")

    # ---- Predictions
    pr = []
    for m in R["methods"]:
        feas_cat = {c for c, res in m["by_cat"].items() if RM.feasible(res)}
        for _, x in m["pred"].iterrows():
            pr.append({"Method": m["label"], "Fund": x["scheme_name"], "Category": x["category"],
                       "Signal": x["signal"], "Fifth in category": x["fifth"], "Category part %": x["cat_part"],
                       "Fund part %": x["rel_pred"], f"Predicted excess {ty} %": None, f"Beats Nifty by {T:g}%+?": None,
                       "Validated (method passed for this category)": "Yes" if x["category"] in feas_cat else "no",
                       f"As a return % (+ Nifty avg {nifty_avg:.2f})": None})
    pdf = pd.DataFrame(pr)
    s5 = book.create_sheet("Predictions")
    write_table(s5, pdf, title=f"Every fund x method: {ty} prediction = category part + fund part (formula). Only rows marked "
                               "Validated come from a method that passed the test for that category; the rest are shown for "
                               "reference and are not predictions to rely on.",
                widths=[28, 40, 16, 10, 8, 11, 10, 12, 10, 13, 12], formats={"Signal": "0.000", "Category part %": "0.00",
                                                                            "Fund part %": "0.00"})
    put(s5, 4, len(pdf), 8, '=IF(OR(F{r}="",G{r}=""),"",F{r}+G{r})', "0.00")
    put(s5, 4, len(pdf), 9, f'=IF(H{{r}}="","",IF(H{{r}}>={T:g},"Yes","No"))')
    put(s5, 4, len(pdf), 11, f'=IF(H{{r}}="","",H{{r}}+{nifty_avg:.4f})', "0.00")

    write_guide(book, runs, data, labels)
    for ws in book.worksheets:
        if ws.title not in ("Read_Me", "Methods") and ws.max_row > 3:
            ws.auto_filter.ref = f"A3:{get_column_letter(ws.max_column)}{ws.max_row}"
    order = ["Read_Me", "Methods", "Results", "Results_by_Category", "Results_by_Year", "Results_Long", "Results_Long_by_Category",
             "Results_Long_by_Year", "Category_Part", "Category_Part_Long", "Avoid_Worst", "Backtest_Detail", "Fund_Signals",
             "Predictions"]
    book._sheets = [book[n] for n in order]
    book.save(WORKBOOK)


def write_guide(book, runs, data, labels):
    R, L = runs["recent"], runs["long"]
    T, ly, ty = RM.TARGET, R["latest_year"], R["target_year"]
    sh = book.create_sheet("Read_Me", 0)
    sh.column_dimensions["A"].width = 30
    sh.column_dimensions["B"].width = 116
    row = [1]

    def line(k, v=None, title=False, bold=False):
        sh.cell(row=row[0], column=1, value=k).font = TITLE_FONT if title else Font(bold=True)
        if v is not None:
            c = sh.cell(row=row[0], column=2, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if bold:
                c.font = Font(bold=True)
            sh.row_dimensions[row[0]].height = max(15, 15 * (len(v) // 112 + 1))
        row[0] += 1

    line("READ ME FIRST", title=True)
    row[0] += 1
    line("What this is", "Methods from published research on predicting fund returns (momentum, low R2 / selectivity, multi-year "
                         "Alpha and Information Ratio, a combined regression), tested on our data with the same question and rule "
                         "as the Testing & prediction tab. Separate from every other tab.")
    a, b = R["test"]
    feas = [(m["label"], c) for m in R["methods"] for c, res in m["by_cat"].items() if RM.feasible(res)]
    line("The answer", ("Passed: " + "; ".join(f"{m} for {short(c)}" for m, c in feas) + ". Nothing else passes.") if feas else
         "No method passes.", bold=True)
    for m in R["methods"]:
        o = m["overall"]
        lo = [x for x in L["methods"] if x["key"] == m["key"]][0]["overall"]
        line(f"  {m['label']}", f"All funds, returns {a + 1}-{b + 1}: right {o['hits'] / o['n']:.1%} vs naive {o['naive'] / o['n']:.1%}; "
                                f"top fifth beat its category's bottom fifth by {o['spread']:+.2f} pts a year. Over returns "
                                f"{L['test'][0] + 1}-{L['test'][1] + 1}: {lo['spread']:+.2f} pts ({lo['spread_years']} of {lo['years']} years).")
    cc = R["category_check"]
    right = ((cc["predicted"] >= T) == (cc["actual"] >= T)).mean()
    line("Why the 3% call fails", f"The category part (past average) called 'category beats the Nifty by {T:g}%+' right only "
                                  f"{right:.0%} of the time in returns {a + 1}-{b + 1}, off by {(cc['predicted'] - cc['actual']).abs().mean():.1f} "
                                  "pts on average (Category_Part). Whether a fund beats the Nifty by 3% depends mostly on how its "
                                  "category and the market do that year, which no fund parameter here predicts.", bold=True)
    row[0] += 1
    line("HOW TO READ", title=True)
    row[0] += 1
    for k, v in [("Methods", "Each method in plain words, and the papers."),
                 ("Results / _by_Category / _by_Year", f"Returns {a + 1}-{b + 1}: hit ratio vs naive, precision, and within-category "
                                                        "ranking (top vs bottom fifth, rank IC). Fund-years / Right / Naive right in "
                                                        "Results are formulas counting Backtest_Detail."),
                 ("Results_Long ...", f"The same over returns {L['test'][0] + 1}-{L['test'][1] + 1} (15 years)."),
                 ("Category_Part", "The category part alone, predicted vs actual each year (formulas)."),
                 ("Avoid_Worst", "Do last year's worst fifth keep lagging?"),
                 ("Backtest_Detail", "Every backtest prediction: category part + fund part = predicted (formula); call; right; naive right."),
                 ("Fund_Signals", "Every fund-year's inputs: excess, category average, fund vs category (formula), each signal."),
                 ("Predictions", f"{ty}: every fund x method, with Validated = Yes only where the method passed for that category.")]:
        line(k, v)
    row[0] += 1
    # worked example: one prediction
    m = next((x for x in R["methods"] for c in x["by_cat"] if RM.feasible(x["by_cat"][c])), R["methods"][0])
    feas_cat = [c for c, res in m["by_cat"].items() if RM.feasible(res)]
    pr = m["pred"].dropna(subset=["pred"])
    if feas_cat:
        pr = pr[pr["category"] == feas_cat[0]]
    x = pr.sort_values("pred", ascending=False).iloc[0]
    cy = R["category_yearly"].loc[x["category"]]
    line("VERIFY BY HAND - one prediction", title=True)
    row[0] += 1
    line("Example", f"{x['scheme_name']} ({short(x['category'])}), method: {m['label']}.", bold=True)
    line("Category part", f"Category_Part / Fund_Signals: the {short(x['category'])} average excess over the Nifty 50 each year "
                          f"({len(cy)} years, parameter years {int(cy.index.min())}-{int(cy.index.max())}): "
                          + ", ".join(f"{int(y) + 1}: {v:+.1f}" for y, v in cy.items()) + f". Average = {x['cat_part']:+.2f}%.")
    if m["key"] != "ridge":
        fa = m["info"]["fifth_avg"]
        line("Fund part", f"The fund's {ly} {m['label']} = {x['signal']:.3f}, fifth {int(x['fifth'])} of 5 within {short(x['category'])} "
                          f"in {ly}. Each fifth's average return vs its category the next year, over {m['info']['years']} years "
                          f"(all categories): " + ", ".join(f"Q{int(q)}: {v:+.2f}" for q, v in fa.items())
                          + f". So the fund part = {x['rel_pred']:+.2f}%.")
    line("Prediction", f"{x['cat_part']:+.2f} + {x['rel_pred']:+.2f} = {x['cat_part'] + x['rel_pred']:+.2f}% -> "
                       f"{'beats' if x['cat_part'] + x['rel_pred'] >= T else 'does not beat'} the Nifty 50 by {T:g}%+ "
                       f"(Predictions sheet: Method = {m['label']}, Fund = {x['scheme_name']}).", bold=True)


def write_dashboard(runs, data, nifty_avg):
    R = runs["recent"]

    def r(v, n=3):
        v = clean(v)
        return None if v is None else round(float(v), n)

    def res(x):
        return None if not x else {k: (r(v, 3) if isinstance(v, float) else v) for k, v in x.items() if k != "fifth_avg"}

    members = R["panel"][R["panel"]["param_year"] == R["latest_year"]].sort_values(["category", "scheme_name"])
    fi = {sid: i for i, sid in enumerate(members["scheme_id"])}
    windows = []
    for key, _ in WINDOWS:
        Rw = runs[key]
        windows.append({"key": key, "test": list(Rw["test"]),
                        "methods": [{"key": m["key"], "overall": res(m["overall"]),
                                     "byCat": {c: res(v) for c, v in m["by_cat"].items()},
                                     "years": [res(y) | {"year": y["year"]} for y in m["years"]],
                                     "live": res(m["live"])} for m in Rw["methods"]],
                        "categoryCheck": [[c["category"], int(c["year"]), r(c["predicted"], 2), r(c["actual"], 2)]
                                          for _, c in Rw["category_check"].iterrows()],
                        "avoid": {k: res(v) for k, v in Rw["avoid"].items()}})
    preds = []
    for m in R["methods"]:
        info = m["info"] or {}
        rows = []
        for sid, x in m["pred"].set_index("scheme_id").iterrows():
            row = [fi[sid], r(x["signal"], 4), None if pd.isna(x["fifth"]) else int(x["fifth"]), r(x["rel_pred"], 5), r(x["pred"], 5)]
            if m["key"] == "ridge" and "z" in info:
                z = info["z"].loc[m["pred"].index[m["pred"]["scheme_id"] == sid][0]]
                row.append([r(v, 3) for v in z])
            rows.append(row)
        preds.append({"key": m["key"], "label": m["label"], "text": m["text"],
                      "fifthAvg": None if "fifth_avg" not in info else [r(info["fifth_avg"].get(q), 3) for q in range(1, 6)],
                      "fifthYears": info.get("years"), "beta": None if "beta" not in info else [r(v, 4) for v in info["beta"]],
                      "rows": rows})
    cy = R["category_yearly"]
    payload = {"latestYear": R["latest_year"], "targetYear": R["target_year"], "liveLabel": R["live_label"],
               "target": RM.TARGET, "hitRatio": RM.HIT_RATIO, "minCalls": RM.MIN_CALLS, "niftyAverage": r(nifty_avg, 2),
               "niftyPartial": r(data.nifty_partial, 2), "features": RM.FEATURES, "categories": R["categories"],
               "categoryYearly": {c: [[int(y), r(v, 2)] for y, v in cy.loc[c].items()] for c in R["categories"]},
               "references": [{"title": t, "url": u} for t, u in REFERENCES],
               "windows": windows, "methods": preds,
               "funds": [{"id": x.scheme_id, "name": x.scheme_name, "category": x.category, "live": r(x.target, 2)}
                         for x in members.itertuples()]}
    DATA.write_text("window.RESEARCH = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=clean) + ";\n")


def main():
    data = S.load()
    runs = {key: RM.run(data, first) for key, first in WINDOWS}
    years = [y + 1 for y in data.full_years]
    nifty_avg = float(data.nifty.reindex(years).mean())
    write_workbook(runs, data, nifty_avg)
    write_dashboard(runs, data, nifty_avg)
    for m in runs["recent"]["methods"]:
        print(f"{m['label']:32} passed for: {[c for c, x in m['by_cat'].items() if RM.feasible(x)]}")


if __name__ == "__main__":
    main()
