# Beating the Nifty 50 by 3–4%

Which fund parameters reliably predict next-year returns, which categories beat
the Nifty 50 by 3–4%, and whether specific funds can be picked in advance.

## Run

```bash
python3 fetch_indices.py              # optional: refresh Nifty index returns from Yahoo Finance
python3 build.py                      # from this folder; writes the workbook and dashboard data
python3 -m http.server 8700 --bind 127.0.0.1 --directory dashboard
```

Then open http://localhost:8700 (or open `dashboard/index.html` directly).

| File | What it is |
| --- | --- |
| `study.py` | The analysis: data, reliability, categories, backtest, outlook |
| `fetch_indices.py` | Downloads Nifty index levels (Yahoo Finance) into `data/index_returns.csv` |
| `stats_analysis.py` | Statistical tests: Fama-MacBeth regressions per category and parameter, q-values, multivariate model |
| `build.py` | Runs it; writes `Outperformance_Analysis.xlsx` and `dashboard/data.js` |
| `Outperformance_Analysis.xlsx` | The whole working, one sheet per step, with a reconciliation sheet |
| `dashboard/index.html` | The dashboard: hypotheses, analytics and results |

## Data

`DEC25_WORKBOOK` and the Book3 funds from the parent project's `config.py`.
Parameters in calendar year T are paired with the fund's return in T+1. The
benchmark is the Nifty 50 price index row of the export. The latest return year
(Jan–Sep 2026) is used only as a live check of the final call.

Each category's own benchmark (Smallcap 250, Midcap 150, Nifty 100, Nifty 500 ...
TRI) is read from the export: fund return minus Morningstar's "Excess Return" is
identical for every fund in a category. Yahoo Finance supplies the price-index
returns for the partial year (which the export lacks) and confirms the history:
its Nifty 50 matches the export in every year, and each derived TRI sits a
steady ~1.4 points a year (dividends) above the same-name price index.

## Method

1. **Reliability.** Each year, funds are ranked by the parameter and by next-year
   return; the Spearman rank correlation is that year's IC. A parameter is
   reliable when the mean IC has |t| ≥ 2, the same sign in ≥ 65% of years and in
   both halves of history. Ranking within each year removes the market-wide
   year effect that dominates the pooled correlations of the earlier sheets.
2. **Categories.** Equal-weight category return minus the Nifty 50, per year;
   how often each cleared +3% and +4%; whether leaders persist.
3. **Backtest.** From 2010, each year chooses up to 8 signals using only ICs
   already known, drops near-duplicates, scores every fund by its average
   percentile rank, and follows the top 20% for a year.
4. **Outlook.** The same scoring on 2025 parameters for 2026.

All settings are at the top of `study.py`.

5. **Statistical analysis** (`stats_analysis.py`, the dashboard's first tab; benchmark: the
   Nifty 50 only). For every group (all funds, all funds within category, each of
   the 11 categories) and every parameter: descriptive statistics; a Fama-MacBeth
   regression of next-year return over the Nifty 50 on the parameter, standardised
   within year and capped at ±3 SD; Newey-West standard errors; t, p, 95% CI;
   Benjamini-Hochberg q-values within each group; a second regression for the
   chance of beating the Nifty 50 by 3%+; and a multivariate model of the strongest
   non-duplicate parameters with VIFs. Sheets `Stats_Univariate`, `Stats_Returns`,
   `Regression`.
6. **Explorer** (dashboard tab). Pick any parameter and category to see every
   statistic for that pair, the quintile analysis (funds split into five equal
   groups by the parameter each year: average next-year return over the Nifty 50
   and the share beating it by 3%+), the yearly slopes with the confidence band,
   and a scatter of every fund-year (drawn from `dashboard/panel.js`, loaded on
   demand). Sheets `Quintiles` and `Yearly_Slopes` hold the same numbers.

## Fund analysis (fund → parameters → prediction)

```bash
python3 build.py          # caches the category statistics (cache/statistics.pkl)
python3 build_funds.py    # writes Fund_Level_Analysis.xlsx and dashboard/funds.js
```

