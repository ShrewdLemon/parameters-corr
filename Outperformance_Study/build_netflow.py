"""Each fund's calendar-year net flow for the "With net flow in the equation" card of the Absolute and Excess tabs:
dashboard/netflow.js.

The flows are those of "FLows since 2005.xlsx" (sheet Flows: header in row 2, fund name in column B, ISIN in column C,
one column per December from Dec-2004, net flow in Rs crore = AUM Dec Y - AUM Dec Y-1 x (1 + NAV return of Y); a blank
cell = no figure), by ISIN. Only the dashboard's funds (isin.js) are kept. The page puts the flow of calendar year E on
the row with the parameters of year E, so it predicts the return of E + 1, and the latest year's flow goes with the
latest values for the next year's picks.

    python build_netflow.py "<path>/FLows since 2005.xlsx"
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
ISIN_JS = HERE / "dashboard" / "isin.js"
OUT = HERE / "dashboard" / "netflow.js"


def year_of(v):
    return v.year if isinstance(v, (datetime, date)) else None


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def read_flows(path):
    """{ isin: { year: Rs crore } } from the Flows sheet; blank cells are left out"""
    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True)["Flows"].iter_rows(values_only=True))
    ycol = {year_of(v): j for j, v in enumerate(rows[1]) if year_of(v)}
    flows = {}
    for r in rows[2:]:
        isin = str(r[2]).strip() if len(r) > 2 and r[2] else ""
        if isin.startswith("INF"):
            flows[isin] = {y: num(r[j]) for y, j in ycol.items() if j < len(r) and num(r[j]) is not None}
    return flows, sorted(ycol)


def main():
    src = Path(sys.argv[1])
    text = ISIN_JS.read_text(encoding="utf-8")
    dash = set(json.loads(text[text.index("{"):text.rindex("}") + 1]).values())
    flows, years = read_flows(src)
    payload = {"source": src.name, "unit": "Rs crore", "years": years,
               "flow": {k: {str(y): v for y, v in fy.items()} for k, fy in sorted(flows.items()) if k in dash and fy}}
    OUT.write_text("window.NETFLOW = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    n = sum(len(v) for v in payload["flow"].values())
    print(f"{OUT.name}: {len(payload['flow'])} of {len(dash)} funds in {src.name} (CY {years[0]}-{years[-1]}, {n} flows)")


if __name__ == "__main__":
    main()
