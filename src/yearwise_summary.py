"""Year-wise summary: the `Summary.xlsx` grid, built for every start year.

Sheet "YYYY" holds, for each parameter and fund group, the Pearson correlation
between the parameter in year T and the same fund's return in year T+1, pooled
over every parameter year T from YYYY to the last one. This is exactly what the
reference `Summary.xlsx` holds for 2005 and 2018. Funds are grouped by the
"Final Category" of the working file's fund list, which reproduces every group
column to floating-point precision, All Funds included when it follows the working
file's formula range (see config.py).

The figures follow Excel's CORREL deliberately -- pairwise complete pairs, no
observation floor and no zero-to-missing restoration -- because that is what
the reference summary contains. The observation count travels with every cell
so a thin sample can be shown as such.
"""

import re
import warnings
from io import BytesIO

import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from config import SUMMARY_GROUPS

UNDEFINED = "#DIV/0!"


def _normalise_text(value):
    if pd.isna(value):
        return None
    return " ".join(str(value).replace("\n", " ").split()).strip()


def _year(value):
    if pd.isna(value):
        return None
    if hasattr(value, "year"):
        return int(value.year)
    match = re.search(r"(\d{4})\s*$", str(value).strip())
    return int(match.group(1)) if match else None


def _header_cell(raw):
    """(row, column) of the 'Group/Investment' header; exports may start in A or B."""
    for row_number in range(min(len(raw), 40)):
        for column in range(min(raw.shape[1], 5)):
            if _normalise_text(raw.iat[row_number, column]) == "Group/Investment":
                return row_number, column
    raise ValueError("No 'Group/Investment' header row found")


def _fund_rows(raw, header_row, name_column):
    """Yield (row, scheme_id, scheme_name, category) for every fund row.

    Category headings are rows with a name, no ISIN and no data; funds follow
    them. A named row with data but no ISIN (a benchmark index) is skipped.
    """
    category = "Unclassified"
    for row_number in range(header_row + 1, len(raw)):
        name = raw.iat[row_number, name_column]
        identifier = raw.iat[row_number, name_column + 1]
        if pd.notna(identifier):
            yield row_number, str(identifier).strip(), _normalise_text(name), category
        elif pd.notna(name) and raw.iloc[row_number, name_column + 2:].isna().all():
            category = _normalise_text(name) or category


def _read_parameters(workbook, sheet, label_by="end"):
    raw = pd.read_excel(workbook, sheet_name=sheet, header=None)
    header, name_column = _header_cell(raw)
    period_row = header - 1  # period end dates, one per year block
    label_row = header - 2 if label_by == "start" else period_row
    starts = [column for column in range(name_column + 2, raw.shape[1])
              if _year(raw.iat[period_row, column]) is not None]
    blocks = []
    for index, start in enumerate(starts):
        stop = starts[index + 1] if index + 1 < len(starts) else raw.shape[1]
        columns = {column: _normalise_text(raw.iat[header, column])
                   for column in range(start, stop) if pd.notna(raw.iat[header, column])}
        blocks.append((_year(raw.iat[label_row, start]), columns))

    names = []
    for _, columns in blocks:
        names.extend(name for name in columns.values() if name not in names)

    records = []
    for row_number, key, scheme_name, category in _fund_rows(raw, header, name_column):
        for year, columns in blocks:
            record = {"scheme_id": key, "scheme_name": scheme_name,
                      "category": category, "year": year}
            for column, name in columns.items():
                record[name] = raw.iat[row_number, column]
            records.append(record)
    frame = pd.DataFrame(records)
    for name in names:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame.drop_duplicates(["scheme_id", "year"], keep="first"), names


