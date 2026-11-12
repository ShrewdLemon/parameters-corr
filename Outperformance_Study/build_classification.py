"""Each fund's category from the MF Universe Shortlist workbook, matched by ISIN.

    python build_classification.py     # writes Fund_Classification.xlsx
"""

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

import study as S

HERE = Path(__file__).resolve().parent
SHORTLIST = HERE.parent / "MF Universe Shortlist FY 26-27 Maker 1.xlsx"
OUT = HERE / "Fund_Classification.xlsx"


def group(category):
    if category in ("Sector Funds", "Thematic Fund"):
        return "Sectoral" if category == "Sector Funds" else "Thematic"
    return {"Large Cap Fund": "Large", "Flexi Cap Fund": "Flexi"}.get(category, "Other diversified")


def main():
    rows = list(load_workbook(SHORTLIST, read_only=True, data_only=True)["Total 1122 schemes"].iter_rows(values_only=True, min_row=6))
    head = [str(x).strip() if x else "" for x in rows[0]]
    col = {name: head.index(name) for name in ("Scheme Name", "Category", "Sub-Category", "Scheme ISIN")}
    book = pd.DataFrame([{"ISIN": str(r[col["Scheme ISIN"]]).strip(), "Shortlist name": r[col["Scheme Name"]], "Shortlist category": r[col["Category"]],
                          "Shortlist sub-category": r[col["Sub-Category"]]} for r in rows[1:] if r[col["Scheme ISIN"]]])
    funds = S.load().panel.drop_duplicates("scheme_id")[["scheme_id", "scheme_name", "category"]].rename(
        columns={"scheme_id": "ISIN", "scheme_name": "Fund", "category": "Study category"})
    out = funds.merge(book, on="ISIN", how="left").sort_values(["Shortlist category", "Fund"])
    out["Group"] = out["Shortlist category"].map(group)
    out[["Fund", "ISIN", "Group", "Shortlist category", "Shortlist sub-category", "Study category", "Shortlist name"]].to_excel(OUT, index=False)
    print(f"Wrote {OUT.name}: {len(out)} funds,", out["Group"].value_counts().to_dict())


if __name__ == "__main__":
    main()
