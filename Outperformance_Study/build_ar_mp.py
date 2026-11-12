"""AR model portfolio for the dashboard's AR MP analysis tab: dashboard/armp.js.

Reads every rebalance of the AR model portfolio (sheet "Actual dates" of Model Port data.xlsx) and maps each fund
to the study's fund names, by name or else by ISIN through Fund_Classification.xlsx. The page applies the rule:
the portfolio held at the end of March of a year (the latest rebalance on or before 31 March) is taken as held for
that whole calendar year, matching the study's calendar-year returns.
"""
import json
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
SOURCE = Path("/home/sofiyaan/Desktop/MF_AR_Workstation_New/research/datadump/Model Port data.xlsx")
SHEET = "Actual dates "
CLASSIFICATION = HERE / "Fund_Classification.xlsx"
PANEL = HERE / "dashboard" / "panel.js"
OUT = HERE / "dashboard" / "armp.js"


def main():
    text = PANEL.read_text()
    study = set(json.loads(text[text.index("{"):text.rindex("}") + 1])["funds"])
    by_isin = {r[1]: r[0] for r in list(openpyxl.load_workbook(CLASSIFICATION, read_only=True).active.iter_rows(values_only=True))[1:]}

    ports, unmatched = {}, set()
    for r in openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)[SHEET].iter_rows(values_only=True):
        name, isin, date, weight = (r[1], r[2], r[3], r[4]) if len(r) > 4 else (None,) * 4
        if not name or name == "Scheme Name" or date is None:
            continue
        name, isin = name.strip(), (isin or "").strip()
        # one rebalance date is typed as text (31/1/2017)
        key = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else "-".join(reversed([p.zfill(2) for p in str(date).split("/")]))
        fund = name if name in study else by_isin.get(isin)
        if fund is None:
            unmatched.add(name)
        ports.setdefault(key, []).append([fund, round(float(weight or 0), 4), name, isin])

    dates = sorted(ports)
    OUT.write_text("window.ARMP = " + json.dumps(
        {"source": SOURCE.name + " (sheet " + SHEET.strip() + ")",
         "portfolios": [{"date": d, "funds": ports[d]} for d in dates],
         "unmatched": sorted(unmatched)},
        ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"Wrote {OUT.relative_to(HERE)}: {len(dates)} portfolios {dates[0]} to {dates[-1]}, {len(unmatched)} unmatched funds")


if __name__ == "__main__":
    main()
