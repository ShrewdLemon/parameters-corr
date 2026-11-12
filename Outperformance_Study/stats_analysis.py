"""Statistical analysis of every parameter in every fund category.

Question: does a fund's parameter in year T predict its return in year T+1
relative to the Nifty 50, within each category? The benchmark is the Nifty 50
throughout: returns are expressed as excess over it, and a second regression
targets the goal directly - the chance of beating it by 3% or more.

Method (standard for panels of funds/stocks with strong year effects):

* Fama-MacBeth. Each year, the parameter is standardised across the group's
  funds (z-score, capped at +/-3 SD so outliers cannot drive it) and next-year
  return is regressed on it. The yearly slopes are averaged. The slope reads as
  "percentage points of next-year return per 1 SD of the parameter".
* Standard errors come from the time series of yearly slopes, with a
  Newey-West correction (1 lag) for serial correlation. Pooling all fund-years
  as if independent would overstate significance: funds in the same year share
  the market's move.
* Robustness: the mean yearly Spearman rank IC, the share of years with a
  positive slope, and the sign in each half of history.
* Multiple testing: p-values are turned into Benjamini-Hochberg q-values,
  controlling the false discovery rate across the 101 parameters of each group
  (each group is its own question).
* Multivariate: a small set of non-duplicate parameters estimated together,
  with variance inflation factors to check for collinearity.
"""

import numpy as np
import pandas as pd
from scipy import stats

MIN_FUNDS_PER_YEAR = 5      # cross-section needed for a yearly slope
MIN_YEARS = 8               # yearly slopes needed for a result
NW_LAGS = 1                 # Newey-West lags for the slope series
Z_CAP = 3.0                 # standardised values are capped at +/- this
ALPHA = 0.05                # significance level
FDR = 0.10                  # false discovery rate for q-values
MULTI_MAX_VARS = 6          # parameters in the multivariate model
MULTI_MAX_CORR = 0.70       # a candidate is dropped if it correlates more with one kept
QUINTILE_MIN_FUNDS = 10     # funds needed in a year to split it into five groups
QUINTILE_MIN_YEARS = 5
BEAT_MARGIN = 3.0           # "beat the Nifty 50 by 3%" (percentage points)


def _zscore(values):
    sd = values.std(ddof=1)
    if not np.isfinite(sd) or sd == 0:
        return values * np.nan
    return ((values - values.mean()) / sd).clip(-Z_CAP, Z_CAP)