`fund_analysis.py`, the dashboard's first tab. For each fund and parameter: the
fund's own rank correlation between the parameter in year T and its return over
the Nifty 50 in T+1 (8+ years needed), its category's Fama-MacBeth result, and a
reliability label (Fund + category agree / Fund only / Category only / none).
Each category's values are cut into five equal-count ranges with the chance of
beating the Nifty 50 by 3%+ next year (Wilson 95% interval); the fund's latest
value is placed in its range. The prediction averages, over the parameters that
are significant for the category and whose fund correlation agrees with
|ρ| ≥ 0.30 (adjustable on the page), the next-year excess of the range the fund
sits in, weighted by |ρ|, near-duplicates counted once. The live check against
Jan–Sep 2026 is reported overall and after removing category averages.

**Update — fund analysis is now fund-only.** `fund_analysis.py` / `build_funds.py` model each fund's own
parameters against its own excess return over the Nifty 50 the following year: for each parameter the
fund's values are split into low / middle / high ranges, the fund's 2025 value is placed in one, and that
range's average next-year excess is what the parameter expects. Parameters with |correlation| ≥ 0.30
are averaged, weighted by |correlation| (near-duplicates once). Output: expected excess return over the
Nifty 50 for calendar 2026. Workbook sheets: Method, Expected_Excess, Calculation, Fund_History,
All_Parameters.

## Category analysis and Testing

```bash
python3 build_category.py   # writes Category_Analysis.xlsx and dashboard/category.js
```

`category_analysis.py` applies the fund method to a category (or all funds) by pooling every fund-year,
so funds with a short history count with the years they have. A parameter is used if its pooled
correlation with next-year excess has p < 0.05 and |correlation| ≥ 0.15 (adjustable). Applied to the
group's median 2025 values (typical fund) and to every fund's own 2025 values.

Testing & prediction (`stats_prediction.py`, `build_prediction.py` → `Stats_Prediction.xlsx`,
`dashboard/prediction.js`; run `build.py` first for the Statistical analysis cache). The question: does a
fund beat the Nifty 50 by 3%+ next calendar year? Candidates are the parameters the Statistical analysis
rates **Robust** per group; versions of one measure and parameters moving together (|rank corr| > 0.80)
count once. Backtest on parameter years 2020–2024 (returns 2021–2025): each year funds are split into
fifths by the parameter, a fund's predicted excess is its fifth's average next-year excess over the
earlier years only, and the call is "beats by 3%+" if that is ≥ 3. Hit ratio = right calls / all funds;
the naive call gives every fund the answer from the group's own past average. Feasible = hit ratio above
60% (page: 55/60/65%) on 30+ calls and more right than naive. At 60% no parameter passes (closest: Flexi
Cap Up Capture Return 59.7% vs naive 30.6%), so there is no 2026 prediction; at 55% Flexi Cap gets one.
The workbook opens with a Read_Me sheet (the answer, how the sheets connect, worked examples to verify a
call and the feasibility decision by hand); every count is an Excel formula.

## Research methods (separate tab)

```bash
python3 build_research.py   # writes Research_Methods.xlsx and dashboard/research.js
```

`research_methods.py` tests methods from the fund-performance literature on the same question as Testing
& prediction (beats the Nifty 50 by 3%+ next year; feasible = > 60% and better than naive). Prediction =
category part (the category's past average yearly excess over the Nifty 50) + fund part (expected return
vs the category, from: 1- and 3-year momentum, 3-year Alpha, 3-year Information Ratio, low R², low R² +
high Alpha (Amihud & Goyenko), or a ridge regression on all six). Walk-forward on returns 2021–2025 and,
for robustness, 2011–2025. Result: only Low R² + high Alpha for Focused passes; over 2011–2025 that signal
ranks funds within a category well (top − bottom fifth +2.7 pts a year, 11 of 15 years) but the 3% call
fails on the category part (right 44% of the time in 2021–2025). Independent of every other tab's files.

