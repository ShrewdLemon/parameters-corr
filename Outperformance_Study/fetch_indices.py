"""Download Nifty index levels from Yahoo Finance and cache calendar-year returns.

    python fetch_indices.py

Yahoo Finance's chart endpoint is free and needs no key (it is unofficial and
has soft rate limits; this makes one request per index). It carries the price
indices only, so these figures exclude dividends. The result is cached in
data/index_returns.csv so the study never depends on the network.
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "data" / "index_returns.csv"

# Index name -> Yahoo Finance symbol.
INDICES = {
    "Nifty 50": "^NSEI",
    "Nifty 100": "^CNX100",
    "Nifty 500": "^CRSLDX",
    "Nifty Midcap 150": "NIFTYMIDCAP150.NS",
    "Nifty Smallcap 250": "NIFTYSMLCAP250.NS",
    "Nifty LargeMidcap 250": "NIFTY_LARGEMID250.NS",
    "Nifty 500 Multicap 50:25:25": "NIFTY500_MULTICAP.NS",
}
IST = timezone(timedelta(hours=5, minutes=30))


def daily_closes(symbol):
    query = urllib.parse.urlencode({"period1": 946684800, "period2": int(time.time()),
                                    "interval": "1d", "events": "history"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)["chart"]["result"][0]
    dates = [datetime.fromtimestamp(t, IST).date() for t in result["timestamp"]]
    closes = result["indicators"]["quote"][0]["close"]
    series = pd.Series(closes, index=pd.to_datetime(dates), dtype="float64").dropna()
    return series[~series.index.duplicated(keep="last")]


def period_returns(closes):
    """Calendar-year returns, plus the current year to the last complete month."""
    year_end = closes.groupby(closes.index.year).last()
    rows = []
    for year in year_end.index[1:]:
        last = closes[closes.index.year == year]
        complete = last.index.max().month == 12 and last.index.max().day >= 24
        if complete:
            rows.append({"year": year, "period": f"Jan-Dec {year}",
                         "return": (year_end[year] / year_end[year - 1] - 1) * 100})
        else:
            # Partial year: up to the last month that has ended.
            month_end = last.groupby(last.index.month).last()
            ended = [m for m in month_end.index if m < datetime.now(IST).month or
                     last.index.max().month > m]
            if ended:
                m = max(ended)
                rows.append({"year": year,
                             "period": f"Jan-{datetime(year, m, 1):%b} {year}",
                             "return": (month_end[m] / year_end[year - 1] - 1) * 100})
    first_year = closes.index.year.min()
    return [r for r in rows if r["year"] > first_year]


def main():
    frames = []
    for name, symbol in INDICES.items():
        closes = daily_closes(symbol)
        rows = period_returns(closes)
        frames.append(pd.DataFrame(rows).assign(index=name, symbol=symbol,
                                                first_date=closes.index.min().date()))
        print(f"{name:28s} {symbol:22s} {closes.index.min().date()} -> {closes.index.max().date()} "
              f"({len(rows)} periods)")
        time.sleep(1)
    out = pd.concat(frames, ignore_index=True)[["index", "symbol", "year", "period", "return",
                                                  "first_date"]]
    out["source"] = "Yahoo Finance (price index)"
    out["fetched"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    OUTPUT.parent.mkdir(exist_ok=True)
    out.to_csv(OUTPUT, index=False)
    print(f"Wrote {OUTPUT.relative_to(HERE)}")


if __name__ == "__main__":
    main()
