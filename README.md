# Mutual Fund Forward Return Correlation Analytics

A Streamlit dashboard that ranks every eligible numeric mutual-fund parameter by its
correlation with the **same scheme's return in the following year**.

## Run

```bash
python3 -m pip install -r requirements.txt
streamlit run app.py
```

The application reads `Correlation file_rishil_Maker 1.xlsx` from the project root, using the
workbook's `Parameter data` sheet (annual parameter blocks, 2005-2022) and `Return data` sheet
(annual returns, 2006-2023).

## Accuracy

The pooled full-range coefficients reproduce the workbook's own `Summary` sheet **exactly** for
all 24 parameters that sheet reports (maximum absolute difference 1.2e-15). That check is the
regression test for any change to the loader, the cleaner, or the engine.

Three rules earn that agreement and keep sliced views honest:

- **Zero is not always zero.** `Average Drawdown`, `Average Loss` and `Calmar Ratio` average or
  divide over a *subset* of periods. A stored `0.0` means the subset was empty -- no drawdown, or
  no losing period, that year -- so the statistic is undefined. The source export emits `0.0`;
  the workbook's own per-ratio sheets leave those cells blank and compute `Summary` without them.
  `src/cleaner.py` restores them to missing.
- **A minimum sample size.** A Pearson coefficient built from a handful of fund-years is noise.
  The alpha and beta family carries the most missing data here (`Bear Beta` has 901 paired
  observations against `Average (Annualized)`'s 2,489), so it is the first to throw off large,
  unstable values on a narrow slice. A single fund has at most 18 observations, which is why
  selecting one now reports nothing rather than 98 spurious correlations.
- **Significance and robustness travel with every number.** Each coefficient carries its
  two-sided p-value and a Spearman rank correlation. When Pearson and Spearman diverge by 0.15 or
  more, a few extreme values are driving the linear figure and the row is flagged
  *outlier-driven* -- `Calmar Ratio`, for instance, is -0.10 by Pearson but -0.54 by Spearman
  because one observation reaches 1,890.

## Data rules

- Parameter year `T` is joined to the same `scheme_id` and return year `T + 1`.
- The final parameter year is omitted when its next-year return is unavailable.
- Numeric parameters are detected from the workbook at load time.
- Missing values are never imputed; pairwise complete observations are used.
- Parameters are reported only when they clear the observation floor and both series carry
  variance. Everything else is listed under *Omitted parameters* with the reason.

## Excel export

**Download Excel** produces a workbook whose every row carries the year range, the category, the
parameter name and its correlation, so a row stays meaningful once copied elsewhere:

| Sheet | Contents |
| --- | --- |
| `Correlations` | One row per reported parameter for the current selection |
| `By Category` | The same parameters broken out per category (all-funds, all-categories scope) |
| `Omitted` | Parameters excluded, with the reason |
| `Methodology` | Scope, thresholds and the meaning of each flag |

Each sheet carries correlation, Spearman, observations, p-value, significance, strength,
direction and the outlier-sensitivity flag.

## Layout

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit UI: filters, KPIs, ranking table, export |
| `config.py` | Workbook path, observation floor, significance level, outlier gap |
| `src/loader.py` | Reads the two workbook sheets into tidy frames |
| `src/cleaner.py` | Types, de-duplicates, and restores zero placeholders to missing |
| `src/forward_returns.py` | Joins parameter year `T` to return year `T + 1` |
| `src/correlation_engine.py` | The single source of every coefficient in the app |
| `src/filters.py` | Year, scheme and category scoping |
| `src/exporter.py` | Builds the downloadable workbook |
| `src/yearwise_summary.py` | Year-wise summary grid, workbook and reconciliation |
| `build_summary.py` | Writes `Summary_All_Years.xlsx` |

## Year-wise summary

`Parameter data.xlsx` (sheets `Parameter data_Filtered` and `Return data`) feeds a second view,
**Year-wise summary**, and the file `Summary_All_Years.xlsx`:

```bash
python3 build_summary.py   # writes Summary_All_Years.xlsx and reconciles it with Summary.xlsx
```

Sheet `YYYY` pools every parameter year from `YYYY` to the last one in the file and correlates
each of the 101 parameters with the same fund's next-year return, per fund group -- the grid of
`Summary.xlsx`. There is one sheet per parameter year, and they're detected from the file, so a
later export with more years adds sheets automatically. The last sheet is the final parameter year,
because its next-year return is the latest one available.

Figures follow Excel `CORREL` (pairwise complete, no floor), as the reference does. Funds are
grouped by the *Final Category* of the working file's `Fund list` sheet, saved to
`data/fund_categories.csv` (refresh with `python3 build_summary.py --fund-list "Correlation working - 2005.xlsx"`).
Every group column, `All Funds` included, reproduces `Summary.xlsx` to ~1e-15. `All Funds`
follows the working file's `All Funds- 2005` sheet, whose parameter formulas stop at row 470 while
the fund list runs to row 488: the 18 funds below that (UTI Large Cap … WhiteOak) never enter its
CORREL, so they are left out here as well (`in_all_funds` column of the CSV, read from the file).

The same run writes `Summary_Windows.xlsx` with the fixed windows in `SUMMARY_WINDOWS`.
**Convention:** a period `YYYY-ZZ` names its last **parameter** year -- `2005-23` pools parameters
2005-2023 against returns 2006-2024. A window the data cannot cover yet (`2018-25` needs 2025
parameters and 2026 returns) is skipped and appears once the data exists.

`SUMMARY_EXCLUSION_SHEETS` adds sheets to the all-years workbook that drop whole Final
Categories from every group, All Funds included. `2005 ex Sector` is sheet `2005` without the 58
Sector funds (Consumption, Infrastructure, Energy & Power, Service Industry).

`Summary_Ex_Sector.xlsx` (`SUMMARY_EX_SECTOR_SHEETS`) holds the sector-free sheets on their own:
`2005 ex Sector` (parameters 2005-2024) and `2005-23 ex Sector` (parameters 2005-2023, returns 2006-2024).

`Summary_Updated_Data.xlsx` is built from `Parameter data updated.xlsx` (19-10-2026 export, every
annualised parameter filled for every year): 2005-24, 2018-24 and 2005-22, each with and without
Sector funds. Only the funds of `Book3.xlsx` are used, grouped by its Final Category; All Funds
there includes every listed fund.

`Summary_Dec25.xlsx` is the same six-sheet workbook built from `Parameter data updated-Dec 25.xlsx`
(calendar years 2005-2024, Book3 funds).

## Correlation page (no Streamlit)

`frontend/index.html` is a standalone black-and-white page: pick the parameter years (the return
years follow, one year later, and vice versa), optionally exclude Sector funds, search the 101
parameters, and export the full table to Excel. Correlations are computed in the browser from
`frontend/data.js`, with the same pairwise Pearson as the workbooks.

```bash
python3 build_frontend.py      # regenerate frontend/data.js from the latest parameter export
```

Open `frontend/index.html` in a browser -- no server needed. It uses DEC25_WORKBOOK and the Book3
funds (the data behind `Summary_Latest_2005-25.xlsx`); the 2026 return is Jan-Sep only.

## Appearance

The theme is pinned in `.streamlit/config.toml` so the page never inherits the operating
system's light/dark preference — without it, Streamlit renders its own widgets dark on a dark
desktop while the stylesheet paints light panels. Both palettes live in `src/theme.py` and are
verified against WCAG AA for body text; the switch sits at the top right.

`streamlit` is pinned to 1.50.0 in `requirements.txt` because that stylesheet restyles
Streamlit's own widgets through `data-testid` and BaseWeb selectors, which are internal and move
between releases. Verified in a real browser on 1.39 and 1.50, in both palettes:

| Version | Installs on current Python | Theme holds |
| --- | --- | --- |
| 1.39.0 | **No** — caps `pillow<11`, which has no wheel and fails to build from source | yes |
| 1.50.0 | yes (pillow 11.3, packaging 25) | yes |
| 1.53+ | yes | **no** — BaseWeb is gone, so selects and inputs lose their theming |

The bordered container was renamed from `stVerticalBlockBorderWrapper` to `stLayoutWrapper` in
1.4x; `src/theme.py` matches both, so the app also renders correctly on 1.39. Upgrading past
1.50 means re-checking the theme in a browser first.

## Deploy

The repository is private and the workbook is committed, so the app runs as-is.

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with the GitHub account that owns
   this repository and grant access to private repositories when prompted.
2. **Create app → Deploy a public app from GitHub**, then set:
   - Repository: `sofiyaan7/mf-correlation-analytics`
   - Branch: `main`
   - Main file path: `app.py`
3. Under **Advanced settings**, choose Python 3.11 or 3.12.

**Restrict who can view it.** A Community Cloud app is reachable by anyone with the URL even when
the repository is private, and this workbook holds internal fund research. After the first deploy,
open **Settings → Sharing** and either invite specific viewers by email or set the app to private
so the data is not served to the public.

The first load parses the 19 MB workbook and is slow; `st.cache_data` keeps subsequent
interactions fast. Free-tier instances have about 1 GB of memory, which is comfortable for this
dataset.