## Three hit ratios (Testing & prediction)

The tab and `Stats_Prediction.xlsx` now score every parameter three ways, each against the naive call:
the 3%+ call; within ± tolerance (|actual − predicted| ≤ 1/2/3/5 pts; workbook cell Shortlist!Z2); and
actual ≥ predicted (rewards low predictions, so only meaningful next to naive). Feasibility follows the
selected one.

## Markov chain (separate tab)

```bash
python3 build_markov.py     # writes Markov_Chain.xlsx and dashboard/markov.js
```

`markov_chain.py`: each fund-year's excess over the Nifty 50 is a state (lagged by 3%+ / behind 0–3% /
ahead 0–3% / beat by 3%+); the transition matrix (per category, blended with all funds by 10
pseudo-transitions) gives next year's state probabilities, P(beat by 3%+) and an expected excess.
Walk-forward backtest on returns 2021–2025 with the same three hit ratios and naive call, a category-level
chain, and 2026 predictions. Result: next year's state barely depends on this year's (beat → beat 46%,
lagged → beat 46%); no group passes. Matrix, state averages and predictions are formulas in the workbook.

Candidates for every category: groups with Robust parameters (All Funds, Flexi Cap, Large Cap, Mid Cap)
use those; the others have none, so they use their significant (p ≤ 0.05, not Robust) parameters,
labelled "Candidates are" in Group_Summary / Shortlist. Dividend Yield and Multi Cap have too few funds a
year to be backtested.

## Top 3 picks (separate tab)

```bash
python3 build_top3.py       # writes Top3_Picks.xlsx and dashboard/top3.js
```

`top3.py`: every method (Testing & prediction candidates, Research methods signals and ridge, Markov chain)
ranks each group's funds each year with data up to that year and picks its top 3. Checks: picks in the
actual top 3 (exact), in the top 10 (close), and their percentile in the group, each against blind picks
(3/N, 10/N, 50%), plus the chance of doing that well by luck (exact hypergeometric for top-3 hits, normal
approximation for the percentile) with a multiple-testing bar of 0.05 / methods tested. Backtest returns
2021–2025; live 2025 picks vs Jan–Sep 2026; 2026 picks per method.

Markov chain, parameter-based models: the starting state can also be the fund's third of its category by a
candidate parameter this year (3 states) or that third x last year's return state (12 states); same
backtest, checks and workbook formulas (Param_Results / Param_Matrix / Param_State_Averages /
Param_Predictions in Markov_Chain.xlsx). The tab has a model selector and a table of every model per group.

Top 3 picks, the hit: a pick beats the Nifty 50 by 3%+ that year (vs random picks = the share of the group's
funds that did, exact chance by luck, bar 0.05 / methods). Methods that work the same way in every category
are also pooled over all categories (All_Categories sheet): 1-year momentum passes there (109/165 = 66% vs
58% random, chance by luck 0.0002).

## Current dashboard (three tabs)

The page now shows only **Testing & prediction**, **Previous parameters** and **Statistical analysis**
(the other analyses remain in the code and workbooks). Testing & prediction adds the deviation
(actual − predicted) and baskets of predicted excess (below 0%, 0–1%, …, 10%+: count, average predicted,
average actual, deviation, share that beat 3%+); `Stats_Prediction.xlsx` has them as formulas (Backtest_Calls
columns V–X, Shortlist columns AJ–AK, sheet Baskets).

`build_previous.py` → `Previous_Parameters.xlsx`, `dashboard/previous.js`: the nine parameters of the earlier
correlation study (`stats_prediction.PREVIOUS`) through the same backtest in every group, with the three
hit ratios, deviation and baskets. None passes on the 3% call.

Monthly data (`../Parameter_monthly_data`, 44 workbooks, Jan 2005 – Sep 2026) was exported with a one-month
calculation window (Number of Observations = 1), so most statistics are blank; only return-based fields and
flows are usable as delivered.

## Period test tab

