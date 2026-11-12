"""Expected next-year excess return over the Nifty 50 for each fund, from its own
parameters and excess returns.

    python build_funds.py

Outputs:
    Fund_Level_Analysis.xlsx   the working: expected returns, the calculation, the fund history
    dashboard/funds.js         data for the dashboard's Fund analysis tab
"""

import json
import warnings
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

import fund_analysis as F
import study as S
from build import TITLE_FONT, clean, write_table

warnings.filterwarnings("ignore", category=RuntimeWarning)

HERE = Path(__file__).resolve().parent
WORKBOOK = HERE / "Fund_Level_Analysis.xlsx"
DATA = HERE / "dashboard" / "funds.js"


def write_workbook(R, data):
    ly, ty = R["latest_year"], R["target_year"]
    book = Workbook()
    sheet = book.active
    sheet.title = "Method"
    lines = [
        ("Parameters vs excess return over the Nifty 50", None),
        ("Period", f"Expected excess return over the Nifty 50 for calendar year {ty} (1 Jan - 31 Dec {ty}), from "
                   f"each fund's parameters for calendar year {ly} (its latest)."),
        ("Excess return", "Fund's calendar-year return minus the Nifty 50's return in the same year (in %)."),
        ("Data", "Only the fund's own history: its parameters in each year and its excess return over the Nifty 50 "
                 "in the following year. No category or peer data."),
        ("Step 1", f"For each parameter, the correlation between the fund's value in a year and its excess return "
                   f"the next year, across its own years ({F.MIN_FUND_YEARS}+ needed)."),
        ("Step 2", f"The fund's own values of the parameter split into {F.RANGES} equal-count ranges (low / middle / "
                   "high); in each, the fund's average excess return in the following year."),
        ("Step 3", f"The fund's {ly} value is placed in its range; that range's average next-year excess is what "
                   "this parameter expects."),
        ("Step 4", f"Parameters with |correlation| >= {F.MIN_CORRELATION:g} are averaged, each weighted by "
                   f"|correlation| / sum of |correlation|. Parameters that moved together in the fund's history "
                   f"(|correlation| > {F.DUPLICATE_RHO:g}) count once."),
        ("Note", "A fund has at most ~19 years, so each range rests on ~5-6 years and the estimate reflects the "
                 "market years behind it. Treat it as an estimate from the fund's own past, not a guarantee."),
    ]
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 120
    for i, (k, v) in enumerate(lines, 1):
        sheet.cell(row=i, column=1, value=k).font = TITLE_FONT if v is None else Font(bold=True)
        if v:
            sheet.cell(row=i, column=2, value=v).alignment = Alignment(wrap_text=True, vertical="top")
            sheet.row_dimensions[i].height = 34

    s = R["summary"].sort_values(["category", "fund"])
    s = s.assign(history=s["first_year"].astype(str) + "-" + s["last_year"].astype(str))
    s = s[["fund", "category", "years", "history", "avg_excess", "parameters", "expected_excess"]]
    s.columns = ["Fund", "Category", "Years of history", "Parameter years", "Its avg excess over Nifty 50 %",
                 "Parameters used", f"Expected excess over Nifty 50 in {ty} %"]
    write_table(book.create_sheet("Expected_Excess"), s,
                title=f"Expected excess return over the Nifty 50 for calendar year {ty}, from each fund's {ly} "
                      "parameters and its own history",
                widths=[44, 18, 10, 14, 14, 10, 16],
                formats={f"Expected excess over Nifty 50 in {ty} %": "0.00", "Its avg excess over Nifty 50 %": "0.00"})

    u = R["used"].copy()
    if len(u):
        u["Range"] = u["range_low"].round(3).astype(str) + " to " + u["range_high"].round(3).astype(str)
        u = u[["fund", "category", "parameter", "current", "Range", "range_years", "range_excess", "rho",
               "weight", "contribution"]]
        u.columns = ["Fund", "Category", "Parameter", f"Value {ly}", "Its range (fund's own history)",
                     "Years in that range", "Fund's avg excess over Nifty the next year", "Correlation", "Weight",
                     "Contribution %"]
        write_table(book.create_sheet("Calculation"), u,
                    title="How each expected excess is built, parameter by parameter (expected = sum of contributions)",
                    widths=[40, 16, 40, 10, 22, 28, 16, 10, 8, 12],
                    formats={f"Value {ly}": "0.000", "Fund's avg excess over Nifty the next year": "0.00",
                             "Correlation": "0.000", "Weight": "0.0%", "Contribution %": "0.00"})

    p = data.panel[data.panel["param_year"].isin(data.full_years + [ly])].copy()
    p = p.sort_values(["category", "scheme_name", "param_year"])
    hist = p[["scheme_name", "category", "param_year", "fund_return", "nifty_return", "excess"] + data.parameters].rename(
        columns={"scheme_name": "Fund", "category": "Category", "param_year": "Parameter year",
                 "fund_return": "Fund return next year %", "nifty_return": "Nifty 50 next year %",
                 "excess": "Excess over Nifty next year"})
    write_table(book.create_sheet("Fund_History"), hist,
                title=f"Every fund's parameters by year and its return vs the Nifty 50 the following year "
                      f"({ly}: next year still open)",
                widths=[40, 16, 10, 12, 12, 12] + [12] * len(data.parameters),
                formats={"Fund return next year %": "0.00", "Nifty 50 next year %": "0.00",
                         "Excess over Nifty next year": "0.00"})

    t = R["table"][["fund", "category", "parameter", "years", "rho", "p", "current", "range", "range_low",
                    "range_high", "range_n", "range_years", "range_excess"]].copy()
    t.columns = ["Fund", "Category", "Parameter", "Years", "Correlation", "p-value", f"Value {ly}", "Range (1-3)",
                 "Range from", "Range to", "Years in range", "Which years", "Avg next-year excess in range"]
    write_table(book.create_sheet("All_Parameters"), t,
                title="Every fund x parameter: correlation with the next year's excess over the Nifty 50, and the "
                      "latest value's range",
                widths=[40, 16, 40, 7, 11, 9, 10, 9, 10, 10, 9, 28, 14],
                formats={"Correlation": "0.000", "p-value": "0.000", f"Value {ly}": "0.000", "Range from": "0.000",
                         "Range to": "0.000", "Avg next-year excess in range": "0.00"})
    book.save(WORKBOOK)