def _read_returns(workbook, sheet, label_by="end"):
    raw = pd.read_excel(workbook, sheet_name=sheet, header=None)
    header, name_column = _header_cell(raw)
    label_row = header - 2 if label_by == "start" else header - 1
    years = {column: _year(raw.iat[label_row, column])
             for column in range(name_column + 2, raw.shape[1])
             if _year(raw.iat[header - 1, column]) is not None}
    years = {column: year for column, year in years.items() if year is not None}
    records = [{"scheme_id": key, "year": year, "return": raw.iat[row_number, column]}
               for row_number, key, _, _ in _fund_rows(raw, header, name_column)
               for column, year in years.items()]
    frame = pd.DataFrame(records)
    frame["return"] = pd.to_numeric(frame["return"], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame.drop_duplicates(["scheme_id", "year"], keep="first")


def _all_funds_formula_rows(book, sheet="All Funds- 2005", first_row=12, column=26):
    """Rows of the working file's All Funds sheet whose parameter formulas exist.

    The sheet lists the fund list in order from `first_row`, but its parameter
    formulas (column Z onward) were filled down only part of the way. A fund
    below the last formula row has returns and no parameters, so CORREL never
    pairs it: it is effectively outside All Funds.
    """
    filled = 0
    for (value,) in book[sheet].iter_rows(min_row=first_row, min_col=column, max_col=column,
                                          values_only=True):
        if value is None:
            break
        filled += 1
    return filled


def extract_fund_categories(working_workbook, destination):
    """Save ISIN, scheme name, Final Category and All Funds membership.

    Reads the cached values of the 'Fund list' columns J (ISIN), K (scheme name
    as in the Morningstar export) and L (Final Category) -- the columns the
    working file's FILTER formulas use to build each group sheet -- and marks
    which funds fall inside the All Funds sheet's parameter-formula range.
    """
    book = load_workbook(working_workbook, read_only=True, data_only=True)
    records, position = [], 0
    for row in book["Fund list"].iter_rows(min_row=4, min_col=10, max_col=12, values_only=True):
        isin, name, category = row
        if not name:
            continue
        # The All Funds sheet lists every named fund-list row, in this order.
        if isin and category:
            records.append({"isin": str(isin).strip(), "scheme_name": _normalise_text(name),
                            "final_category": _normalise_text(category), "position": position})
        position += 1
    frame = pd.DataFrame(records).drop_duplicates("isin").reset_index(drop=True)

    covered = _all_funds_formula_rows(load_workbook(working_workbook, read_only=True))
    frame["in_all_funds"] = np.where(frame.pop("position") < covered, "yes", "no")

    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False)
    return frame


def load_fund_categories(path):
    """{ISIN: Final Category} from the saved CSV, or {} when it is absent."""
    if path is None or not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str)
    return dict(zip(frame["isin"].str.strip(), frame["final_category"].str.strip()))


def _final_group(value):
    """Map a detailed Final Category ("Sector Funds - Consumption", "Value Fund",
    "Thematic Fund - MNC") to its summary group."""
    text = _normalise_text(value) or ""
    lowered = text.lower()
    if lowered.startswith("sector funds"):
        return "Sector Funds"
    if lowered.startswith("thematic fund"):
        return "Thematic Fund"
    if lowered in ("value fund", "contra"):
        return "Value and Contra"
    return text


def load_fund_list_workbook(path):
    """{ISIN: summary group} from a fund-list workbook such as Book3.xlsx.

    Finds the header row holding 'SD_Scheme ISIN' and 'Final Category' on the
    first sheet and maps each detailed Final Category to its summary group.
    """
    book = load_workbook(path, read_only=True, data_only=True)
    rows = list(book.worksheets[0].iter_rows(values_only=True))
    for index, row in enumerate(rows):
        labels = [_normalise_text(value) for value in row]
        if "SD_Scheme ISIN" in labels and "Final Category" in labels:
            isin_column = labels.index("SD_Scheme ISIN")
            group_column = labels.index("Final Category")
            break
    else:
        raise ValueError(f"No 'SD_Scheme ISIN' / 'Final Category' header in {path}")
    return {str(row[isin_column]).strip(): _final_group(row[group_column])
            for row in rows[index + 1:]
            if row[isin_column] and row[group_column]}


def load_all_funds_members(path):
    """ISINs inside the working file's All Funds formula range, or None for every fund."""
    if path is None or not path.exists():
        return None
    frame = pd.read_csv(path, dtype=str)
    if "in_all_funds" not in frame.columns:
        return None
    return set(frame.loc[frame["in_all_funds"].str.strip() == "yes", "isin"].str.strip())


def load_yearwise_data(workbook, parameter_sheet, return_sheet, fund_categories=None,
                       all_funds_members=None, label_by="end"):
    """Return (forward, parameters): fund-years with a next-year return attached.

    `fund_categories` maps ISIN to the summary's Final Category; funds it does
    not list are kept under "Unclassified". `all_funds_members` restricts the
    All Funds group to those ISINs; None puts every fund in it. `label_by`
    names each period by the year of its "end" date (calendar exports) or its
    "start" date (e.g. October-September periods named by their first year).
    """
    parameters, names = _read_parameters(workbook, parameter_sheet, label_by)
    returns = _read_returns(workbook, return_sheet, label_by)
    target = returns.rename(columns={"year": "target_year", "return": "next_year_return"})
    target["year"] = target["target_year"] - 1
    forward = parameters.merge(target, on=["scheme_id", "year"], how="left",
                               validate="one_to_one")
    forward = forward[forward["next_year_return"].notna()].reset_index(drop=True)
    forward["fund_class"] = forward["scheme_id"].map(fund_categories or {}).fillna("Unclassified")
    forward["in_all_funds"] = (True if all_funds_members is None
                               else forward["scheme_id"].isin(all_funds_members))
    return forward, names


