"""Write the year-wise summary workbook and reconcile it against Summary.xlsx.

    python build_summary.py
    python build_summary.py --fund-list "Correlation working - 2005.xlsx"   # refresh groups
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    SUMMARY_EXACT_GROUPS, SUMMARY_FUND_CATEGORIES, SUMMARY_OUTPUT, SUMMARY_PARAMETER_SHEET,
    SUMMARY_EXCLUSION_SHEETS, SUMMARY_REFERENCE, SUMMARY_RETURN_SHEET, SUMMARY_WINDOWS,
    SUMMARY_WINDOWS_OUTPUT, SUMMARY_WORKBOOK, SUMMARY_EX_SECTOR_OUTPUT, SUMMARY_EX_SECTOR_SHEETS,
    UPDATED_FUND_LIST, UPDATED_OUTPUT, UPDATED_PARAMETER_SHEET, UPDATED_RETURN_SHEET,
    UPDATED_SHEETS, UPDATED_WORKBOOK, DEC25_OUTPUT, DEC25_WORKBOOK, SEPT26_OUTPUT,
    SEPT26_RETURN_SHEET, SEPT26_WORKBOOK, RECENT_OUTPUT, RECENT_SHEETS, LATEST_OUTPUT,
    LATEST_SHEETS, WINDOW_2018_22_OUTPUT, WINDOW_2018_22_SHEETS,
)
from src.yearwise_summary import (
    build_all_years, build_exclusions, build_summary_workbook, extract_fund_categories,
    load_all_funds_members, load_fund_categories, load_fund_list_workbook,
    build_excluded_windows, build_window_workbook, build_windows, load_yearwise_data,
    calendar_period, october_september_period,
    read_reference, reconcile,
    summary_notes, window_notes,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fund-list", type=Path,
                        help="working file whose 'Fund list' sheet defines the fund groups")
    args = parser.parse_args()
    if args.fund_list:
        print(f"Reading the fund list from {args.fund_list.name} (large file, takes a while) ...")
        saved = extract_fund_categories(args.fund_list, SUMMARY_FUND_CATEGORIES)
        print(f"Saved {len(saved)} funds to {SUMMARY_FUND_CATEGORIES.relative_to(Path.cwd())}")

    categories = load_fund_categories(SUMMARY_FUND_CATEGORIES)
    if not categories:
        print(f"No fund list at {SUMMARY_FUND_CATEGORIES}; run with --fund-list first.")
        return 1
    print(f"Reading {SUMMARY_WORKBOOK.name} ...")
    forward, parameters = load_yearwise_data(
        SUMMARY_WORKBOOK, SUMMARY_PARAMETER_SHEET, SUMMARY_RETURN_SHEET, categories,
        load_all_funds_members(SUMMARY_FUND_CATEGORIES))
    unclassified = forward.loc[forward["fund_class"] == "Unclassified", "scheme_name"].unique()
    if len(unclassified):
        print(f"WARNING: {len(unclassified)} fund(s) are not in the fund list and appear only "
              f"in All Funds: {', '.join(unclassified)}")
    all_years = build_all_years(forward, parameters)
    exclusions = build_exclusions(forward, parameters, SUMMARY_EXCLUSION_SHEETS)
    notes = summary_notes(list(all_years), exact_groups=SUMMARY_EXACT_GROUPS)
    notes += [(f"Sheet {name}", f"As sheet {start}, with every {', '.join(excluded)} fund removed "
                                f"from all groups, All Funds included")
              for name, (start, excluded, _, _) in exclusions.items()]
    SUMMARY_OUTPUT.write_bytes(build_summary_workbook(all_years, notes, exclusions))
    print(f"Wrote {SUMMARY_OUTPUT.name}: {len(all_years)} year sheets "
          f"({min(all_years)}-{max(all_years)}) + {', '.join(exclusions) or 'no extra sheets'}, "
          f"{len(parameters)} parameters, {forward['scheme_id'].nunique()} funds")

    windows = build_windows(forward, parameters, SUMMARY_WINDOWS)
    SUMMARY_WINDOWS_OUTPUT.write_bytes(build_window_workbook(
        windows, window_notes(windows, exact_groups=SUMMARY_EXACT_GROUPS)))
    print(f"Wrote {SUMMARY_WINDOWS_OUTPUT.name}: {', '.join(windows)}"
          )
    skipped_labels = [f"{start}-{end % 100:02d}" for start, end in SUMMARY_WINDOWS
                      if f"{start}-{end % 100:02d}" not in windows]
    if skipped_labels:
        print(f"  skipped (no parameters for the last year yet): {', '.join(skipped_labels)}")
    # A window that runs to the last parameter year is the same pool as a full sheet.
    for label, (start, end, correlations, _) in windows.items():
        if start in all_years and end == max(all_years):
            gap = (correlations - all_years[start][0]).abs().max().max()
            print(f"  check: window {label} vs year sheet {start}: max gap {gap:.1e}")

    ex_sector = build_excluded_windows(forward, parameters, SUMMARY_EX_SECTOR_SHEETS)
    ex_notes = [("Sheets", "; ".join(
        f"{name}: parameters {start}-{end} vs returns {start + 1}-{end + 1}, without "
        f"{', '.join(excluded)}" for name, start, end, excluded in SUMMARY_EX_SECTOR_SHEETS)),
        ("Exclusion", "Every fund of the excluded Final Category is removed from every column, "
                      "All Funds included; that category's own column is dropped.")]
    ex_notes += window_notes(ex_sector, exact_groups=SUMMARY_EXACT_GROUPS)[2:]
    SUMMARY_EX_SECTOR_OUTPUT.write_bytes(build_window_workbook(
        ex_sector, ex_notes, title_suffix=", excluding Sector Funds"))
    print(f"Wrote {SUMMARY_EX_SECTOR_OUTPUT.name}: {', '.join(ex_sector)}")
    for name, (_, _, correlations, _) in ex_sector.items():
        if name in exclusions:
            gap = (correlations - exclusions[name][2]).abs().max().max()
            print(f"  check: {name} vs the same sheet in {SUMMARY_OUTPUT.name}: max gap {gap:.1e}")

    for source, output in ((UPDATED_WORKBOOK, UPDATED_OUTPUT), (DEC25_WORKBOOK, DEC25_OUTPUT)):
        if source.exists():
            build_updated(parameters, source, output)
    if DEC25_WORKBOOK.exists():
        build_updated(parameters, DEC25_WORKBOOK, RECENT_OUTPUT, describe=recent_period,
                      sheet_specs=RECENT_SHEETS)
        build_updated(parameters, DEC25_WORKBOOK, LATEST_OUTPUT, describe=latest_period,
                      sheet_specs=LATEST_SHEETS)
        build_updated(parameters, DEC25_WORKBOOK, WINDOW_2018_22_OUTPUT,
                      sheet_specs=WINDOW_2018_22_SHEETS)
    if SEPT26_WORKBOOK.exists():
        build_updated(parameters, SEPT26_WORKBOOK, SEPT26_OUTPUT,
                      return_sheet=SEPT26_RETURN_SHEET, label_by="start",
                      describe=october_september_period)

    if SUMMARY_REFERENCE.exists():
        report = reconcile(all_years, read_reference(SUMMARY_REFERENCE))
        print(f"\nReconciliation against {SUMMARY_REFERENCE.name}:")
        print(report.to_string(index=False))
        exact = report[report["group"].isin(SUMMARY_EXACT_GROUPS)]
        failed = exact[(exact["max_gap"] > 1e-9) | (exact["blank_mismatch"] > 0)]
        if not failed.empty:
            print("\nFAIL: a column expected to match exactly does not.")
            return 1
        print("\nOK: every exact-match column reproduces the reference.")
    return 0


def recent_period(start, end):
    return (f"Parameter year {start} (Jan-Dec {start}) vs the 9-month return Jan-Sep {start + 1} "
            "(cumulative, not annualised)")


def latest_period(start, end):
    """Calendar windows whose last parameter year (2025) has only a 9-month return."""
    text = calendar_period(start, end)
    if end < 2025:
        return text
    return (f"Parameter years {start}-{end} vs next-year return ({start + 1}-{end}, then "
            f"Jan-Sep {end + 1} (9 months, cumulative) for parameter year {end})")


def build_updated(expected_parameters, source, output, return_sheet=UPDATED_RETURN_SHEET,
                  label_by="end", describe=calendar_period, sheet_specs=UPDATED_SHEETS):
    """The UPDATED_SHEETS workbook from a parameter export with the updated layout,
    restricted to the funds of UPDATED_FUND_LIST."""
    print(f"\nReading {source.name} with the funds of {UPDATED_FUND_LIST.name} ...")
    classes = load_fund_list_workbook(UPDATED_FUND_LIST)
    forward, parameters = load_yearwise_data(
        source, UPDATED_PARAMETER_SHEET, return_sheet, classes, label_by=label_by)
    renamed = [(old, new) for old, new in zip(expected_parameters, parameters) if old != new]
    if len(parameters) != len(expected_parameters) or len(renamed) > 3:
        print("WARNING: the parameter list differs from the original one.")
    elif renamed:
        print(f"Note: {len(renamed)} parameter label(s) differ from the original file: "
              + "; ".join(f"'{new}' (was '{old}')" for old, new in renamed))
    outside = forward.loc[forward["fund_class"] == "Unclassified", "scheme_id"].nunique()
    forward = forward[forward["fund_class"] != "Unclassified"].reset_index(drop=True)
    sheets = build_excluded_windows(forward, parameters, sheet_specs)
    notes = [("Source", f"{source.name}: sheets '{UPDATED_PARAMETER_SHEET}' and "
                        f"'{return_sheet}'"),
             ("Funds", f"Only the {len(classes)} funds of {UPDATED_FUND_LIST.name}, grouped by its "
                       f"Final Category; {forward['scheme_id'].nunique()} of them have paired data. "
                       f"{outside} funds in the export but not in the list are left out."),
             ("Sheets", "; ".join(
                 f"{name}: {describe(start, end)}"
                 + (f", without {', '.join(excluded)}" if excluded else "")
                 for name, start, end, excluded in sheet_specs)),
             ("All Funds", "Every listed fund (the 18 UTI/WhiteOak funds included); "
                           "'ex Sector' sheets remove every Sector fund from all columns.")]
    notes += window_notes(sheets)[2:]
    titles = {name: f", excluding {', '.join(excluded)}"
              for name, _, _, excluded in sheet_specs if excluded}
    output.write_bytes(build_window_workbook(sheets, notes, titles, describe))
    counts = forward.drop_duplicates("scheme_id")["fund_class"].value_counts()
    print(f"Wrote {output.name}: {', '.join(sheets)} ({forward['scheme_id'].nunique()} "
          f"funds with data, Sector Funds {counts.get('Sector Funds', 0)}; "
          f"{outside} export funds not in {UPDATED_FUND_LIST.name} left out)")


if __name__ == "__main__":
    sys.exit(main())
