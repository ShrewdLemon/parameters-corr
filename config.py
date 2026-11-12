from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_WORKBOOK = BASE_DIR / "Correlation file_rishil_Maker 1.xlsx"
PARAMETER_SHEET = "Parameter data"
RETURN_SHEET = "Return data"

# A Pearson coefficient built from a handful of fund-years is noise, not signal.
# The alpha/beta family is the sparsest in this workbook, so it is the first to
# produce spurious values when the sample is allowed to get small.
MIN_OBSERVATIONS = 30

# Two-sided significance threshold applied to every reported coefficient.
SIGNIFICANCE_LEVEL = 0.05

# |Pearson - Spearman| above this means a few extreme values are driving the
# linear coefficient, so it is flagged as outlier-sensitive.
OUTLIER_GAP = 0.15

# --- Year-wise summary -------------------------------------------------------
# Sheet "YYYY" of the summary holds, for every parameter and fund group, the
# correlation between the parameter in year T and the same fund's return in
# T+1, pooled over every T from YYYY to the last parameter year.
SUMMARY_WORKBOOK = BASE_DIR / "Parameter data.xlsx"
SUMMARY_PARAMETER_SHEET = "Parameter data_Filtered"
SUMMARY_RETURN_SHEET = "Return data"
SUMMARY_REFERENCE = BASE_DIR / "Summary.xlsx"
SUMMARY_OUTPUT = BASE_DIR / "Summary_All_Years.xlsx"

# Fund classification (ISIN -> "Final Category") taken from the 'Fund list'
# sheet of the correlation working file. Refresh it with:
#   python build_summary.py --fund-list "Correlation working - 2005.xlsx"
SUMMARY_FUND_CATEGORIES = DATA_DIR / "fund_categories.csv"

# Summary columns, in order, as Final Category values (matched case-insensitively).
# None means every fund. This is how the working file builds each group sheet.
SUMMARY_GROUPS = (
    ("All Funds", None),
    ("Large Cap Fund", ("Large Cap Fund",)),
    ("Large & Mid Cap", ("Large & Mid Cap",)),
    ("Flexi Cap Fund", ("Flexi Cap Fund",)),
    ("Focused Fund", ("Focused Fund",)),
    ("Small cap Fund", ("Small cap Fund",)),
    ("Mid Cap Fund", ("Mid Cap Fund",)),
    ("Multi Cap Fund", ("Multi Cap Fund",)),
    ("Value and Contra", ("Value and Contra",)),
    ("Dividend Yield", ("Dividend Yield",)),
    ("Thematic fund", ("Thematic Fund",)),
    ("Sector Funds", ("Sector Funds",)),
)

# Columns verified to reproduce Summary.xlsx to floating-point precision.
# All Funds follows the working file's 'All Funds- 2005' sheet, whose parameter
# formulas stop at row 470: the 18 funds listed below that (UTI Large Cap ..
# WhiteOak) have returns but no parameters there, so CORREL never pairs them.
# fund_categories.csv records that range in its in_all_funds column; drop the
# column (or set every row to "yes") to put every fund in All Funds.
SUMMARY_EXACT_GROUPS = tuple(label for label, _ in SUMMARY_GROUPS)

# Naming convention for every period: "YYYY-ZZ" = parameter years YYYY..20ZZ,
# paired with returns YYYY+1..20ZZ+1. "2005-23" = parameters 2005-2023 vs
# returns 2006-2024.
#
# Fixed windows, written to their own workbook: (start, last parameter year).
# A window the data does not cover yet is skipped -- "2018-25" needs 2025
# parameters and 2026 returns, and appears once they are in Parameter data.xlsx.
SUMMARY_WINDOWS = (
    (2005, 2022), (2005, 2023), (2005, 2024),
    (2018, 2022), (2018, 2023), (2018, 2024), (2018, 2025),
)
SUMMARY_WINDOWS_OUTPUT = BASE_DIR / "Summary_Windows.xlsx"

# Extra sheets in the all-years workbook: (sheet name, start parameter year,
# Final Categories removed from every group, All Funds included).
SUMMARY_EXCLUSION_SHEETS = (
    ("2005 ex Sector", 2005, ("Sector Funds",)),
)

