"""Category / all-funds version of the fund analysis.

    python build_category.py

Outputs:
    Category_Analysis.xlsx     the working: expected excess per group, calculation, fund estimates
    dashboard/category.js      data for the dashboard's Category analysis tab
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

import category_analysis as C
import study as S
from build import TITLE_FONT, clean, write_table

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Category_Analysis.xlsx"
DATA = HERE / "dashboard" / "category.js"
THR = C.MIN_CORRELATION
NAMES = ["Low", "Middle", "High"]


def ratio(a, b):
    return a / b if b else np.nan


def write_workbook(R, params):
    ly, ty = R["latest_year"], R["target_year"]
    book = Workbook()
    sheet = book.active
    sheet.title = "Method"
    lines = [
        ("Parameters vs excess return over the Nifty 50: categories and all funds", None),
        ("Period", f"Expected excess return over the Nifty 50 for calendar {ty} (1 Jan - 31 Dec {ty}), from {ly} parameters."),
        ("Data", "Every fund-year of the group pooled (funds with a short history count with the years they have): "
                 "the parameter in year T and the fund's excess return over the Nifty 50 in T+1."),
        ("Step 1", "Spearman correlation of the parameter with next-year excess across the group's fund-years, and its p-value."),
        ("Step 2", "The group's values split into 3 equal-count ranges (low / middle / high); average next-year excess in each."),
        ("Step 3", f"Used if p < {C.MAX_P:g} and |correlation| >= {THR:g} (sheet defaults; the dashboard can change the "
                   f"cut-off). Near-duplicates (|rank correlation| > {C.DUPLICATE_RHO:g} across the group) count once."),
        ("Step 4", "Weight = |correlation| / sum of |correlation| of the parameters used. Expected excess = sum of "
                   "weight x the average next-year excess of the range the value falls in."),
        ("Typical fund", f"The group's median {ly} value of each parameter. Each fund's own estimate uses its own {ly} "
                         "values (weights re-scaled over the parameters it has)."),
    ]
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 120
    for i, (k, v) in enumerate(lines, 1):
        sheet.cell(row=i, column=1, value=k).font = TITLE_FONT if v is None else Font(bold=True)
        if v:
            sheet.cell(row=i, column=2, value=v).alignment = Alignment(wrap_text=True, vertical="top")
            sheet.row_dimensions[i].height = 34

    summary, calc, funds, allp = [], [], [], []
    for g in R["groups"]:
        f, w = g["fitted"], C.chosen(g["fitted"], THR)
        exp, n = C.expected(f, w, g["typical"])
        est = []
        all_fit = R["groups"][0]["fitted"]
        all_w = C.chosen(all_fit, THR)
        for _, row in g["members"].iterrows():
            e, k = C.expected(f, w, {p: row[p] for p in w})
            est.append(e)
            if g["name"] != C.ALL:
                ea, _ = C.expected(all_fit, all_w, {p: row[p] for p in all_w})
                funds.append({"Fund": row["scheme_name"], "Category": g["name"], f"Expected excess {ty} % (category model)": e,
                              "Parameters available": k, f"Expected excess {ty} % (all-funds model)": ea})
        est = np.array(est, dtype=float)
        summary.append({"Group": g["name"], "Funds": g["funds"], "Fund-years": g["obs"], "Years": f"{g['first']}-{g['last']}",
                        "Avg excess so far %": g["avg_excess"], "Parameters used": n,
                        f"Expected excess {ty} %, typical fund": exp,
                        f"Funds with {ly} data": int(np.isfinite(est).sum()),
                        "Avg of fund estimates %": np.nanmean(est) if np.isfinite(est).any() else np.nan,
                        "Funds expected to beat Nifty by 3%+": int((est >= 3).sum())})
        for p, wt in w.items():
            ex, idx, outside = C.range_excess(f[p], g["typical"][p])
            if idx is None:
                continue
            r = f[p]["ranges"][idx]
            calc.append({"Group": g["name"], "Parameter": p, "Correlation": f[p]["rho"], "p-value": f[p]["p"], "Weight": wt,
                         f"Typical {ly} value": g["typical"][p], "Range": NAMES[idx] + (" (nearest)" if outside else ""),
                         "Range from": r["low"], "Range to": r["high"], "Fund-years in range": r["n"],
                         "Avg next-year excess in range %": ex, "Contribution %": wt * ex})
        for p in params:
            x = f[p]
            row = {"Group": g["name"], "Parameter": p, "Fund-years": x["n"], "Correlation": x["rho"], "p-value": x["p"]}
            for k, nm in enumerate(NAMES):
                rg = x["ranges"][k] if x["ranges"] else None
                row[f"{nm} from"] = rg and rg["low"]
                row[f"{nm} to"] = rg and rg["high"]
                row[f"{nm} avg excess %"] = rg and rg["avg_excess"]
            allp.append(row)

    two = lambda cols: {c: "0.00" for c in cols}
    write_table(book.create_sheet("Group_Expected"), pd.DataFrame(summary),
                title=f"Expected excess over the Nifty 50 for {ty}, by group (cut-off |correlation| >= {THR:g}, p < {C.MAX_P:g})",
                widths=[20, 8, 10, 11, 12, 10, 14, 10, 14, 14],
                formats=two(["Avg excess so far %", f"Expected excess {ty} %, typical fund", "Avg of fund estimates %"]))
    write_table(book.create_sheet("Calculation"), pd.DataFrame(calc),
                title="How each group's expected excess is built (expected = sum of contributions)",
                widths=[18, 40, 11, 9, 8, 12, 14, 10, 10, 10, 14, 12],
                formats={"Correlation": "0.000", "p-value": "0.0000", "Weight": "0.0%", f"Typical {ly} value": "0.000",
                         "Range from": "0.000", "Range to": "0.000", "Avg next-year excess in range %": "0.00",
                         "Contribution %": "0.00"})
    write_table(book.create_sheet("Fund_Estimates"), pd.DataFrame(funds).sort_values(["Category", "Fund"]),
                title=f"Every fund's {ty} estimate from its {ly} values: its category's model and the all-funds model",
                widths=[44, 18, 16, 10, 16],
                formats=two([f"Expected excess {ty} % (category model)", f"Expected excess {ty} % (all-funds model)"]))
    write_table(book.create_sheet("All_Parameters"), pd.DataFrame(allp),
                title="Every group x parameter: pooled correlation with next-year excess, and the three ranges",
                widths=[18, 40, 9, 11, 9] + [10, 10, 11] * 3,
                formats={"Correlation": "0.000", "p-value": "0.0000",
                         **{f"{n} {k}": "0.000" for n in NAMES for k in ("from", "to")},
                         **{f"{n} avg excess %": "0.00" for n in NAMES}})
    book.save(WORKBOOK)


def write_dashboard(R, data):
    params = data.parameters
    pi = {p: i for i, p in enumerate(params)}

    def r(v, n=3):
        v = clean(v)
        return None if v is None else round(float(v), n)

    def ranges(x):
        return None if not x["ranges"] else [[r(g["low"], 4), r(g["high"], 4), int(g["n"]), r(g["avg_excess"], 2)]
                                             for g in x["ranges"]]

    groups = []
    for g in R["groups"]:
        groups.append({
            "name": g["name"], "funds": g["funds"], "obs": g["obs"], "first": g["first"], "last": g["last"],
            "avgExcess": r(g["avg_excess"], 2),
            "params": [[pi[p], x["n"], r(x["rho"]), r(x["p"], 5), x["cluster"], ranges(x), r(g["typical"][p], 4)]
                       for p, x in g["fitted"].items()]})
    members = R["groups"][0]["members"].sort_values(["category", "scheme_name"])
    payload = {
        "parameters": params, "latestYear": R["latest_year"], "targetYear": R["target_year"],
        "liveLabel": R["live_label"],
        "niftyAverage": r(R["nifty_average"], 2), "niftyPartial": r(data.nifty_partial, 2),
        "settings": {"maxP": C.MAX_P, "minCorrelation": C.MIN_CORRELATION, "thresholds": list(C.THRESHOLDS),
                     "duplicateRho": C.DUPLICATE_RHO, "minObs": C.MIN_OBS},
        "groups": groups,
        "funds": [{"id": row["scheme_id"], "name": row["scheme_name"], "category": row["category"],
                   "live": r(row["live_excess"], 2), "v": [r(row[p], 4) for p in params]} for _, row in members.iterrows()],
    }
    DATA.write_text("window.CATEGORY = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                                                     default=clean) + ";\n")


def main():
    data = S.load()
    R = C.run(data)
    years = [y + 1 for y in data.full_years]
    R["nifty_average"] = float(data.nifty.reindex(years).mean())
    write_workbook(R, data.parameters)
    write_dashboard(R, data)
    print(f"Wrote {WORKBOOK.name} and dashboard/{DATA.name}: {len(R['groups'])} groups")


if __name__ == "__main__":
    main()
