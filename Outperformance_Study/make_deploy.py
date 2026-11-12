"""Build deploy/ (or the folder named on the command line): an exact copy of the local dashboard (every tab, same
data) for Vercel. A Vercel project is named after its folder, so another folder deploys to another project.

    python make_deploy.py && cd deploy && vercel deploy --prod --archive=tgz
    python make_deploy.py nifty-outperformance-dashboard && cd nifty-outperformance-dashboard && vercel deploy --prod --archive=tgz
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "dashboard"
OUT = HERE / (sys.argv[1] if len(sys.argv) > 1 else "deploy")
KEEP = {".vercel", ".env.local", ".gitignore"}   # the Vercel project link stays


def main():
    OUT.mkdir(exist_ok=True)
    for item in OUT.iterdir():                     # discard the previous build
        if item.name not in KEEP:
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    for item in SOURCE.iterdir():
        target = OUT / item.name
        shutil.copytree(item, target) if item.is_dir() else shutil.copy(item, target)
    # Version every data file the page loads by its content, so a browser never mixes
    # a new page with a cached old file.
    html = (OUT / "index.html").read_text()
    for name in ("data.js", "funds.js", "category.js", "prediction.js", "previous.js", "period.js", "latest.js", "armp.js", "amc.js", "ex/data.js", "ex/prediction.js", "ex/previous.js", "sec/data.js", "sec/prediction.js", "sec/previous.js", "exsec/data.js", "exsec/prediction.js", "exsec/previous.js", "research.js", "markov.js", "top3.js", "panel.js",
                 "vendor/xlsx.full.min.js"):
        tag = hashlib.md5((OUT / name).read_bytes()).hexdigest()[:10]
        for quote in ('"',):
            html = html.replace(f"{quote}{name}{quote}", f"{quote}{name}?v={tag}{quote}")
    (OUT / "index.html").write_text(html)
    (OUT / "vercel.json").write_text(json.dumps({
        "cleanUrls": True,
        "headers": [{"source": "/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=0, must-revalidate"}]}],
    }, indent=2) + "\n")
    # Never upload local secrets (vercel link writes .env.local here).
    (OUT / ".vercelignore").write_text(".env*\n.vercel\n")
    print(OUT.name + "/:", ", ".join(f"{p.name} ({p.stat().st_size // 1024} KB)" for p in sorted(OUT.iterdir())))


if __name__ == "__main__":
    main()