def newey_west_se(series, lags=NW_LAGS):
    """Standard error of the mean of a time series, Newey-West corrected."""
    x = np.asarray(series, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return np.nan
    e = x - x.mean()
    gamma0 = (e @ e) / n
    long_run = gamma0
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1 - lag / (lags + 1)
        long_run += 2 * weight * (e[lag:] @ e[:-lag]) / n
    return np.sqrt(max(long_run, gamma0 * 0.25) / n)


def bh_qvalues(p):
    """Benjamini-Hochberg q-values for an array of p-values (NaN kept)."""
    p = np.asarray(p, dtype=float)
    q = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    values = p[ok]
    order = np.argsort(values)
    ranked = values[order] * len(values) / (np.arange(len(values)) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(values)
    out[order] = np.minimum(ranked, 1.0)
    q[ok] = out
    return q


def yearly_slopes(frame, parameter, target="excess"):
    """Per year: slope of the target on the standardised parameter, and the rank IC.

    Within a year the Nifty 50 return is the same for every fund, so the slope on
    excess return equals the slope on raw return; the 'beat' target (1 if the fund
    beat the Nifty 50 by BEAT_MARGIN, else 0) is where the benchmark matters.
    """
    rows = []
    for year, group in frame.groupby("param_year"):
        pair = group[[parameter, target]].dropna()
        if len(pair) < MIN_FUNDS_PER_YEAR or pair[parameter].nunique() < 3:
            continue
        z = _zscore(pair[parameter])
        if z.isna().all():
            continue
        y = pair[target]
        zc = z - z.mean()
        slope = (zc * (y - y.mean())).sum() / (zc @ zc)
        ic = stats.spearmanr(pair[parameter], y).statistic if y.nunique() > 1 else np.nan
        rows.append({"year": year, "slope": slope, "ic": ic, "n": len(pair)})
    return pd.DataFrame(rows)


def _fm(slopes):
    slopes = np.asarray(slopes, dtype=float)
    mean = slopes.mean()
    se = newey_west_se(slopes)
    t = mean / se if se and np.isfinite(se) and se > 0 else np.nan
    p = 2 * stats.t.sf(abs(t), df=len(slopes) - 1) if np.isfinite(t) else np.nan
    return mean, se, t, p


def univariate(frame, parameter):
    yearly = yearly_slopes(frame, parameter)
    values = frame[parameter].dropna()
    base = {"fund_years": int(frame[[parameter, "excess"]].dropna().shape[0]),
            "mean": values.mean(), "sd": values.std(ddof=1), "median": values.median(),
            "p10": values.quantile(0.10), "p90": values.quantile(0.90),
            "min": values.min(), "max": values.max(),
            "years": len(yearly), "yearly": yearly}
    if len(yearly) < MIN_YEARS:
        return {**base, "status": "insufficient"}
    slopes = yearly["slope"].to_numpy()
    mean, se, t, p = _fm(slopes)
    beat = yearly_slopes(frame, parameter, "beat")
    b_mean, b_se, b_t, b_p = _fm(beat["slope"]) if len(beat) >= MIN_YEARS else (np.nan,) * 4
    half = len(yearly) // 2
    first, second = yearly["slope"].iloc[:half].mean(), yearly["slope"].iloc[half:].mean()
    return {**base, "status": "ok", "slope": mean, "se": se, "t": t, "p": p,
            "ci_low": mean - stats.t.ppf(0.975, len(slopes) - 1) * se,
            "ci_high": mean + stats.t.ppf(0.975, len(slopes) - 1) * se,
            "ic": yearly["ic"].mean(), "share_positive": (slopes > 0).mean(),
            "first_half": first, "second_half": second,
            "stable": bool(np.sign(first) == np.sign(second) and first != 0),
            "avg_funds": yearly["n"].mean(),
            "beat_slope": b_mean, "beat_se": b_se, "beat_t": b_t, "beat_p": b_p}


def quintiles(frame, parameter):
    """Each year, split the funds into five equal groups by the parameter (Q1 lowest,
    Q5 highest) and average each group's next-year excess return and its rate of
    beating the Nifty 50 by BEAT_MARGIN; then average the years. Also the Q5-Q1
    spread with a Newey-West t-test."""
    by_year = []
    for year, group in frame.groupby("param_year"):
        pair = group[[parameter, "excess", "beat"]].dropna()
        if len(pair) < QUINTILE_MIN_FUNDS or pair[parameter].nunique() < 5:
            continue
        # Equal-sized groups (ties broken by order), the standard quintile split.
        bucket = pd.qcut(pair[parameter].rank(method="first"), 5, labels=False) + 1.0
        agg = pair.groupby(bucket).agg(excess=("excess", "mean"), beat=("beat", "mean"))
        if len(agg) == 5:
            by_year.append((year, agg))
    if len(by_year) < QUINTILE_MIN_YEARS:
        return None
    excess = pd.DataFrame({y: a["excess"] for y, a in by_year}).T
    beat = pd.DataFrame({y: a["beat"] for y, a in by_year}).T
    spread = excess[5.0] - excess[1.0]
    mean, se, t, p = _fm(spread.to_numpy())
    return {"years": len(by_year), "excess": excess.mean().tolist(), "beat": beat.mean().tolist(),
            "spread": mean, "spread_se": se, "spread_t": t, "spread_p": p,
            "spread_share_positive": (spread > 0).mean()}


def verdict(row):
    if row["status"] != "ok":
        return "Insufficient data"
    if row["q"] <= FDR and row["p"] <= ALPHA and row["stable"]:
        return "Robust"
    if row["p"] <= ALPHA:
        return "Significant, not robust"
    return "Not significant"


WITHIN = "All Funds, within category"


def within_category(panel, parameters):
    """Each fund compared only with its own category in the same year: parameters
    standardised and returns demeaned within (year, category). This strips out
    category tilts, leaving fund selection inside categories."""
    keys = [panel["param_year"], panel["category"]]
    out = panel[["param_year", "category", "scheme_id"]].copy()
    for column in ("excess", "beat"):
        out[column] = panel[column] - panel.groupby(keys)[column].transform("mean")
    z = panel.groupby(keys)[parameters].transform(lambda s: _zscore(s) if s.notna().sum() >= 3 else s * np.nan)
    return pd.concat([out, z], axis=1)


def group_frame(panel, group, parameters):
    if group == "All Funds":
        return panel
    if group == WITHIN:
        return within_category(panel, parameters)
    return panel[panel["category"] == group]


def all_groups(panel, parameters, groups):
    """Univariate results for every (group, parameter); q-values across all of them."""
    rows = []
    for group in groups:
        frame = group_frame(panel, group, parameters)
        for parameter in parameters:
            rows.append({"group": group, "parameter": parameter, **univariate(frame, parameter),
                         "quintiles": quintiles(frame, parameter)})
    table = pd.DataFrame(rows)
    # One family per group: "which of the 101 parameters matter in this universe?"
    # The false discovery rate is controlled across those 101 tests.
    table["q"] = np.nan
    table["beat_q"] = np.nan
    for _, idx in table.groupby("group").groups.items():
        table.loc[idx, "q"] = bh_qvalues(table.loc[idx, "p"])
        table.loc[idx, "beat_q"] = bh_qvalues(table.loc[idx, "beat_p"])
    table["verdict"] = table.apply(verdict, axis=1)
    return table


def return_stats(panel, groups):
    """Next-year return over the Nifty 50 for each group: mean, SD, how often funds
    beat it by BEAT_MARGIN, and the share of the variation in fund returns that is
    common to the year (the market) rather than specific to funds."""
    rows = []
    for group in groups:
        if group == WITHIN:
            continue
        frame = panel if group == "All Funds" else panel[panel["category"] == group]
        frame = frame.dropna(subset=["excess"])
        e = frame["excess"]
        year_means = frame.groupby("param_year")["fund_return"].transform("mean")
        within = (frame["fund_return"] - year_means).var(ddof=1)
        total = frame["fund_return"].var(ddof=1)
        t, p = stats.ttest_1samp(e, 0) if len(e) > 2 else (np.nan, np.nan)
        rows.append({"group": group, "fund_years": len(e), "mean_excess": e.mean(), "sd_excess": e.std(ddof=1),
                     "median_excess": e.median(), "share_beat": (e > 0).mean(),
                     "share_beat_margin": (e >= BEAT_MARGIN).mean(),
                     "share_year_effect": 1 - within / total if total else np.nan})
    return pd.DataFrame(rows)


# ---- multivariate ------------------------------------------------------------

def choose_variables(panel, univariate_all, parameters):
    """Strongest robust parameters for All Funds, skipping near-duplicates."""
    ranked = univariate_all[(univariate_all["group"] == "All Funds") & (univariate_all["status"] == "ok")]
    ranked = ranked.reindex(ranked["t"].abs().sort_values(ascending=False).index)
    z = standardised(panel, parameters)
    kept = []
    for parameter in ranked["parameter"]:
        if ranked.set_index("parameter").at[parameter, "p"] > ALPHA:
            break
        if all(abs(z[parameter].corr(z[k])) < MULTI_MAX_CORR for k in kept):
            kept.append(parameter)
        if len(kept) == MULTI_MAX_VARS:
            break
    return kept


def standardised(frame, parameters):
    return frame.groupby("param_year")[parameters].transform(_zscore)


def vif(z):
    """Variance inflation factor of each column of a standardised design."""
    data = z.dropna()
    out = {}
    for column in data.columns:
        others = data.drop(columns=column)
        if others.empty:
            out[column] = 1.0
            continue
        X = np.column_stack([np.ones(len(others)), others.to_numpy()])
        y = data[column].to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        r2 = 1 - resid.var() / y.var()
        out[column] = 1 / (1 - r2) if r2 < 1 else np.inf
    return pd.Series(out)


def multivariate(frame, variables):
    """Fama-MacBeth multiple regression: yearly OLS of next-year return on the
    standardised variables, averaged; Newey-West standard errors."""
    if not variables:
        return None
    z = standardised(frame, variables)
    data = pd.concat([frame[["param_year", "excess"]], z], axis=1).dropna()
    k = len(variables)
    yearly, r2s, ns = [], [], []
    for year, group in data.groupby("param_year"):
        if len(group) < max(MIN_FUNDS_PER_YEAR, k + 5):
            continue
        X = np.column_stack([np.ones(len(group)), group[variables].to_numpy()])
        y = group["excess"].to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        tss = ((y - y.mean()) ** 2).sum()
        r2 = 1 - (resid @ resid) / tss if tss else np.nan
        n = len(group)
        yearly.append(beta[1:])
        r2s.append(r2)
        ns.append(n)
    if len(yearly) < MIN_YEARS:
        return None
    B = np.array(yearly)
    T = len(B)
    rows = []
    for j, name in enumerate(variables):
        coef = B[:, j].mean()
        se = newey_west_se(B[:, j])
        t = coef / se
        p = 2 * stats.t.sf(abs(t), df=T - 1)
        crit = stats.t.ppf(0.975, T - 1)
        rows.append({"variable": name, "coef": coef, "se": se, "t": t, "p": p,
                     "ci_low": coef - crit * se, "ci_high": coef + crit * se,
                     "share_positive": (B[:, j] > 0).mean()})
    coefs = pd.DataFrame(rows)
    coefs["vif"] = coefs["variable"].map(vif(data[variables]))
    avg_n = np.mean(ns)
    r2 = np.nanmean(r2s)
    adj = 1 - (1 - r2) * (avg_n - 1) / (avg_n - k - 1)
    return {"coefficients": coefs, "years": T, "fund_years": int(sum(ns)), "avg_funds": avg_n,
            "avg_r2": r2, "avg_adj_r2": adj}


def run(panel, parameters, groups):
    panel = panel.dropna(subset=["excess"]).copy()
    panel["beat"] = (panel["excess"] >= BEAT_MARGIN).astype(float)
    uni = all_groups(panel, parameters, groups)
    variables = choose_variables(panel, uni, parameters)
    models = {}
    for group in groups:
        models[group] = multivariate(group_frame(panel, group, parameters), variables)
    return {"univariate": uni, "returns": return_stats(panel, groups), "variables": variables,
            "models": models}
