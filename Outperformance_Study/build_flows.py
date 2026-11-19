"""Each fund's calendar-year net flow for the Walk-forward tab's "Picks by year" download: dashboard/flows.js.

The flows are those of "Flows since 2020.xlsx" (Flows sheet: row 2 fund names, row 3 ISINs, the flow rows labelled by year
from row 20 on; AUM Dec Y - AUM Dec Y-1 x NAV Dec Y / NAV Dec Y-1), by ISIN. For the note on a blank flow, the Morningstar
figure: the sum of "Estimated Fund-level Net Flow (Monthly)" in ../Parameter_monthly_data, in Rs crore. Only the dashboard's
funds (isin.js) are kept.

    python build_flows.py "<path>/Flows since 2020.xlsx"
"""
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
MONTHLY = HERE.parent / "Parameter_monthly_data"
ISIN_JS = HERE / "dashboard" / "isin.js"
OUT = HERE / "dashboard" / "flows.js"
FLOW = "Estimated Fund-level Net Flow (Monthly)"


def month_of(v):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            d = datetime.strptime(str(v).strip(), fmt)
            return d.year, d.month
        except ValueError:
            pass
    return None


def theirs(path):
    """{ isin: { year: flow or None } } and the years the file works out"""
    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True)["Flows"].iter_rows(values_only=True))
    lab = [r[1] for r in rows]
    r_flow = {int(str(lab[i])[:4]): i for i in range(19, len(rows)) if lab[i] is not None and str(lab[i])[:4].isdigit()}
    out = {}
    for j in range(2, len(rows[1])):
        isin = rows[2][j] if j < len(rows[2]) else None
        if isin:
            out.setdefault(str(isin).strip(), {y: (rows[i][j] if j < len(rows[i]) and isinstance(rows[i][j], (int, float)) else None) for y, i in r_flow.items()})
    return out, sorted(r_flow)


def morningstar(years):
    """{ isin: { year: Rs crore } }: the monthly net flows of Parameter_monthly_data summed by calendar year"""
    flows = {}
    for f in sorted(glob.glob(str(MONTHLY / "**" / "*.xlsx"), recursive=True)):
        R = list(openpyxl.load_workbook(f, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
        hdr, r7 = R[8], R[6]
        starts = [j for j in range(2, len(r7)) if r7[j] is not None]
        blocks = []
        for k, s in enumerate(starts):
            e = starts[k + 1] if k + 1 < len(starts) else len(hdr)
            m = month_of(r7[s])
            col = next((j for j in range(s, e) if isinstance(hdr[j], str) and hdr[j].strip() == FLOW), None)
            if m and col is not None and m[0] in years:
                blocks.append((m, col))
        for r in R[9:]:
            if not blocks or not r or not r[0] or len(r) < 2 or not r[1]:
                continue
            isin = str(r[1]).strip()
            for m, col in blocks:
                v = r[col] if col < len(r) else None
                if isinstance(v, (int, float)):
                    flows.setdefault(isin, {})[m] = v / 1e7
    return {k: {y: round(sum(v for m, v in ms.items() if m[0] == y), 2) for y in years if any(m[0] == y for m in ms)} for k, ms in flows.items()}


def main():
    src = Path(sys.argv[1])
    text = ISIN_JS.read_text(encoding="utf-8")
    dash = set(json.loads(text[text.index("{"):text.rindex("}") + 1]).values())
    fl, years = theirs(src)
    ms = morningstar(set(range(min(years), max(years) + 3)))
    payload = {"source": src.name, "years": years,
               "flow": {k: v for k, v in fl.items() if k in dash},
               "ms": {k: v for k, v in ms.items() if k in dash}}
    OUT.write_text("window.FLOWS = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    n = sum(1 for v in payload["flow"].values() for x in v.values() if x is not None)
    print(f"{OUT.name}: {len(payload['flow'])} of {len(dash)} funds in {src.name} (CY {years[0]}-{years[-1]}, {n} flows); Morningstar figures for {len(payload['ms'])}")


if __name__ == "__main__":
    main()