def group_frame(forward, categories):
    if categories is None:
        return forward[forward["in_all_funds"]]
    wanted = {category.lower() for category in categories}
    return forward[forward["fund_class"].str.lower().isin(wanted)]


def summary_matrix(forward, parameters, start_year, end_year=None, groups=SUMMARY_GROUPS):
    """(correlations, observations) for one start year: parameters x groups."""
    end_year = int(forward["year"].max()) if end_year is None else end_year
    pooled = forward[forward["year"].between(start_year, end_year)]
    correlations, observations = {}, {}
    for label, categories in groups:
        scoped = group_frame(pooled, categories)
        target = scoped["next_year_return"]
        values = scoped[parameters]
        # Degenerate slices (fewer than two pairs, no variance) become NaN.
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            correlations[label] = values.corrwith(target)
        observations[label] = values.notna().mul(target.notna(), axis=0).sum()
    correlations = pd.DataFrame(correlations).reindex(parameters)
    correlations = correlations.where(np.isfinite(correlations))
    observations = pd.DataFrame(observations).reindex(parameters).astype(int)
    return correlations, observations


def build_all_years(forward, parameters, groups=SUMMARY_GROUPS):
    """{start_year: (correlations, observations)} for every parameter year."""
    years = sorted(int(year) for year in forward["year"].dropna().unique())
    end_year = years[-1]
    return {year: summary_matrix(forward, parameters, year, end_year, groups)
            for year in years}


# --- Workbook -----------------------------------------------------------------

_HEADER_FILL = PatternFill("solid", fgColor="000066")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HIGHLIGHT_FONT = Font(color="00B050", bold=True)
HIGHLIGHT_COUNT = 5


def _extremes(column, count=HIGHLIGHT_COUNT):
    """Row labels holding the `count` highest and `count` lowest defined values."""
    defined = column.dropna()
    return set(defined.nlargest(count).index) | set(defined.nsmallest(count).index)


def _write_grid(sheet, title, row_labels, column_labels, values, first_label="Parameter",
                highlight=False):
    """Summary.xlsx layout: title in B1, headers on row 3 from column B, data from row 4.

    With `highlight`, each column's top and bottom HIGHLIGHT_COUNT values are
    written in green.
    """
    marked = ({column_label: _extremes(values[column_label]) for column_label in column_labels}
              if highlight else {})
    sheet["B1"] = title
    sheet["B1"].font = Font(bold=True, size=12)
    headers = ["Sr No", first_label] + list(column_labels)
    for offset, text in enumerate(headers):
        cell = sheet.cell(row=3, column=2 + offset, value=text)
        cell.fill, cell.font, cell.border = _HEADER_FILL, _HEADER_FONT, _BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for index, label in enumerate(row_labels):
        row = 4 + index
        sheet.cell(row=row, column=2, value=index + 1).border = _BORDER
        sheet.cell(row=row, column=3, value=label).border = _BORDER
        for offset, column_label in enumerate(column_labels):
            value = values.at[label, column_label]
            cell = sheet.cell(row=row, column=4 + offset,
                              value=UNDEFINED if pd.isna(value) else float(value))
            cell.number_format = "0.00"
            cell.border = _BORDER
            cell.alignment = Alignment(horizontal="center")
            if label in marked.get(column_label, ()):
                cell.font = _HIGHLIGHT_FONT
    sheet.column_dimensions["A"].width = 2
    sheet.column_dimensions["B"].width = 6
    sheet.column_dimensions["C"].width = 48
    for offset in range(len(column_labels)):
        sheet.column_dimensions[get_column_letter(4 + offset)].width = 14
    sheet.row_dimensions[3].height = 32
    sheet.freeze_panes = "D4"


