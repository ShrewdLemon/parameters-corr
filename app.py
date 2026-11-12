import sys
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DEFAULT_WORKBOOK, MIN_OBSERVATIONS, OUTLIER_GAP, PARAMETER_SHEET,
    RETURN_SHEET, SIGNIFICANCE_LEVEL, SUMMARY_EXACT_GROUPS, SUMMARY_FUND_CATEGORIES, SUMMARY_GROUPS,
    SUMMARY_PARAMETER_SHEET, SUMMARY_REFERENCE, SUMMARY_RETURN_SHEET, SUMMARY_WINDOWS,
    SUMMARY_EXCLUSION_SHEETS, SUMMARY_EX_SECTOR_SHEETS, UPDATED_FUND_LIST,
    UPDATED_PARAMETER_SHEET, UPDATED_RETURN_SHEET, UPDATED_SHEETS, UPDATED_WORKBOOK,
    DEC25_WORKBOOK,
    SUMMARY_WORKBOOK,
)
from src.cleaner import clean_data
from src.correlation_engine import (
    calculate_parameter_correlations, correlations_by_group,
)
from src.exporter import build_correlation_workbook, export_filename
from src.filters import apply_filters
from src.forward_returns import build_forward_dataset
from src.loader import load_workbook_data
from src.theme import APPEARANCES, build_css
from src.yearwise_summary import (
    build_all_years, build_summary_workbook, load_all_funds_members, load_fund_categories,
    load_yearwise_data,
    read_reference, reconcile, summary_notes, build_window_workbook, build_windows, window_notes,
    build_exclusions, build_excluded_windows, load_fund_list_workbook,
)

st.set_page_config(page_title="MF Correlation Analytics", page_icon="▦", layout="wide")

st.session_state.setdefault("appearance", "Dark")
appearance = st.session_state["appearance"]
st.markdown(build_css(appearance), unsafe_allow_html=True)


@st.cache_data(show_spinner="Reading the Excel workbook...")
def prepare_dataset(workbook):
    parameters, returns = load_workbook_data(workbook)
    parameters, returns, parameter_columns = clean_data(parameters, returns)
    forward = build_forward_dataset(parameters, returns)
    detected = [column for column in parameter_columns if column in forward.columns]
    return forward, detected, parameters.shape, returns.shape


@st.cache_data(show_spinner="Computing correlations...")
def compute_rankings(workbook, from_year, to_year, scheme, category,
                     min_observations, significance_level, significant_only):
    dataset, parameter_columns, _, _ = prepare_dataset(workbook)
    filtered = apply_filters(dataset, from_year, to_year, scheme, category)
    results, excluded = calculate_parameter_correlations(
        filtered, parameter_columns, min_observations=min_observations,
        significance_level=significance_level, significant_only=significant_only)
    return results, excluded, int(filtered["scheme_id"].nunique()), int(len(filtered))


