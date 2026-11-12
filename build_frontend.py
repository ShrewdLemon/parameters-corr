"""Write frontend/data.js: the fund-year data the static correlation page computes from.

    python build_frontend.py

Uses the latest parameter export (DEC25_WORKBOOK) and only the funds of
UPDATED_FUND_LIST (Book3), grouped by their Final Category -- the same data and
rules as Summary_Latest_2005-25.xlsx.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    BASE_DIR, DEC25_WORKBOOK, SUMMARY_GROUPS, UPDATED_FUND_LIST, UPDATED_PARAMETER_SHEET,
    UPDATED_RETURN_SHEET,
)
from src.yearwise_summary import load_fund_list_workbook, load_yearwise_data

OUTPUT = BASE_DIR / "frontend" / "data.js"


def _number(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def main():
    classes = load_fund_list_workbook(UPDATED_FUND_LIST)
    forward, parameters = load_yearwise_data(
        DEC25_WORKBOOK, UPDATED_PARAMETER_SHEET, UPDATED_RETURN_SHEET, classes)
    forward = forward[forward["fund_class"] != "Unclassified"]

    # Category columns in summary order; "All Funds" is every row, so it is not a category.
    groups = [label for label, categories in SUMMARY_GROUPS if categories]
    lookup = {categories[0].lower(): index
              for index, (_, categories) in enumerate(g for g in SUMMARY_GROUPS if g[1])}
    sector = groups.index("Sector Funds")

    # Each return year's period, so a partial year (e.g. Jan-Sep 2026) is labelled as such.
    raw = pd.read_excel(DEC25_WORKBOOK, sheet_name=UPDATED_RETURN_SHEET, header=None, nrows=10)
    header = next(i for i in range(len(raw))
                  if "Group/Investment" in [str(v) for v in raw.iloc[i].tolist()])
    return_labels = {}
    for column in range(raw.shape[1]):
        start, end = raw.iat[header - 2, column], raw.iat[header - 1, column]
        if pd.isna(end):
            continue
        start, end = pd.to_datetime(start, dayfirst=True), pd.to_datetime(end, dayfirst=True)
        full = start.month == 1 and start.day == 1 and end.month == 12 and end.day == 31
        return_labels[end.year] = (str(end.year) if full else
                                   f"{end.year} ({start:%b}–{end:%b})")

    rows = [
        [lookup[str(fund_class).lower()], int(year), _number(ret)]
        + [_number(value) for value in values]
        for fund_class, year, ret, *values in forward[
            ["fund_class", "year", "next_year_return"] + parameters].itertuples(index=False)
    ]

    years = sorted({row[1] for row in rows})
    data = {
        "source": DEC25_WORKBOOK.name,
        "fundList": UPDATED_FUND_LIST.name,
        "parameters": parameters,
        "groups": groups,
        "sectorGroup": sector,
        "parameterYears": years,
        "returnLabels": {str(year + 1): return_labels.get(year + 1, str(year + 1))
                         for year in years},
        "rows": rows,
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text("window.CORR_DATA = " + json.dumps(data, separators=(",", ":"),
                                                         allow_nan=False) + ";\n")
    print(f"Wrote {OUTPUT.relative_to(BASE_DIR)}: {len(rows)} fund-years, {len(parameters)} "
          f"parameters, parameter years {years[0]}-{years[-1]}, "
          f"{OUTPUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