`dashboard/period.js` re-runs the analysis in the browser for any analysis and testing period (return years; return year Y uses parameter year Y - 1). The analysis period gives the statistics, the tested parameters and each fifth's average; the testing period gives the hit ratios, deviation and baskets. The nine previous parameters run on the same periods. Export to Excel writes every prediction with formulas. The explanation page is hidden from the tab bar and opens at `#how`.

The Period test tab also has an Analysis only mode, and shows the statistics of all 101 parameters separately from the testing. The Parameter correlation tab shows the rank correlation of every parameter pair as a heatmap, with the pairs ranked below it.

The Indicator tests tab tests all 101 indicators against next-year excess and against beating the Nifty 50 by 3 points: direction, effect size, 95% CI and p-value for any period and group. Period test and Indicator tests apply no multiple-testing correction: Robust there means p <= 0.05 with the same sign in both halves.

The Period test hit ratio table lists all 101 parameters and marks the ones shortlisted in the analysis period.

The Linear regression tab runs OLS on next-year excess return: a multiple regression on chosen parameters and all 101 one at a time, with coefficient, standard error, t, p, 95% CI, R-squared, F and VIF. Standard errors are clustered by year by default; classic OLS and year effects are options. The tab also shows a correlation heatmap of the 20 parameters with the smallest p.

The switch at the top of the dashboard excludes return years 2008 and 2009 with their parameter years 2007 and 2008. The browser-calculated tabs filter the panel; `python build_excluded.py` rebuilds the Python-built tabs into `dashboard/ex/` and `Excluded_2008_2009/`.

The Linear regression tab predicts next-year excess by applying a multiple regression to each fund's latest values (parameters significant at p <= 0.05, with data for at least 80% of fund-years, dropping any with a correlation above 0.9 with a stronger one) in `dashboard/latest.js` (`python build_latest.py`).

Period test can require a minimum share of analysis and testing years with data for each parameter.

The Linear regression tab can compare custom periods and list the parameters significant in all of them. Once periods are added, the prediction's multiple regression uses the common parameters with one direction. The Multiple regression section shows the line equation and how it's built from each parameter's individual line.

The Regression test tab builds a line on one chosen period from chosen parameters, shows its derivation, and tests it on another period.

The Multiple regression section ends with a Backtest: the line equation applied to a chosen period.

Regression test can select the nine AR previous parameters at once, and Linear regression shows a heatmap of the model's parameters against them. A further heatmap shows the shortlisted parameters against each other in the backtest years.

A second switch excludes Sector and Thematic funds everywhere (`python build_excluded.py sector` and `both` rebuild the Python-built tabs). Fund categories agree with the MF Universe Shortlist FY 26-27 file; `build_classification.py` writes `Fund_Classification.xlsx`.

The tabs sit in a side panel: the excess-return regression work, then Top quartile prediction, then the earlier analysis.

