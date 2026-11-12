"""The Python-built tabs again, with years and/or fund categories left out.

    python build_excluded.py years      # without return years 2008 and 2009 (parameter years 2007 and 2008)
    python build_excluded.py sector     # without Sector and Thematic funds
    python build_excluded.py both       # without either

Outputs, by variant (ex, sec, exsec):
    dashboard/<variant>/         data for the dashboard's exclude switches
    Excluded_<name>/             the same workbooks, with those funds or years left out
"""

import sys
from pathlib import Path

import study as S

EXCLUDED_RETURN_YEARS = (2008, 2009)
EXCLUDED_CATEGORIES = ("Sector Funds", "Thematic Fund")
VARIANTS = {"years": ("ex", "Excluded_2008_2009"), "sector": ("sec", "Excluded_Sector_Thematic"),
            "both": ("exsec", "Excluded_2008_2009_Sector_Thematic")}
HERE = Path(__file__).resolve().parent
_load = S.load


def loader(years, categories):
    def load(*args, **kwargs):
        data = _load(*args, **kwargs)
        if years:
            gone = [y - 1 for y in EXCLUDED_RETURN_YEARS]
            data.panel = data.panel[~data.panel["param_year"].isin(gone)].copy()
            data.full_years = [y for y in data.full_years if y not in gone]
        if categories:
            data.panel = data.panel[~data.panel["category"].isin(EXCLUDED_CATEGORIES)].copy()
        return data
    return load


def main(which):
    variant, folder = VARIANTS[which]
    out, books = HERE / "dashboard" / variant, HERE / folder
    out.mkdir(parents=True, exist_ok=True)
    books.mkdir(exist_ok=True)
    S.load = loader(which in ("years", "both"), which in ("sector", "both"))
    import build
    import build_prediction
    import build_previous
    build.CACHE = build_prediction.CACHE = build_previous.CACHE = HERE / "cache" / f"statistics_{variant}.pkl"
    build.WORKBOOK = books / build.WORKBOOK.name
    build.DASHBOARD_DATA = out / "data.js"
    build.PANEL_DATA = HERE / "cache" / f"panel_{variant}.js"    # the page filters panel.js itself
    build_prediction.WORKBOOK = books / build_prediction.WORKBOOK.name
    build_prediction.DATA = out / "prediction.js"
    build_previous.WORKBOOK = books / build_previous.WORKBOOK.name
    build_previous.DATA = out / "previous.js"
    build.main()
    build_prediction.main()
    build_previous.main()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "years")