def write_dashboard(R, data):
    params = data.parameters
    pi = {p: i for i, p in enumerate(params)}

    def r(v, n=3):
        v = clean(v)
        return None if v is None else round(v, n)

    rows = {}
    for fund_id, frame in R["table"].groupby("scheme_id"):
        rows[fund_id] = [[pi[x.parameter], int(x.years), r(x.rho), r(x.p, 4), r(x.current, 4),
                          None if pd.isna(x.range) else int(x.range), r(x.range_low, 4), r(x.range_high, 4),
                          None if pd.isna(x.range_n) else int(x.range_n), r(x.range_excess, 4),
                          x.range_years if isinstance(x.range_years, str) else None, int(x.cluster)]
                         for x in frame.itertuples()]
    funds = R["summary"].sort_values(["category", "fund"])
    payload = {
        "parameters": params, "latestYear": R["latest_year"], "targetYear": R["target_year"],
        "settings": {"minFundYears": F.MIN_FUND_YEARS, "ranges": F.RANGES, "minCorrelation": F.MIN_CORRELATION,
                     "duplicateRho": F.DUPLICATE_RHO},
        "nifty": {int(y): r(v, 4) for y, v in data.nifty.items()},
        "niftyAverage": r(R["nifty_average"], 2), "niftyYears": list(R["nifty_years"]),
        "funds": [{"id": f.scheme_id, "name": f.fund, "category": f.category, "years": int(f.years),
                   "firstYear": int(f.first_year), "lastYear": int(f.last_year), "avgExcess": r(f.avg_excess, 2),
                   "rows": rows.get(f.scheme_id, [])}
                  for f in funds.itertuples()],
    }
    DATA.write_text("window.FUNDS = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                                                  default=clean) + ";\n")


def main():
    data = S.load()
    R = F.run(data)
    write_workbook(R, data)
    write_dashboard(R, data)
    s = R["summary"]
    print(f"Wrote {WORKBOOK.name} and dashboard/{DATA.name}: {len(s)} funds, "
          f"{int((s['parameters'] > 0).sum())} with an expected excess over the Nifty 50 for {R['target_year']}")


if __name__ == "__main__":
    main()
