"""The basket of each year: dashboard/mpbasket.js, the model portfolio's funds per category year by year.

Reads the CY sheets of "Perf of all funds (version 1).xlsx" (CY 21 ... CY 26: the model portfolio held through that
calendar year, Scheme Name / ISIN / Date / Weights) and gives every holding its study category through its ISIN in
Fund_Classification.xlsx ("Study category"), falling back to the fund's name on the dashboard. The Absolute / Excess /
Walk-forward tabs' basket then takes, each year, as many funds from each category as that year's portfolio held.
Holdings in Value and Contra or Dividend Yield stay listed, but those categories are left out of the picks.

    python build_mp_basket.py ["path/to/Perf of all funds (version 1).xlsx"]
"""
import json
import re
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "Perf of all funds (version 1).xlsx"
CLASSIFICATION = HERE / "Fund_Classification.xlsx"
PANEL = HERE / "dashboard" / "panel.js"
OUT = HERE / "dashboard" / "mpbasket.js"


def load_js(path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def main():
    rows = list(openpyxl.load_workbook(CLASSIFICATION, read_only=True, data_only=True).active.iter_rows(values_only=True))
    head = rows[0]
    c_isin, c_cat = head.index("ISIN"), head.index("Study category")
    cat_of_isin = {(r[c_isin] or "").strip(): r[c_cat] for r in rows[1:] if r[c_isin] and r[c_cat]}
    P = load_js(PANEL)
    cat_of_name = {}
    for r in P["rows"]:                                   # a fund's latest category on the dashboard
        cat_of_name[P["funds"][r[2]]] = P["categories"][r[1]]

    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    years, funds, unmatched = {}, {}, []
    for ws in wb.worksheets:
        m = re.fullmatch(r"CY\s*(\d{2})", ws.title.strip())
        if not m:
            continue
        year = 2000 + int(m.group(1))
        sheet = list(ws.iter_rows(values_only=True))
        top = next(i for i, r in enumerate(sheet) if r and r[0] and str(r[0]).strip() == "Scheme Name")
        counts, held = {}, []
        for r in sheet[top + 1:]:
            if not r or not r[0]:
                continue
            name, isin = str(r[0]).strip(), (str(r[1]).strip() if r[1] else "")
            cat = cat_of_isin.get(isin) or cat_of_name.get(name)
            if not cat:
                unmatched.append(f"{year}: {name} ({isin})")
                continue
            counts[cat] = counts.get(cat, 0) + 1
            held.append([name, isin, cat, r[3] if isinstance(r[3], (int, float)) else None])
        years[str(year)] = dict(sorted(counts.items()))
        funds[str(year)] = held

    data = {"source": SOURCE.name + " (sheets CY 21 ...)", "years": dict(sorted(years.items())), "funds": dict(sorted(funds.items())), "unmatched": unmatched}
    OUT.write_text("window.MPBASKET = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    for y, c in data["years"].items():
        print(y, sum(c.values()), "funds:", ", ".join(f"{k} {v}" for k, v in c.items()))
    print("unmatched:", unmatched or "none")


if __name__ == "__main__":
    main()