Top quartile prediction has two tabs, Absolute return (y = excess + the Nifty 50's return, stored in `panel.js` as `nifty`) and Excess return. Each category gets its own model:
1. Every parameter is regressed alone on y in the training years.
2. The significant ones are kept (p <= 0.05, data for 80% of fund-years), dropping any above 0.9 correlation with a stronger kept one.
3. A multiple regression is fitted on the kept parameters.
4. In each test year, the category's top round(n/4) funds by prediction are compared with its actual top quartile (random baseline k*k/n).

The Funds choice "All funds combined" (the default) builds one model on every fund and forms quartiles across all funds each year; "Each category separately" builds one model per category. Any set of quartiles can be predicted (Q1 = top, cut-offs round(n/4), round(n/2), round(3n/4)): a hit is a fund in the chosen quartiles by both prediction and actual return.

Both tabs run the same test again with the nine AR previous parameters fixed (no selection step) and show it alongside: a card, a column in the main table, a year-by-year comparison, the AR line in each step-by-step view, and AR_Prev_ sheets in the export.

Results are shown per category, step by step, with the 2026 prediction and a Jan-Sep 2026 check (`tqCat` in `period.js`).

The Improved methods tab (peer-rank, seeded and blend lines) is no longer in the side panel; its code stays in `period.js` and `index.html`.

The AR MP analysis tab shows where the AR model portfolio's funds finished each calendar year, using any quartile combination, with quartiles within the fund's category or across all funds.
- Portfolio data comes from `MF_AR_Workstation_New/research/datadump/Model Port data.xlsx`, sheet "Actual dates". `python build_ar_mp.py` builds `dashboard/armp.js`, matching funds by name or by ISIN.
- The portfolio as of 31 March of a year is the latest rebalance on or before that date. It is taken as held for that whole calendar year.
- The tab reports the hit ratio by count and by weight, the random baseline, year-by-year quartile counts, each year's holdings, and a Jan-Sep 2026 live row.

The Absolute return and Excess return tabs now score picks rather than predicted quartiles, using `tqPicks` in `period.js`:
- Value and Contra and Dividend Yield are left out of training and testing.
- Each test year, every category's best 3 funds by predicted return are its picks (or best 2 if the category has fewer than 20 funds; the threshold is selectable). A pick is a hit when it finishes in the chosen quartiles of its category.
- A 14-fund basket takes the model portfolio's category counts: Large & Mid Cap 3, Focused 2, Multi Cap 2, Small Cap 2, Flexi Cap 2 (including the Dividend Yield slot), Large Cap 1, Mid Cap 1, Sector 1.
- The Funds dropdown chooses either all funds (one line, the default) or a single category. A single category gets its own parameter selection and line, built from that category's funds only, and only that category's picks and basket slots are scored. The tabs show the hit ratio, random baseline, p, AR previous parameters, live 2026, by category, and year-by-year picks and basket.

**Score** (Absolute return and Excess return tabs): every pick scores by the quartile it finished in, Q1 100, Q2 65, Q3 35, Q4 0 (`SCORE` in period.js). The tabs give the picks' and basket's average score out of 100 next to the random score, the average score of the same categories that year (what a random pick would get), for the test years, the live year so far, by year against the AR previous parameters, and by category; the fund lists show each fund's score. Both Excel exports carry it as formulas: a Score column on the Picks / Basket and run sheets (from Actual quartile) and its averages on the summary sheets. In Export iterations the points sit in the Summary's "Score points" row, so changing them there rescores the whole workbook.

**Walk-forward** tab: the 16 iterations of Export iterations, each test year predicted only from the years before it. With training from 2006 and testing 2021–2025, 2021 is predicted by models trained on returns 2006–2020, 2022 on 2006–2021, … 2025 on 2006–2024, and the live picks on 2006–2025; every model chooses its parameters afresh (steps 1–4). The AMC filter only changes the picks, so runs 3 and 4 share the models of runs 1 and 2: 8 models × (test years + live), about 48 fits, some 15 seconds. The tab shows all 16 runs (hit ratio, p, basket, scores, live), a year-by-year table (hit ratio or score, picks or basket) with each year's training window, and each model's training window and chosen parameters year by year. The quartiles, the 3-pick rule and the AMC grid re-pick without refitting. Export to Excel gives the same formula-linked iterations workbook plus a Training windows sheet (WalkForward_Iterations_…_L2006-expanding_….xlsx). Engine: `tqWalkPicks` in period.js merges one `tqCat` per test year.

The tab also fits each model once on the fixed period (training start to the year before testing: the linear regression of the Absolute / Excess return tabs) and shows, for all 16 runs:
- **Confusion matrices**, walk-forward next to fixed: every fund's predicted quartile (from its predicted rank, with the actual quartile's cut-offs; `predQuart`) against the quartile it finished in (`tqConfusion`), for the test years together, each year or the live year; with exact, within one, Q1 precision, big miss (predicted Q1 that finished Q4) and the picks' precision / recall.
- **The audit**: for every model and category, the parameters per window (fixed, each test year, live), how many were used, kept in every window, added + dropped from year to year, shared with the fixed model, sign flips, and windows with no model or not scored (a chosen parameter with no data that year). One model in detail: its weights (or weight × 1 SD, or t) window by window with each parameter's status, the year-over-year log, and every window's equation.

