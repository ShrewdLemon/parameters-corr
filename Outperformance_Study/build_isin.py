"""ISIN of every fund on the dashboard: dashboard/isin.js, for the ISIN column of the iteration workbooks.

Each study fund (panel.js and latest.js) is matched to its ISIN through Fund_Classification.xlsx, as in build_amc.py.

    python build_isin.py
"""
import json
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
CLASSIFICATION = HERE / "Fund_Classification.xlsx"
SOURCES = [HERE / "dashboard" / "panel.js", HERE / "dashboard" / "latest.js"]
OUT = HERE / "dashboard" / "isin.js"


def study_funds():
    names = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        names += [f if isinstance(f, str) else f[0] for f in data["funds"]]
    return list(dict.fromkeys(names))


def main():
    isin = {r[0]: (r[1] or "").strip() for r in list(openpyxl.load_workbook(CLASSIFICATION, read_only=True).active.iter_rows(values_only=True))[1:] if r[0]}
    out, unmatched = {}, []
    for fund in study_funds():
        if isin.get(fund):
            out[fund] = isin[fund]
        else:
            unmatched.append(fund)
    OUT.write_text("window.ISIN = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"{OUT.name}: {len(out)} funds; unmatched: {len(unmatched)}")
    for f in unmatched:
        print("  no ISIN:", f)


if __name__ == "__main__":
    main()