@st.cache_data(show_spinner="Building the per-category breakdown...")
def compute_by_category(workbook, from_year, to_year, parameters,
                        min_observations, significance_level):
    dataset, _, _, _ = prepare_dataset(workbook)
    scoped = apply_filters(dataset, from_year, to_year)
    frames = [correlations_by_group(scoped, parameter, "category",
                                   min_observations=min_observations,
                                   significance_level=significance_level)
              for parameter in parameters]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def render_ranking(results):
    rows = []
    for rank, item in enumerate(results.itertuples(index=False), 1):
        value = item.correlation
        polarity = "positive" if value >= 0 else "negative"
        significance = (f"<span class='pill pill-ok'>p = {item.p_value:.3f}</span>"
                        if item.significant else
                        f"<span class='pill pill-warn'>p = {item.p_value:.2f}</span>")
        robustness = ("<span class='pill pill-warn'>outlier-driven</span>"
                      if item.outlier_sensitive else
                      f"<span class='pill'>ρ {item.spearman:+.2f}</span>")
        rows.append(
            f"<tr><td class='rk'>{rank:02d}</td>"
            f"<td class='pname'>{escape(item.parameter)}</td>"
            f"<td class='cval {'up' if value >= 0 else 'down'}'>{value:+.3f}</td>"
            f"<td><div class='track'><span class='zero'></span>"
            f"<span class='fill {polarity}' style='width:{min(abs(value) * 50, 50):.1f}%'></span></div></td>"
            f"<td><span class='pill'>{item.strength}</span></td>"
            f"<td class='num'>{item.observations:,}</td>"
            f"<td>{significance}</td><td>{robustness}</td></tr>")
    return ("<table class='rank'><thead><tr><th>#</th><th>Parameter</th><th>Pearson</th>"
            "<th>Signal</th><th>Strength</th><th>N</th>"
            "<th title='Two-sided p-value'>Significance</th>"
            "<th title='Spearman rank correlation'>Robustness</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def render_omitted(excluded):
    rows = "".join(
        f"<tr><td class='pname'>{escape(item.parameter)}</td>"
        f"<td class='num'>{item.observations:,}</td>"
        f"<td class='reason'>{escape(str(item.excluded_reason))}</td></tr>"
        for item in excluded.itertuples(index=False))
    return ("<table class='rank'><thead><tr><th>Parameter</th><th>N</th>"
            f"<th>Reason omitted</th></tr></thead><tbody>{rows}</tbody></table>")


@st.cache_data(show_spinner="Reading the year-wise parameter workbook...")
def prepare_yearwise(workbook, fund_list=str(SUMMARY_FUND_CATEGORIES)):
    forward, parameters = load_yearwise_data(workbook, SUMMARY_PARAMETER_SHEET,
                                             SUMMARY_RETURN_SHEET,
                                             load_fund_categories(Path(fund_list)),
                                             load_all_funds_members(Path(fund_list)))
    return forward, parameters, build_all_years(forward, parameters)


@st.cache_data(show_spinner="Computing the exclusion sheets...")
def yearwise_exclusions(workbook):
    forward, parameters, _ = prepare_yearwise(workbook)
    return build_exclusions(forward, parameters, SUMMARY_EXCLUSION_SHEETS)


@st.cache_data(show_spinner="Building the ex-Sector workbook...")
def ex_sector_workbook(workbook):
    forward, parameters, _ = prepare_yearwise(workbook)
    sheets = build_excluded_windows(forward, parameters, SUMMARY_EX_SECTOR_SHEETS)
    notes = window_notes(sheets, exact_groups=SUMMARY_EXACT_GROUPS)
    return sheets, build_window_workbook(sheets, notes, title_suffix=", excluding Sector Funds")


@st.cache_data(show_spinner="Building the updated-data workbook...")
def updated_workbook(workbook):
    forward, parameters = load_yearwise_data(workbook, UPDATED_PARAMETER_SHEET,
                                             UPDATED_RETURN_SHEET,
                                             load_fund_list_workbook(UPDATED_FUND_LIST))
    forward = forward[forward["fund_class"] != "Unclassified"]
    sheets = build_excluded_windows(forward, parameters, UPDATED_SHEETS)
    titles = {name: f", excluding {', '.join(excluded)}"
              for name, _, _, excluded in UPDATED_SHEETS if excluded}
    return build_window_workbook(sheets, window_notes(sheets), titles)


@st.cache_data(show_spinner="Computing the fixed windows...")
def yearwise_windows(workbook):
    forward, parameters, _ = prepare_yearwise(workbook)
    return build_windows(forward, parameters, SUMMARY_WINDOWS)


@st.cache_data(show_spinner="Building the windows workbook...")
def windows_workbook(workbook):
    windows = yearwise_windows(workbook)
    return build_window_workbook(windows, window_notes(windows, exact_groups=SUMMARY_EXACT_GROUPS))


@st.cache_data(show_spinner="Building the all-years workbook...")
def yearwise_workbook(workbook):
    _, _, all_years = prepare_yearwise(workbook)
    return build_summary_workbook(
        all_years, summary_notes(list(all_years), exact_groups=SUMMARY_EXACT_GROUPS),
        yearwise_exclusions(workbook))


@st.cache_data(show_spinner=False)
def yearwise_reconciliation(workbook, reference):
    _, _, all_years = prepare_yearwise(workbook)
    return reconcile(all_years, read_reference(reference))


def render_matrix(table, observations, min_observations):
    """`table`: indexed by parameter, with "Sr No" and one column per fund group."""
    groups = [group for group, _ in SUMMARY_GROUPS if group in table.columns]
    head = "".join(f"<th>{escape(group)}</th>" for group in groups)
    rows = []
    for parameter, row in table.iterrows():
        cells = []
        for group in groups:
            value = row[group]
            count = int(observations.at[parameter, group])
            if pd.isna(value):
                cells.append(f"<td class='mv na' title='{count:,} pairs: undefined'>—</td>")
                continue
            colour = "var(--pos)" if value >= 0 else "var(--neg)"
            thin = count < min_observations
            tint = 0 if thin else min(abs(value), 1) * 55
            cells.append(
                f"<td class='mv{' thin' if thin else ''}' title='{count:,} paired observations'"
                f" style='background:color-mix(in srgb,{colour} {tint:.0f}%,transparent)'>"
                f"{value:+.2f}</td>")
        rows.append(f"<tr><td class='pname'>{int(row['Sr No'])}. {escape(parameter)}</td>"
                    f"{''.join(cells)}</tr>")
    return ("<table class='rank matrix'><thead><tr><th class='lead'>Parameter</th>"
            f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>")


@st.cache_resource
def input_stamp():
    """Server-wide record of the input files' modification times."""
    return {}


def render_yearwise():
    workbook = str(SUMMARY_WORKBOOK)
    # The caches key on file paths, so a replaced input file would keep serving
    # stale results. Clear them whenever any input's modification time changes.
    inputs = (SUMMARY_WORKBOOK, SUMMARY_FUND_CATEGORIES, UPDATED_WORKBOOK, UPDATED_FUND_LIST,
              DEC25_WORKBOOK)
    stamp = tuple(path.stat().st_mtime if path.exists() else None for path in inputs)
    seen = input_stamp()
    if seen.get("stamp") not in (None, stamp):
        st.cache_data.clear()
    seen["stamp"] = stamp
    try:
        forward, parameters, all_years = prepare_yearwise(workbook)
    except Exception as error:
        st.error(f"Could not load {SUMMARY_WORKBOOK.name}: {error}")
        return
    years = sorted(all_years)
    end_year = years[-1]
    windows = yearwise_windows(workbook)
    # Every period: (first parameter year, last parameter year, correlations, observations).
    periods = {f"Sheet {year} · returns to {end_year + 1}": (year, end_year, *all_years[year])
               for year in years}
    periods.update({f"Window {label} · returns {start + 1}–{end + 1}": (start, end, corr, obs)
                    for label, (start, end, corr, obs) in windows.items()})
    periods.update({f"Sheet {name} · returns to {end_year + 1}": (start, end_year, corr, obs)
                    for name, (start, _, corr, obs) in yearwise_exclusions(workbook).items()})
    ex_sheets, ex_bytes = ex_sector_workbook(workbook)
    periods.update({f"Sheet {name} · returns {start + 1}–{end + 1}": (start, end, corr, obs)
                    for name, (start, end, corr, obs) in ex_sheets.items()
                    if not name.startswith(f"{start} ex")})

    with st.container(border=True):
        st.markdown('<div class="kicker">Summary scope</div>', unsafe_allow_html=True)
        top = st.columns([1.9, 2, 1.8, 1.2])
        period = top[0].selectbox(
            "Period", list(periods), index=0,
            help=f"'Sheet YYYY' pools parameter years YYYY–{end_year}. 'YYYY-ZZ' pools "
                 "parameter years YYYY to 20ZZ, i.e. returns YYYY+1 to 20ZZ+1.")
        search = top[1].text_input("Search parameters", placeholder="Search parameters…")
        sort_by = top[2].selectbox("Sort by", ["Workbook order"] + [g for g, _ in SUMMARY_GROUPS],
                                   help="Sorts by the absolute correlation in the chosen group.")
        min_pairs = top[3].number_input("Shade from N ≥", min_value=2, max_value=500,
                                        value=MIN_OBSERVATIONS, step=5,
                                        help="Cells built from fewer pairs are shown faded.")

    start_year, last_year, correlations, observations = periods[period]
    pooled = forward[forward["year"].between(start_year, last_year)]
    all_funds = correlations["All Funds"].where(observations["All Funds"] >= min_pairs).dropna()
    strongest = all_funds.abs().idxmax() if not all_funds.empty else None

    tiles = [
        ("Parameter years", f"{start_year}–{last_year}", f"returns {start_year + 1}–{last_year + 1}"),
        ("Funds pooled", f"{pooled['scheme_id'].nunique():,}", f"{len(pooled):,} fund-year rows"),
        ("Parameters", f"{len(parameters):,}", f"{len(SUMMARY_GROUPS)} fund groups"),
        ("Strongest (All Funds)",
         f"{all_funds[strongest]:+.3f}" if strongest else "—", strongest or "No result"),
        ("Downloads", f"{len(years)} + {len(windows)}", "year sheets + fixed windows"),
    ]
    for column, (label, value, sub) in zip(st.columns(5), tiles):
        column.markdown(
            f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-sub">{escape(str(sub))}</div></div>', unsafe_allow_html=True)

    head, download, download_windows, download_ex, download_updated, download_dec25 = st.columns(
        [2.2, 1, 1, 1, 1, 1])
    head.markdown(
        '<div class="section-head"><div><h2>Year-wise summary</h2>'
        f"<p>Correlation of each parameter in year T with the same fund's return in T+1, "
        f"pooled over T = {start_year}–{last_year}. Same grid as <code>Summary.xlsx</code>.</p>"
        '</div></div>', unsafe_allow_html=True)
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    with download:
        st.markdown("<div style='height:2.1rem'></div>", unsafe_allow_html=True)
        st.download_button(
            "Download all years", data=yearwise_workbook(workbook),
            file_name=f"Summary_All_Years_{years[0]}-{end_year}.xlsx", mime=xlsx,
            use_container_width=True,
            help=f"One sheet per start year {years[0]}–{end_year}, in the Summary.xlsx layout.")
    with download_windows:
        st.markdown("<div style='height:2.1rem'></div>", unsafe_allow_html=True)
        st.download_button(
            "Download windows", data=windows_workbook(workbook),
            file_name="Summary_Windows.xlsx", mime=xlsx, use_container_width=True,
            help="One sheet per window: " + ", ".join(windows) + ".")
    with download_ex:
        st.markdown("<div style='height:2.1rem'></div>", unsafe_allow_html=True)
        st.download_button(
            "Download ex-Sector", data=ex_bytes, file_name="Summary_Ex_Sector.xlsx", mime=xlsx,
            use_container_width=True,
            help="Sheets without the Sector funds: " + ", ".join(ex_sheets) + ".")
    with download_updated:
        st.markdown("<div style='height:2.1rem'></div>", unsafe_allow_html=True)
        if UPDATED_WORKBOOK.exists() and UPDATED_FUND_LIST.exists():
            st.download_button(
                "Updated data", data=updated_workbook(str(UPDATED_WORKBOOK)),
                file_name="Summary_Updated_Data.xlsx", mime=xlsx, use_container_width=True,
                help=f"From {UPDATED_WORKBOOK.name}: "
                     + ", ".join(name for name, *_ in UPDATED_SHEETS) + ".")
    with download_dec25:
        st.markdown("<div style='height:2.1rem'></div>", unsafe_allow_html=True)
        if DEC25_WORKBOOK.exists() and UPDATED_FUND_LIST.exists():
            st.download_button(
                "Dec 25 data", data=updated_workbook(str(DEC25_WORKBOOK)),
                file_name="Summary_Dec25.xlsx", mime=xlsx, use_container_width=True,
                help=f"From {DEC25_WORKBOOK.name}: "
                     + ", ".join(name for name, *_ in UPDATED_SHEETS) + ".")

    table = correlations.copy()
    table.insert(0, "Sr No", range(1, len(table) + 1))
    if search:
        table = table[table.index.str.contains(search, case=False, regex=False)]
    if sort_by in table.columns:
        table = table.reindex(table[sort_by].abs().sort_values(
            ascending=False, na_position="last").index)

    st.markdown(
        '<div class="legend"><span><i style="background:var(--pos)"></i>positive</span>'
        '<span><i style="background:var(--neg)"></i>negative — shade grows with |r|</span>'
        f'<span><i style="background:var(--sunken);border:1px solid var(--line)"></i>'
        f'<em>faded</em> = fewer than {int(min_pairs)} pairs</span>'
        '<span>— = undefined (#DIV/0! in Excel)</span></div>', unsafe_allow_html=True)
    if table.empty:
        st.info("No parameter matches the search.")
    else:
        st.markdown(f'<div class="panel scroll">'
                    f'{render_matrix(table, observations, int(min_pairs))}</div>',
                    unsafe_allow_html=True)

    with st.expander("Method, fund groups and reconciliation with Summary.xlsx"):
        st.markdown(f"""
**Pairing.** Parameter year **T** is joined to the same ISIN's return in **T+1**; this period
pools T = {start_year}–{last_year} (returns {start_year + 1}–{last_year + 1}). A period *YYYY-ZZ*
names its last **parameter** year, so 2005-23 = parameters 2005–2023 against returns 2006–2024.

**Coefficient.** Excel `CORREL` equivalent — pairwise complete observations, nothing imputed,
no minimum sample. Hover any cell for the number of pairs behind it.

**Fund groups.** Each column is the funds whose *Final Category* in the working file's
fund list (`{SUMMARY_FUND_CATEGORIES.relative_to(SUMMARY_WORKBOOK.parent)}`) matches it, exactly as
the working file builds its group sheets. Every column, All Funds included, reproduces
`Summary.xlsx` to floating-point precision.

**All Funds follows the working file's formula range.** In its *All Funds- 2005* sheet the
parameter formulas stop at row 470 while the fund list runs to row 488, so the last 18 funds
(UTI Large Cap … WhiteOak) have returns but no parameters and never enter CORREL. They are left
out of All Funds here too (column `in_all_funds` of the fund-list CSV); they still count in their
own category columns.

**Source.** `{SUMMARY_WORKBOOK.name}` — sheets `{SUMMARY_PARAMETER_SHEET}` and
`{SUMMARY_RETURN_SHEET}`; {forward['scheme_id'].nunique():,} funds with at least one paired year.
""")
        for label, categories in SUMMARY_GROUPS:
            st.markdown(f"- **{label}**: {'every fund' if categories is None else ', '.join(categories)}")
        if SUMMARY_REFERENCE.exists():
            report = yearwise_reconciliation(workbook, str(SUMMARY_REFERENCE))
            if not report.empty:
                report = report.assign(match=report["group"].isin(SUMMARY_EXACT_GROUPS)
                                       .map({True: "exact", False: "best-fit"}))
                st.dataframe(report, hide_index=True, use_container_width=True,
                             column_config={"max_gap": st.column_config.NumberColumn(format="%.2e"),
                                            "median_gap": st.column_config.NumberColumn(format="%.2e")})


heading, switch = st.columns([4.6, 1])
with heading:
    st.markdown(
        '<div class="hero-line"><h1>Mutual Fund Correlation Analytics</h1>'
        '<span class="badge">Parameter T &rarr; Return T+1</span></div>',
        unsafe_allow_html=True)
with switch:
    # A plain button, not a styled radio: hiding BaseWeb's radio internals also
    # hides the real input, which leaves nothing to click.
    target = APPEARANCES[1] if appearance == APPEARANCES[0] else APPEARANCES[0]
    if st.button(f"Switch to {target}", key="appearance_switch", use_container_width=True):
        st.session_state["appearance"] = target
        st.rerun()
st.markdown(
    '<div class="hero"><p>Ranks every eligible numeric parameter by its correlation with the '
    "same scheme's return in the following year. Each coefficient carries its sample size, its "
    'two-sided p-value and a Spearman robustness check, so a figure produced by a thin or '
    'outlier-driven sample is never presented as an established result.</p></div>',
    unsafe_allow_html=True)

VIEWS = (f"Parameter ranking · {DEFAULT_WORKBOOK.name}",
         f"Year-wise summary · {SUMMARY_WORKBOOK.name}")
# Held in session state, not only in the widget: the appearance switch reruns
# the script before this selectbox renders, which discards its widget state.
st.session_state.setdefault("active_view", VIEWS[0])
view = st.columns([2.2, 3])[0].selectbox(
    "View", VIEWS, index=VIEWS.index(st.session_state["active_view"]))
st.session_state["active_view"] = view
if view == VIEWS[1]:
    render_yearwise()
    st.stop()

try:
    dataset, parameter_columns, parameter_shape, return_shape = prepare_dataset(str(DEFAULT_WORKBOOK))
except Exception as error:
    st.error(f"Could not load the workbook: {error}")
    st.stop()

if dataset.empty:
    st.warning("No scheme-year observation has a valid next-year return.")
    st.stop()

years = sorted(dataset["year"].dropna().astype(int).unique())

with st.container(border=True):
    st.markdown('<div class="kicker">Analysis scope</div>', unsafe_allow_html=True)
    top = st.columns([1, 1, 2.6, 2.1])
    from_year = top[0].selectbox("From year (T)", years, index=0)
    to_year = top[1].selectbox("To year (T)", years, index=len(years) - 1)
    scheme_options = ["All Funds"] + sorted(dataset["scheme_name"].dropna().unique().tolist())
    scheme = top[2].selectbox("Fund / Scheme", scheme_options)
    category_options = ["All Categories"] + sorted(dataset["category"].dropna().unique().tolist())
    category = top[3].selectbox("Category", category_options, disabled=scheme != "All Funds")

    bottom = st.columns([1.5, 1.5, 2.4])
    min_observations = bottom[0].number_input(
        "Minimum observations", min_value=10, max_value=500, value=MIN_OBSERVATIONS, step=5,
        help="Pearson correlations built from a small sample are unstable. The alpha and beta "
             "family is the sparsest in this workbook, so it is the first to produce spurious "
             "values when this floor is set too low.")
    significance_level = bottom[1].selectbox(
        "Significance level", [0.01, 0.05, 0.10],
        index=[0.01, 0.05, 0.10].index(SIGNIFICANCE_LEVEL),
        format_func=lambda value: f"p ≤ {value:g}")
    significant_only = bottom[2].checkbox(
        "Show statistically significant parameters only", value=False,
        help="Hides coefficients whose p-value does not clear the significance level.")

if from_year > to_year:
    st.error("**From year** must be less than or equal to **To year**.")
    st.stop()

results, excluded, fund_count, observation_count = compute_rankings(
    str(DEFAULT_WORKBOOK), from_year, to_year, scheme, category,
    int(min_observations), float(significance_level), bool(significant_only))

significant_count = int(results["significant"].sum()) if not results.empty else 0
flagged_count = int(results["outlier_sensitive"].sum()) if not results.empty else 0
strongest = results.iloc[0] if not results.empty else None
return_span = f"{from_year + 1}–{to_year + 1}"

tiles = [
    ("Funds analysed", f"{fund_count:,}", f"{observation_count:,} fund-year rows"),
    ("Parameters reported", f"{len(results):,}", f"{len(excluded):,} omitted as unreliable"),
    ("Statistically significant", f"{significant_count:,}", f"at p ≤ {significance_level:g}"),
    ("Strongest correlation",
     f"{strongest['correlation']:+.3f}" if strongest is not None else "—",
     strongest["parameter"] if strongest is not None else "No result"),
    ("Return years covered", return_span, f"parameter years {from_year}–{to_year}"),
]
for column, (label, value, sub) in zip(st.columns(5), tiles):
    column.markdown(
        f'<div class="kpi"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{escape(str(sub))}</div></div>', unsafe_allow_html=True)

if flagged_count or (not results.empty and significant_count < len(results)):
    parts = []
    if significant_count < len(results):
        parts.append(f"<b>{len(results) - significant_count}</b> reported coefficient(s) "
                     f"are not significant at p ≤ {significance_level:g}")
    if flagged_count:
        parts.append(f"<b>{flagged_count}</b> are outlier-driven "
                     f"(|Pearson − Spearman| ≥ {OUTLIER_GAP})")
    st.markdown(f'<div class="callout">Read with care: {" and ".join(parts)}. '
                'Treat these as unconfirmed rather than as findings.</div>',
                unsafe_allow_html=True)

st.markdown(
    '<div class="section-head"><div><h2>Parameter ranking</h2>'
    "<p>Ranked by the absolute strength of the correlation with the same scheme's "
    'next-year return</p></div>'
    f'<div class="section-count">{len(parameter_columns):,} parameters in the workbook</div></div>',
    unsafe_allow_html=True)

controls = st.columns([3.4, 1.15, 1.5])
search = controls[0].text_input("Search", placeholder="Search parameters…",
                                label_visibility="collapsed")
top_n = controls[1].selectbox("Show", ["Top 10", "Top 20", "Top 50", "All"], index=3,
                             label_visibility="collapsed")

display = (results[results["parameter"].str.contains(search, case=False, na=False)]
           if search else results)
if top_n != "All":
    display = display.head(int(top_n.split()[1]))

with controls[2]:
    if results.empty:
        st.button("Download Excel", disabled=True, use_container_width=True)
    else:
        by_category = None
        if scheme == "All Funds" and category == "All Categories":
            by_category = compute_by_category(
                str(DEFAULT_WORKBOOK), from_year, to_year,
                tuple(results["parameter"].tolist()),
                int(min_observations), float(significance_level))
        st.download_button(
            "Download Excel",
            data=build_correlation_workbook(
                results, from_year, to_year, category, scheme,
                by_category=by_category, excluded=excluded,
                min_observations=int(min_observations),
                significance_level=float(significance_level)),
            file_name=export_filename(from_year, to_year, category, scheme),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            help="Year range, category, parameter name and correlation for every "
                 "reported parameter, plus a per-category breakdown.")

if display.empty:
    st.info("No parameter meets the current thresholds. Lower the minimum observation "
            "count, widen the year range, or clear the significance filter.")
else:
    st.markdown(
        f'<div class="panel">{render_ranking(display)}'
        f'<div class="meta">Showing {len(display):,} of {len(results):,} reported parameters '
        f'· pairwise complete observations · minimum N = {int(min_observations)} '
        f'· significance at p ≤ {significance_level:g}</div></div>',
        unsafe_allow_html=True)

if not excluded.empty:
    with st.expander(f"Omitted parameters ({len(excluded):,})"):
        st.markdown(render_omitted(excluded), unsafe_allow_html=True)

with st.expander("Methodology and data notes"):
    st.markdown(f"""
**Pairing.** A parameter observed in year **T** is matched to the same `scheme_id`'s return in
year **T+1**. The current scope covers parameter years **{from_year}–{to_year}** against return
years **{return_span}**. The final parameter year is dropped when its next-year return is
unavailable.

**Coefficient.** Pearson correlation over pairwise complete observations. Missing values are
never imputed and non-finite values are dropped. A parameter is reported only when it clears the
minimum observation floor and both series carry real variance.

**Why the floor matters.** A Pearson coefficient from a handful of fund-years is noise. The alpha
and beta family carries the most missing data in this workbook, so it is the first to produce
large, unstable values on a narrow slice. The floor and the p-value together keep those out of
the ranking.

**Robustness.** Spearman's rank correlation (ρ) is computed alongside Pearson. When the two
differ by {OUTLIER_GAP} or more, a small number of extreme values is driving the linear
coefficient and the row is flagged as outlier-driven.

**Sources.** Sheets `{PARAMETER_SHEET}` and `{RETURN_SHEET}`. Loaded {parameter_shape[0]:,}
parameter rows and {return_shape[0]:,} return rows; {len(parameter_columns):,} numeric parameters
detected automatically.
""")