# Separate workbook of sector-free sheets: (sheet name, start parameter year,
# last parameter year, Final Categories removed from every group incl. All Funds).
SUMMARY_EX_SECTOR_SHEETS = (
    ("2005 ex Sector", 2005, 2024, ("Sector Funds",)),
    ("2005-23 ex Sector", 2005, 2023, ("Sector Funds",)),
)
SUMMARY_EX_SECTOR_OUTPUT = BASE_DIR / "Summary_Ex_Sector.xlsx"

# --- Updated parameter data (19-10-2026 export) ------------------------------
# Same layout as SUMMARY_WORKBOOK one column to the right, with every
# annualised parameter filled for every year. Only the funds listed in
# UPDATED_FUND_LIST are used, grouped by its Final Category (detailed labels
# such as "Sector Funds - Consumption" map to their summary group). All Funds
# here is every listed fund (no row-470 formula-range rule).
UPDATED_WORKBOOK = BASE_DIR / "Parameter data updated.xlsx"
UPDATED_PARAMETER_SHEET = "Parameter data"
UPDATED_RETURN_SHEET = "Return"
UPDATED_FUND_LIST = BASE_DIR / "Book3.xlsx"
UPDATED_OUTPUT = BASE_DIR / "Summary_Updated_Data.xlsx"
# (sheet name, start parameter year, last parameter year, categories removed).
UPDATED_SHEETS = (
    ("2005-24", 2005, 2024, ()),
    ("2005-24 ex Sector", 2005, 2024, ("Sector Funds",)),
    ("2018-24", 2018, 2024, ()),
    ("2018-24 ex Sector", 2018, 2024, ("Sector Funds",)),
    ("2005-22", 2005, 2022, ()),
    ("2005-22 ex Sector", 2005, 2022, ("Sector Funds",)),
)

# Dec 2025 export: same layout and funds (UPDATED_FUND_LIST), calendar years.
# Re-uploaded 21-10-2026 as "...Dec 25(1).xlsx" (identical data; the original
# name no longer exists). Adds calendar-2025 parameters and the Jan-Sep 2026 return.
DEC25_WORKBOOK = BASE_DIR / "Parameter data updated-Dec 25(1).xlsx"
DEC25_OUTPUT = BASE_DIR / "Summary_Dec25.xlsx"

# Sept 2026 export: October-September periods throughout, named by their first
# year (2005 = Oct 2005 - Sep 2006), so the UPDATED_SHEETS names keep their
# meaning: "2005-24" = Oct 2005 .. Sep 2025 parameters, returns to Sep 2026.
SEPT26_WORKBOOK = BASE_DIR / "Parameter data updated-Sept 26.xlsx"
SEPT26_RETURN_SHEET = "Return data"
SEPT26_OUTPUT = BASE_DIR / "Summary_Sept26.xlsx"

# Most recent cross-section from the Dec export: calendar-2025 parameters vs
# the partial-year return Jan-Sep 2026 (9 months, cumulative, not annualised).
RECENT_OUTPUT = BASE_DIR / "Summary_2025_vs_9M2026.xlsx"
RECENT_SHEETS = (
    ("2025 vs Jan-Sep 26", 2025, 2025, ()),
)

# The six iterations moved forward one year to use the latest data from
# DEC25_WORKBOOK: parameter year 2025 pairs with the 9-month Jan-Sep 2026 return.
LATEST_OUTPUT = BASE_DIR / "Summary_Latest_2005-25.xlsx"
LATEST_SHEETS = (
    ("2005-25", 2005, 2025, ()),
    ("2005-25 ex Sector", 2005, 2025, ("Sector Funds",)),
    ("2018-25", 2018, 2025, ()),
    ("2018-25 ex Sector", 2018, 2025, ("Sector Funds",)),
    ("2005-23", 2005, 2023, ()),
    ("2005-23 ex Sector", 2005, 2023, ("Sector Funds",)),
)

# Parameters 2018-2022 vs returns 2019-2023, with and without Sector funds.
WINDOW_2018_22_OUTPUT = BASE_DIR / "Summary_2018-22.xlsx"
WINDOW_2018_22_SHEETS = (
    ("2018-22", 2018, 2022, ()),
    ("2018-22 ex Sector", 2018, 2022, ("Sector Funds",)),
)
