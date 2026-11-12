"""Fund house (AMC) of every fund on the dashboard: dashboard/amc.js, for the "Leave out AMCs" option.

Each study fund is matched to its ISIN through Fund_Classification.xlsx, and the ISIN to "AMC Full Name" in Book3.xlsx.
Funds with no ISIN match fall back to the AMC whose short name starts the fund's name. The AMC is today's, so a fund
that changed hands (L&T to HSBC, IDFC to Bandhan, Principal to Sundaram) counts under its current AMC.

    python build_amc.py
"""
import json
import re
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
CLASSIFICATION = HERE / "Fund_Classification.xlsx"
BOOK3 = HERE.parent / "Book3.xlsx"
SOURCES = [HERE / "dashboard" / "panel.js", HERE / "dashboard" / "latest.js"]
OUT = HERE / "dashboard" / "amc.js"

# short names where cutting the legal suffix is not enough
RENAME = {"HSBC Global": "HSBC", "Nippon Life India": "Nippon India", "LIC Mutual Fund": "LIC", "PPFAS": "PPFAS (Parag Parikh)",
          "Kotak Mahindra": "Kotak"}
# words a fund name may start with for each AMC, for funds without an ISIN match
PREFIX = {"Aditya Birla Sun Life": ["Aditya BSL", "Aditya Birla"], "ICICI Prudential": ["ICICI Pru"], "Kotak": ["Kotak"],
          "Nippon India": ["Nippon India"], "PPFAS (Parag Parikh)": ["Parag Parikh"], "Franklin Templeton": ["Franklin", "Templeton"],
          "Baroda BNP Paribas": ["Baroda BNP"], "Bank of India": ["Bank of India", "BOI"], "Mirae Asset": ["Mirae"], "LIC": ["LIC MF", "LIC"]}


def short(full):
    name = re.split(r"\s+(?:Asset Management|AMC\b|Investment Managers?|Investment Management|Funds Management|Money Managers|Capital Asset)", full)[0]
    name = re.sub(r"\s+(?:Mutual Fund)$", "", name.strip())
    return RENAME.get(name, name)


def study_funds():
    names = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        names += [f if isinstance(f, str) else f[0] for f in data["funds"]]
    return list(dict.fromkeys(names))


def main():
    isin = {r[0]: (r[1] or "").strip() for r in list(openpyxl.load_workbook(CLASSIFICATION, read_only=True).active.iter_rows(values_only=True))[1:] if r[0]}
    rows = list(openpyxl.load_workbook(BOOK3, read_only=True, data_only=True).active.iter_rows(values_only=True))
    head = next(i for i, r in enumerate(rows) if r and "AMC Full Name" in r)
    col_amc, col_isin = rows[head].index("AMC Full Name"), rows[head].index("SD_Scheme ISIN")
    amc_of_isin = {(r[col_isin] or "").strip(): short(r[col_amc]) for r in rows[head + 1:] if r and r[col_isin] and r[col_amc]}
    starts = {a: PREFIX.get(a, [a]) for a in set(amc_of_isin.values())}

    out, unmatched = {}, []
    for fund in study_funds():
        amc = amc_of_isin.get(isin.get(fund, ""))
        if amc is None:
            amc = next((a for a, words in sorted(starts.items(), key=lambda kv: -max(len(w) for w in kv[1]))
                        if any(fund.startswith(w + " ") for w in words)), None)
        if amc is None:
            unmatched.append(fund)
            amc = "Other"
        out[fund] = amc
    OUT.write_text("window.AMC = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    counts = {}
    for a in out.values():
        counts[a] = counts.get(a, 0) + 1
    print(f"{OUT.name}: {len(out)} funds, {len(counts)} AMCs; unmatched: {len(unmatched)}")
    for f in unmatched:
        print("  no AMC:", f)


if __name__ == "__main__":
    main()