def _build_workbook(periods, overview_title, notes=None):
    """`periods`: {sheet name: (title, correlations, observations)}, in sheet order."""
    book = Workbook()
    book.remove(book.active)
    labels = None
    for name, (title, correlations, _) in periods.items():
        labels = list(correlations.index)
        _write_grid(book.create_sheet(name), title, labels, list(correlations.columns),
                    correlations, highlight=True)

    overview = pd.DataFrame({name: correlations["All Funds"]
                             for name, (_, correlations, _) in periods.items()})
    _write_grid(book.create_sheet("All Funds overview"), overview_title,
                labels, list(overview.columns), overview, highlight=True)

    counts = pd.DataFrame({name: observations["All Funds"]
                           for name, (_, _, observations) in periods.items()})
    sheet = book.create_sheet("Observations")
    _write_grid(sheet, "All Funds: paired observations behind each correlation",
                labels, list(counts.columns), counts)
    for row in sheet.iter_rows(min_row=4, min_col=4):
        for cell in row:
            cell.number_format = "#,##0"

    if notes:
        notes = list(notes) + [("Highlight", f"In every correlation column the {HIGHLIGHT_COUNT} "
                                             f"highest and {HIGHLIGHT_COUNT} lowest values are in "
                                             "green bold text.")]
        sheet = book.create_sheet("Notes")
        for row_number, (field, value) in enumerate(notes, 1):
            sheet.cell(row=row_number, column=1, value=field).font = Font(bold=True)
            sheet.cell(row=row_number, column=2, value=value).alignment = Alignment(wrap_text=True)
        sheet.column_dimensions["A"].width = 30
        sheet.column_dimensions["B"].width = 110

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _without(forward, groups, excluded):
    """Drop funds of the `excluded` Final Categories, and the groups made only of them."""
    removed = {category.lower() for category in excluded}
    kept = forward[~forward["fund_class"].str.lower().isin(removed)]
    kept_groups = [(label, categories) for label, categories in groups
                   if categories is None or not {c.lower() for c in categories} <= removed]
    return kept, kept_groups


def build_exclusions(forward, parameters, specs, groups=SUMMARY_GROUPS):
    """{sheet name: (start, excluded, correlations, observations)} per spec.

    Each spec (name, start_year, excluded_categories) drops funds of those Final
    Categories from every group, All Funds included, and drops the groups made
    only of them.
    """
    end_year = int(forward["year"].max())
    built = {}
    for name, start, excluded in specs:
        kept, kept_groups = _without(forward, groups, excluded)
        built[name] = (start, tuple(excluded),
                       *summary_matrix(kept, parameters, start, end_year, kept_groups))
    return built


def build_excluded_windows(forward, parameters, specs, groups=SUMMARY_GROUPS):
    """Windows with categories removed: {name: (start, last_year, corr, obs)}.

    Each spec is (name, start_year, last_parameter_year, excluded_categories);
    the result has the shape of `build_windows`, so `build_window_workbook`
    writes it.
    """
    built = {}
    for name, start, last_year, excluded in specs:
        kept, kept_groups = _without(forward, groups, excluded)
        built[name] = (start, last_year,
                       *summary_matrix(kept, parameters, start, last_year, kept_groups))
    return built


def build_summary_workbook(all_years, notes=None, exclusions=None):
    """Bytes of the all-years workbook: one sheet per start year, plus overviews.

    Each exclusion sheet is placed right after the year sheet it starts from.
    """
    end_year = max(all_years)
    periods = {}
    for year in sorted(all_years):
        periods[str(year)] = (f"Parameter years {year}-{end_year} vs next-year return "
                              f"({year + 1}-{end_year + 1})", *all_years[year])
        for name, (start, excluded, correlations, observations) in (exclusions or {}).items():
            if start == year:
                periods[name] = (f"Parameter years {start}-{end_year} vs next-year return "
                                 f"({start + 1}-{end_year + 1}), excluding "
                                 f"{', '.join(excluded)} from every group",
                                 correlations, observations)
    return _build_workbook(periods, f"All Funds: correlation by start year (pooled to {end_year})",
                           notes)


def window_label(start_year, last_year):
    """"2005-23": parameter years 2005-2023, so returns 2006-2024."""
    return f"{start_year}-{last_year % 100:02d}"


def build_windows(forward, parameters, windows, groups=SUMMARY_GROUPS):
    """{label: (start, last_year, correlations, observations)} for each window.

    A window (start, last_year) pools parameter years start..last_year against
    returns start+1..last_year+1. Windows the data cannot fully cover -- no
    parameters for `last_year`, or no return for the year after -- are skipped.
    """
    first_year = int(forward["year"].min())
    last_covered = int(forward["year"].max())
    built = {}
    for start, last_year in windows:
        if start < first_year or last_year > last_covered or last_year < start:
            continue
        correlations, observations = summary_matrix(forward, parameters, start, last_year, groups)
        built[window_label(start, last_year)] = (start, last_year, correlations, observations)
    return built


def calendar_period(start, end):
    return f"Parameter years {start}-{end} vs next-year return ({start + 1}-{end + 1})"