- **Precision, recall, accuracy and F1** for all 16 runs, walk-forward next to fixed, each with what random picks would give: for the top 2–3 picks and the basket (positive = picked; actual positive = finished in the chosen quartiles; TP, FP, FN, TN), and for the four quartiles as classes (macro averages; with equal-sized predicted and actual quartiles each quartile's precision, recall and F1 coincide). Accuracy is mostly true negatives, so read it against random.

Both iteration workbooks get a Predicted quartile column on the run sheets, a Metrics sheet (the same measures per run, period and classifier, as formulas: COUNTIFS on the run sheets for the picks and basket, the Confusion sheet's blocks for the quartiles) and a Confusion sheet (COUNTIFS on the run sheets; the walk-forward one adds the fixed regression's as values); the walk-forward workbook adds Audit weights, Audit changes and Equations sheets.

**Leave out AMCs** (Absolute return and Excess return tabs): a grid with the AMCs as rows and the years as columns (each year of the testing period, then the live year). A ticked cell removes that AMC's funds from that year's testing or live data: never picked and not counted in the category's quartiles; All ticks every year of the row. Training always keeps every fund. The picks update when the list closes. `python build_amc.py` builds `dashboard/amc.js` (fund to AMC) from Fund_Classification.xlsx (fund to ISIN) and Book3.xlsx (ISIN to "AMC Full Name"); the AMC is today's, so a fund that changed hands counts under its current AMC.

**Export iterations** (Absolute return and Excess return tabs): one workbook with Summary, Yearwise, Categorywise and Year x Category sheets, then 16 runs, each with every fund of every category and year (Year, Category, Fund, AMC, Shortlist, Predicted rank, Actual quartile, Hit/Miss): for the parameters selected in training and for the nine AR previous parameters, for absolute and excess return, with one formula for all categories or a formula per category, without and with the AMC filter. The page's years, quartiles, 3-pick rule, Options and AMC choice apply. With the AMC filter (runs 3 and 4) those funds are removed from the test and live years ticked in the grid; training keeps them. The workbook is formula-linked: every number on the four summary sheets is a COUNTIFS / AVERAGEIFS on the run sheets (p uses NORMSDIST), and on each run sheet Actual (quartile, from Actual rank and Funds in category), Result (Hit/Miss for the picks and basket funds) and Random (the category's chance of the chosen quartiles) are formulas, so editing a run sheet updates everything. The file name gives the number of AMCs left out; Summary lists them.

**Funds in a year** (AR MP analysis tab): every fund with a return in the chosen year, ranked inside its category (or against all funds), with the portfolio's holdings in bold and their weight. Filter to the holdings only or to one category. The export adds an All_Funds sheet.

To share the dashboard on the local network, run `python3 serve.py 8700` and open `http://<this machine's IP>:8700/`. It serves `dashboard/` on all interfaces and sends Cache-Control: no-cache, so viewers always get the latest files. The firewall must allow the port, for example `sudo ufw allow 8700/tcp`.

## Vercel (parametres-correlation)

The dashboard is published at https://parametres-correlation.vercel.app (Vercel project parametres-correlation; it was created as
nifty-outperformance-dashboard and renamed, and the local build folder keeps that first name). To update it after a change:

```
python make_deploy.py nifty-outperformance-dashboard
cd nifty-outperformance-dashboard
npx vercel deploy --prod --yes --archive=tgz
```

`make_deploy.py` keeps the folder's `.vercel` link (by project id), so the deploy goes to parametres-correlation. On the office network
Node.js needs the Windows certificate store first (in PowerShell: `$env:NODE_OPTIONS = '--use-system-ca'`, and `npx.cmd` instead of `npx`),
otherwise the Vercel CLI fails with "fetch failed" (UNABLE_TO_GET_ISSUER_CERT_LOCALLY). The older `deploy/` folder is linked to the separate
nifty-outperformance project.
