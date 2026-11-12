"""Each fund's latest parameter values, for the Linear regression tab's next-year prediction.

    python build_latest.py       # writes dashboard/latest.js
"""

import json
from pathlib import Path

import numpy as np

import study as S

OUT = Path(__file__).resolve().parent / "dashboard" / "latest.js"


def num(v, d=4):
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def main():
    data = S.load()
    year = data.partial_year or max(data.full_years)
    rows = data.panel[data.panel["param_year"] == year].sort_values(["category", "scheme_name"])
    live = rows["fund_return"] - data.nifty_partial
    returns = [y + 1 for y in data.full_years]
    payload = {"year": int(year), "target": int(year) + 1, "liveLabel": data.partial_label, "niftyAverage": num(data.nifty.reindex(returns).mean(), 2),
               "parameters": data.parameters,
               "funds": [[r.scheme_name, r.category, num(v, 2)] for r, v in zip(rows.itertuples(), live)],
               "values": [[num(v) for v in row] for row in rows[data.parameters].to_numpy(dtype=float)]}
    OUT.write_text("window.LATEST = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"Wrote dashboard/{OUT.name}: {len(rows)} funds, {year} parameters")


if __name__ == "__main__":
    main()