def october_september_period(start, end):
    """Periods named by their first year: 2005 = Oct 2005 - Sep 2006."""
    return (f"Parameter periods Oct {start}-Sep {start + 1} .. Oct {end}-Sep {end + 1} vs the "
            f"next 12 months' return (Oct {start + 1}-Sep {start + 2} .. "
            f"Oct {end + 1}-Sep {end + 2})")


def build_window_workbook(windows, notes=None, title_suffix="", describe=calendar_period):
    """Bytes of the windows workbook: one sheet per window, plus overviews.

    `title_suffix` is appended to every sheet title, or, as a dict, per label;
    `describe(start, end)` words the period in each title.
    """
    suffix = title_suffix if isinstance(title_suffix, dict) else {}
    common = "" if isinstance(title_suffix, dict) else title_suffix
    periods = {label: (f"{describe(start, end)}{common}{suffix.get(label, '')}",
                       correlations, observations)
               for label, (start, end, correlations, observations) in windows.items()}
    return _build_workbook(periods, f"All Funds: correlation by window{common}", notes)


def summary_notes(parameter_years, groups=SUMMARY_GROUPS, exact_groups=()):
    first, last = min(parameter_years), max(parameter_years)
    notes = [
        ("Sheet YYYY", f"Pearson correlation of each parameter in year T with the same "
                       f"fund's return in T+1, pooled over T = YYYY..{last} "
                       f"(return years YYYY+1..{last + 1})."),
        ("Years", f"Start years {first}-{last}. The {last} sheet is a single year "
                  f"({last} parameters vs {last + 1} returns)."),
        ("Method", "Excel CORREL equivalent: pairwise complete observations, no imputation, "
                   "no minimum sample. #DIV/0! means fewer than two pairs or no variance."),
        ("Sample size", "See 'Observations' for the pairs behind each All Funds figure; "
                        "a correlation from a few dozen pairs is not reliable."),
    ]
    for label, categories in groups:
        source = "every fund" if categories is None else ", ".join(categories)
        status = "  [matches Summary.xlsx exactly]" if label in exact_groups else ""
        notes.append((f"Group: {label}", f"Final Category = {source}{status}"
                      if categories else f"{source}{status}"))
    return notes


def window_notes(windows, groups=SUMMARY_GROUPS, exact_groups=()):
    """Notes for the windows workbook; group definitions shared with summary_notes."""
    spans = "; ".join(f"{label}: parameters {start}-{end}, returns {start + 1}-{end + 1}"
                      for label, (start, end, _, _) in windows.items())
    years = [start for start, _, _, _ in windows.values()]
    shared = summary_notes(years or [0], groups, exact_groups)[2:]
    return [("Sheet YYYY-ZZ", "Pearson correlation of each parameter in year T with the same "
                              "fund's return in T+1, for parameter years T = YYYY..20ZZ, so "
                              "returns YYYY+1..20ZZ+1. ZZ is the last parameter year."),
            ("Windows", spans)] + shared


# --- Reconciliation -------------------------------------------------------------

def read_reference(path):
    """{sheet_year: DataFrame parameter x group} from a Summary.xlsx-style file."""
    book = load_workbook(path, data_only=True, read_only=True)
    reference = {}
    for name in book.sheetnames:
        if not name.strip().isdigit():
            continue
        rows = list(book[name].iter_rows(min_row=3, values_only=True))
        header = [_normalise_text(value) for value in rows[0]]
        start = header.index("Parameter")
        columns = [value for value in header[start + 1:] if value]
        records = {}
        for row in rows[1:]:
            label = _normalise_text(row[start]) if len(row) > start else None
            if label:
                values = row[start + 1:start + 1 + len(columns)]
                records[label] = [value if isinstance(value, (int, float)) else np.nan
                                  for value in values]
        reference[int(name)] = pd.DataFrame.from_dict(records, orient="index", columns=columns)
    return reference


def reconcile(all_years, reference):
    """Max absolute gap per (reference sheet, group), comparing shared cells only."""
    rows = []
    for year, expected in reference.items():
        if year not in all_years:
            continue
        computed = all_years[year][0]
        for group in expected.columns:
            if group not in computed.columns:
                continue
            left = expected[group]
            right = computed[group].reindex(left.index)
            both = left.notna() & right.notna()
            mismatch_blank = int((left.isna() != right.isna()).sum())
            gap = (left[both] - right[both]).abs()
            rows.append({"sheet": year, "group": group, "cells": int(both.sum()),
                         "max_gap": float(gap.max()) if both.any() else np.nan,
                         "median_gap": float(gap.median()) if both.any() else np.nan,
                         "blank_mismatch": mismatch_blank})
    return pd.DataFrame(rows)
