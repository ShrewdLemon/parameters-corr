"""Top 3 picks tab: can a method name next year's 3 best funds?

    python build.py              # once: the Statistical analysis cache
    python build_top3.py

Outputs (separate from every other tab):
    Top3_Picks.xlsx          the working (in-top-3 / in-top-10 / percentile are formulas)
    dashboard/top3.js        data for the dashboard's Top 3 picks tab
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
import top3 as T3
from build import CACHE, TITLE_FONT, clean, header, write_table

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Top3_Picks.xlsx"
DATA = HERE / "dashboard" / "top3.js"
KIND = {"research": "Research methods", "markov": "Markov chain", "parameter": "Testing & prediction candidate"}


def short(name):
    return name.replace(" Funds", "").replace(" Fund", "").replace("Small cap", "Small Cap")


def put(sheet, first, n, column, template, fmt=None):
    for r in range(first, first + n):
        c = sheet.cell(row=r, column=column, value=template.format(r=r))
        if fmt:
            c.number_format = fmt


def best_of(G, labels):
    rows = [(k, m["backtest"]) for k, m in G["methods"].items() if m["backtest"]]
    return sorted(rows, key=lambda x: (x[1]["luck_beat"], -x[1]["beat"]))


def write_workbook(R):
    labels, ly, ty = R["labels"], R["latest_year"], R["target_year"]
    a, b = R["test"]
    book = Workbook()
    book.calculation.fullCalcOnLoad = True

    # ---- Picks
    picks = []
    for grp, G in R["groups"].items():
        kb = {}
        for m in G["methods"].values():
            for y in m["years"]:
                kb[(grp, y["year"])] = y["k_beat"]
        for key, m in G["methods"].items():
            for r in m["picks"]:
                live = r["year"] == ly
                picks.append({"Group": grp, "Method": labels[key][1], "Type": KIND[labels[key][0]],
                              "Period": f"{ty} pick (live {R['live_label']})" if live else "backtest",
                              "Parameter year": r["year"], "Return year": r["year"] + 1, "Pick": r["pick"], "Fund": r["fund"],
                              "Score": r["score"], "Actual excess %": r["actual"], "Actual rank": r["actual_rank"], "Of funds": r["of"],
                              "In actual top 3": None, f"In actual top {T3.CLOSE}": None, "Percentile": None,
                              "Group average excess %": r["group_avg"], f"Beat Nifty by {T3.TARGET:g}%+": None,
                              f"Funds that beat {T3.TARGET:g}%+ that year": kb.get((grp, r["year"]))})
    pdf = pd.DataFrame(picks)
    sp = book.active
    sp.title = "Picks"
    write_table(sp, pdf, title="Every pick: each method's top 3 funds per year (scores use only the years before), where they "
                               "actually finished (in top 3 / top 10 / percentile = formulas)",
                widths=[18, 34, 22, 20, 9, 9, 5, 40, 9, 10, 8, 7, 9, 9, 9, 11, 10, 11],
                formats={"Score": "0.000", "Actual excess %": "0.00", "Group average excess %": "0.00"})
    n = len(pdf)
    put(sp, 4, n, 13, "=IF(K{r}<=3,1,0)")
    put(sp, 4, n, 14, f"=IF(K{{r}}<={T3.CLOSE},1,0)")
    put(sp, 4, n, 15, "=1-(K{r}-1)/(L{r}-1)", "0%")
    put(sp, 4, n, 17, f"=IF(J{{r}}>={T3.TARGET:g},1,0)")
    last = n + 3
    PR = lambda c: f"Picks!${c}$4:${c}${last}"

    # ---- Results (formulas over Picks)
    T = T3.TARGET
    res = book.create_sheet("Results", 0)
    res.cell(row=1, column=1, value=f"Results, backtest returns {a + 1}-{b + 1}: the hit = a pick beat the Nifty 50 by {T:g}%+ that year. "
                                    f"Counts are formulas over Picks; random = blind picks (the share of the group's funds that beat by {T:g}%+)").font = TITLE_FONT
    heads = ["Group", "Method", "Type", "Years", "Picks", f"Beat by {T:g}%+", "Hit ratio", "Random picks expect", "Random hit ratio",
             "Chance by luck", "Passes", "In top 3", "Random", f"In top {T3.CLOSE}", "Random", "Average percentile",
             "Picks' avg excess %", "Group avg excess %", f"Live {R['live_label']}: beat {T:g}%+", "Live picks"]
    header(res, 3, heads, [16, 34, 22, 6, 6, 8, 8, 9, 9, 9, 7, 7, 7, 7, 7, 9, 10, 10, 11, 7])
    r = 4
    for grp, G in R["groups"].items():
        nm = len([1 for m in G["methods"].values() if m["backtest"]])
        for key, bt in best_of(G, labels):
            m = G["methods"][key]
            lv = m["live"]
            k = f'{PR("A")},A{r},{PR("B")},B{r},{PR("D")},"backtest"'
            vals = [grp, labels[key][1], KIND[labels[key][0]], bt["years"], f"=COUNTIFS({k})", f"=SUMIFS({PR('Q')},{k})",
                    f"=IF(E{r}>0,F{r}/E{r},\"\")", bt["random_beat"], f"=IF(E{r}>0,H{r}/E{r},\"\")", bt["luck_beat"],
                    "Yes" if T3.passes(bt, nm) else "no", f"=SUMIFS({PR('M')},{k})", bt["random_hits"], f"=SUMIFS({PR('N')},{k})",
                    bt["random_close"], f"=AVERAGEIFS({PR('O')},{k})", f"=AVERAGEIFS({PR('J')},{k})", bt["group_avg"],
                    lv and lv["beat"], lv and lv["picks"]]
            for c, v in enumerate(vals, 1):
                cell = res.cell(row=r, column=c, value=clean(v) if not isinstance(v, str) else v)
                fmt = {7: "0%", 8: "0.0", 9: "0%", 10: "0.0000", 13: "0.0", 15: "0.0", 16: "0%", 17: "0.00", 18: "0.00"}.get(c)
                if fmt:
                    cell.number_format = fmt
            r += 1
    res.freeze_panes = "C4"
    res.auto_filter.ref = f"A3:{get_column_letter(len(heads))}{r - 1}"

    # ---- Same method in every category, pooled
    pl = []
    nm = len(R["pooled"])
    for key, x in sorted(R["pooled"].items(), key=lambda kv: kv[1]["luck_beat"]):
        pl.append({"Method": labels[key][1], "Categories": x["categories"], "Picks": x["picks"], f"Beat by {T:g}%+": x["beat"],
                   "Hit ratio": x["beat"] / x["picks"], "Random picks expect": x["random_beat"], "Random hit ratio": x["random_beat"] / x["picks"],
                   "Chance by luck": x["luck_beat"], "Bar (0.05 / methods)": 0.05 / nm,
                   "Passes": "Yes" if (x["beat"] / x["picks"] > T3.HIT_RATIO and x["beat"] > x["random_beat"] and x["luck_beat"] < 0.05 / nm) else "no"})
    write_table(book.create_sheet("All_Categories"), pd.DataFrame(pl),
                title=f"Methods that work the same way in every category: their picks in all {len(R['groups']) - 1} categories together "
                      f"(one test per method, so the luck bar is 0.05 / {nm})",
                widths=[34, 10, 7, 9, 8, 10, 9, 10, 10, 7],
                formats={"Hit ratio": "0%", "Random picks expect": "0.0", "Random hit ratio": "0%", "Chance by luck": "0.0000",
                         "Bar (0.05 / methods)": "0.0000"})

    # ---- Actual top 3 each year
    at = []
    for grp, G in R["groups"].items():
        any_m = next(iter(G["methods"].values()), None)
        if not any_m:
            continue
        for y in any_m["years"]:
            for k, (f, x) in enumerate(y["actual_top"], 1):
                at.append({"Group": grp, "Parameter year": y["year"], "Return year": y["year"] + 1,
                           "Period": "live (partial)" if y["live"] else "full year", "Rank": k, "Fund": f, "Excess %": x,
                           "Funds that year": y["of"]})
    write_table(book.create_sheet("Actual_Top3"), pd.DataFrame(at), title="The actual top 3 funds of each group each year",
                widths=[18, 9, 9, 13, 5, 40, 9, 9], formats={"Excess %": "0.00"})

    # ---- 2026 picks
    p26 = []
    for grp, G in R["groups"].items():
        for key, bt in best_of(G, labels):
            m = G["methods"][key]
            for x in [p for p in m["picks"] if p["year"] == ly]:
                p26.append({"Group": grp, "Method": labels[key][1], "Pick": x["pick"], "Fund": x["fund"], "Score": x["score"],
                            f"Backtest: picks that beat {T3.TARGET:g}%+": f"{bt['beat']} of {bt['picks']}",
                            "Backtest hit ratio": bt["beat"] / bt["picks"], "Random hit ratio": bt["random_beat"] / bt["picks"],
                            "Chance by luck": bt["luck_beat"], "Passes in this category": "Yes" if T3.passes(bt, len(best_of(G, labels))) else "no",
                            "Passes across all categories": ("Yes" if key in R["pooled"] and R["pooled"][key]["luck_beat"] < 0.05 / len(R["pooled"])
                                                             and R["pooled"][key]["beat"] / R["pooled"][key]["picks"] > T3.HIT_RATIO else "no")
                            if key in R["pooled"] else "",
                            f"Actual so far ({R['live_label']}): rank": f"{x['actual_rank']} of {x['of']}"})
    write_table(book.create_sheet(f"Picks_{ty}"), pd.DataFrame(p26),
                title=f"Every method's 3 picks for {ty} (from {ly} data), with its backtest record. Only methods whose record "
                      "is unlikely to be luck deserve weight.", widths=[18, 34, 5, 40, 9, 12, 9, 9, 9, 9, 10, 14],
                formats={"Score": "0.000", "Backtest hit ratio": "0%", "Random hit ratio": "0%", "Chance by luck": "0.000"})

    write_guide(book, R)
    order = ["Read_Me", "Results", "All_Categories", "Picks", "Actual_Top3", f"Picks_{ty}"]
    book._sheets = [book[x] for x in order]
    for ws in book.worksheets:
        if ws.title not in ("Read_Me", "Results") and ws.max_row > 3:
            ws.auto_filter.ref = f"A3:{get_column_letter(ws.max_column)}{ws.max_row}"
    book.save(WORKBOOK)


def write_guide(book, R):
    labels, ly, ty = R["labels"], R["latest_year"], R["target_year"]
    a, b = R["test"]
    sh = book.create_sheet("Read_Me", 0)
    sh.column_dimensions["A"].width = 26
    sh.column_dimensions["B"].width = 120
    row = [1]

    def line(k, v=None, title=False, bold=False):
        sh.cell(row=row[0], column=1, value=k).font = TITLE_FONT if title else Font(bold=True)
        if v is not None:
            c = sh.cell(row=row[0], column=2, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if bold:
                c.font = Font(bold=True)
            sh.row_dimensions[row[0]].height = max(15, 15 * (len(v) // 116 + 1))
        row[0] += 1

    line("READ ME FIRST", title=True)
    row[0] += 1
    T = T3.TARGET
    line("The question", f"If a method picks the 3 funds it ranks highest in a group each year, do those picks beat the Nifty 50 by "
                         f"{T:g}%+ the next year? Each method ranks the funds with data up to the end of year Y; we check the picks in "
                         f"Y+1. Backtest: returns {a + 1}-{b + 1}. Live: {ly} picks vs {R['live_label']}.")
    line("The hit ratio", f"Picks that beat the Nifty 50 by {T:g}%+ / picks. Compared with random picks: in a year when K of N funds in "
                          f"the group beat by {T:g}%+, 3 blind picks would get 3 x K / N - in strong years almost every fund beats it, so a "
                          "high hit ratio alone means little.")
    line("Chance by luck", f"The probability that blind picks would do at least as well (exact). With 9-21 methods per group one of them "
                           "looks good by chance, so a method passes only if: hit ratio > "
                           f"{T3.HIT_RATIO:.0%}, better than random, and chance by luck < 0.05 / number of methods.")
    pooled = R["pooled"]
    nm = len(pooled)
    good = [k for k, x in pooled.items() if x["luck_beat"] < 0.05 / nm and x["beat"] / x["picks"] > T3.HIT_RATIO]
    line("The answer", ("Across all categories together: " + "; ".join(
        f"{labels[k][1]} - {pooled[k]['beat']} of {pooled[k]['picks']} picks ({pooled[k]['beat'] / pooled[k]['picks']:.0%}) beat the Nifty by "
        f"{T:g}%+ vs {pooled[k]['random_beat'] / pooled[k]['picks']:.0%} for random picks, chance by luck {pooled[k]['luck_beat']:.4f}"
        for k in good) + " - passes. Within single categories nothing passes (too few picks to rule out luck); see All_Categories and Results.")
         if good else "No method passes, in single categories or across all of them.", bold=True)
    for grp, G in R["groups"].items():
        rows = best_of(G, labels)
        if not rows:
            continue
        k, bt = rows[0]
        line(f"  {short(grp)}", f"{len(rows)} methods; most convincing: {labels[k][1]} - {bt['beat']} of {bt['picks']} picks beat the Nifty "
                                f"by {T:g}%+ ({bt['beat'] / bt['picks']:.0%}) vs random {bt['random_beat'] / bt['picks']:.0%}; chance by luck "
                                f"{bt['luck_beat']:.3f} (bar {0.05 / len(rows):.4f}) -> {'passes' if T3.passes(bt, len(rows)) else 'does not pass'}. "
                                f"Rank closeness: {bt['hits']} in the top 3, average percentile {bt['pct']:.0%}.")
    row[0] += 1
    line("HOW TO READ", title=True)
    row[0] += 1
    for k, v in [("Results", "One row per group x method, most convincing first: the 3%+ hit ratio vs random and luck, plus how close the picks came in rank (formulas over Picks)."),
                 ("All_Categories", "Methods that work the same way everywhere, with their picks from every category together."),
                 ("Picks", "Every pick: the fund, its score, its actual excess and rank that year; in top 3 / top 10 / percentile are formulas."),
                 ("Actual_Top3", "Who actually finished top 3 each year."),
                 (f"Picks_{ty}", f"Each method's 3 picks for {ty}, with its backtest record.")]:
        line(k, v)
    row[0] += 1
    grp = "Flexi Cap Fund" if "Flexi Cap Fund" in R["groups"] else next(iter(R["groups"]))
    G = R["groups"][grp]
    k, bt = best_of(G, labels)[0]
    y = [x for x in G["methods"][k]["years"] if not x["live"]][-1]
    pk = [p for p in G["methods"][k]["picks"] if p["year"] == y["year"]]
    line("VERIFY BY HAND", title=True)
    row[0] += 1
    line("Example", f"{short(grp)}, {labels[k][1]}, parameter year {y['year']} -> returns {y['year'] + 1} ({y['of']} funds).", bold=True)
    line("The picks", "; ".join(f"#{p['pick']} {p['fund']} (score {p['score']:.3f}): actual excess {p['actual']:+.2f}%, rank "
                                f"{p['actual_rank']} of {p['of']}, percentile {p['pct']:.0%}" for p in pk))
    line("The actual top 3", "; ".join(f"{f} ({x:+.2f}%)" for f, x in y["actual_top"]) + f" (Actual_Top3 sheet).")
    line("That year", f"{y['beat']} of 3 picks beat the Nifty by {T3.TARGET:g}%+ ({y['k_beat']} of {y['of']} funds did, so random picks expect "
                      f"{y['random_beat']:.2f}). Rank: {y['hits']} in the top 3, {y['close']} in the top {T3.CLOSE}; percentile = 1 - (rank - 1) / (funds - 1).")


def write_dashboard(R):
    labels, ly = R["labels"], R["latest_year"]

    def r(v, n=3):
        v = clean(v)
        return None if v is None else round(float(v), n)

    def agg(x):
        return None if not x else {k: (r(v, 4) if isinstance(v, float) else v) for k, v in x.items()}

    groups = []
    for grp, G in R["groups"].items():
        methods = []
        for key, m in G["methods"].items():
            methods.append({"key": key, "kind": labels[key][0], "label": labels[key][1], "bt": agg(m["backtest"]), "live": agg(m["live"]),
                            "years": [{"year": y["year"], "of": y["of"], "hits": y["hits"], "close": y["close"], "pct": r(y["pct"]),
                                       "beat": y["beat"], "kBeat": y["k_beat"], "randomBeat": r(y["random_beat"]),
                                       "picksAvg": r(y["picks_avg"], 2), "groupAvg": r(y["group_avg"], 2),
                                       "randomHits": r(y["random_hits"]), "live": y["live"],
                                       "top": [[f, r(x, 2)] for f, x in y["actual_top"]]} for y in m["years"]],
                            "picks": [[p["year"], p["pick"], p["fund"], r(p["score"], 4), r(p["actual"], 2), p["actual_rank"], p["of"]]
                                      for p in m["picks"]]})
        groups.append({"name": grp, "nLatest": G["n_latest"], "methods": methods})
    payload = {"latestYear": ly, "targetYear": R["target_year"], "test": list(R["test"]), "liveLabel": R["live_label"],
               "picks": T3.PICKS, "close": T3.CLOSE, "target": T3.TARGET, "hitRatio": T3.HIT_RATIO, "kinds": KIND, "groups": groups,
               "pooled": [{"key": k, "label": labels[k][1], **{a: (r(v, 5) if isinstance(v, float) else v) for a, v in x.items()}}
                          for k, x in sorted(R["pooled"].items(), key=lambda kv: kv[1]["luck_beat"])]}
    DATA.write_text("window.TOP3 = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=clean) + ";\n")


def main():
    data = S.load()
    spr = SP.run(data, pickle.loads(CACHE.read_bytes())["univariate"])
    R = T3.run(data, spr)
    write_workbook(R)
    write_dashboard(R)
    for key, x in R["pooled"].items():
        print(f"all categories: {R['labels'][key][1][:32]:32} {x['beat']}/{x['picks']} vs random {x['random_beat']:.1f}, luck {x['luck_beat']:.4f}")


if __name__ == "__main__":
    main()
