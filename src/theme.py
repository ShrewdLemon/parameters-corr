"""Appearance tokens and the stylesheet built from them.

Two palettes, both verified against WCAG AA for body-sized text (the weakest
pair is 4.55:1). Every colour the application paints comes from these dicts, so
the two modes can never drift apart, and Streamlit's own widgets are re-skinned
from the same variables rather than left on their defaults.
"""

APPEARANCES = ("Dark", "Light")

LIGHT = {
    "bg": "#f7f9fc", "surface": "#ffffff", "sunken": "#f2f5fa", "raised": "#ffffff",
    "text": "#10141b", "muted": "#4a5566", "quiet": "#6b7688",
    "line": "#dfe4ec", "hair": "#eceff5", "shadow": "rgba(16,24,40,.06)",
    "accent": "#2f4bc4", "accent_soft": "#eef1fd", "accent_line": "#c8d2f4",
    "pos": "#2f5fa8", "neg": "#a8503c", "track": "#e7ebf2", "tick": "#b8c0cd",
    "ok": "#1f6b45", "ok_soft": "#e6f4ec", "ok_line": "#c3e2d1",
    "warn": "#7a5410", "warn_soft": "#fdf4e3", "warn_line": "#eddcb4",
    "hover": "#f7f9fc",
}

DARK = {
    "bg": "#14161b", "surface": "#1c1f26", "sunken": "#22262f", "raised": "#242833",
    "text": "#e8ecf3", "muted": "#9aa6b8", "quiet": "#7d8798",
    "line": "#2a2f39", "hair": "#23272f", "shadow": "rgba(0,0,0,.28)",
    "accent": "#7d9bf5", "accent_soft": "#202a44", "accent_line": "#33406a",
    "pos": "#6f9fe0", "neg": "#d98e77", "track": "#2b303b", "tick": "#59616f",
    "ok": "#7ddba6", "ok_soft": "#172f22", "ok_line": "#2c4d39",
    "warn": "#e0b562", "warn_soft": "#322611", "warn_line": "#54421c",
    "hover": "#222630",
}


def tokens(appearance):
    return DARK if appearance == "Dark" else LIGHT


def build_css(appearance):
    t = tokens(appearance)
    variables = "".join(f"--{key.replace('_', '-')}:{value};" for key, value in t.items())
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{{{variables}
--font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
--mono:ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace;}}

/* ---------- foundation ---------- */
html,body,.stApp,[data-testid="stAppViewContainer"]{{background:var(--bg)!important;color:var(--text);}}
.stApp,body,.stMarkdown,p,span,div,label,li,td,th{{font-family:var(--font);}}
.block-container{{max-width:1400px;padding:1.5rem 2.4rem 4rem;}}
header[data-testid="stHeader"]{{background:transparent!important;}}
[data-testid="stToolbar"]{{background:transparent;}}
footer,[data-testid="stStatusWidget"]{{visibility:hidden;}}
[data-testid="stDecoration"]{{display:none!important;}}
h1,h2,h3,h4,h5{{font-family:var(--font);color:var(--text)!important;letter-spacing:-.02em;}}
a{{color:var(--accent);}}
hr{{border-color:var(--line);}}
::selection{{background:var(--accent-soft);color:var(--text);}}

/* ---------- hero ---------- */
.hero{{padding:.2rem 0 1.15rem;border-bottom:1px solid var(--line);margin-bottom:1.3rem;}}
.hero-line{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}}
.hero h1{{font-size:32px;line-height:1.14;margin:0;font-weight:700;color:var(--text)!important;}}
.hero p{{color:var(--muted);font-size:14px;margin:.6rem 0 0;max-width:82ch;line-height:1.62;}}
.badge{{border-radius:999px;padding:6px 12px;font-size:12px;font-weight:600;white-space:nowrap;
color:var(--accent);border:1px solid var(--accent-line);background:var(--accent-soft);}}

/* ---------- kpi tiles ---------- */
.kicker{{color:var(--muted);font-size:12px;letter-spacing:.05em;text-transform:uppercase;
font-weight:600;margin-bottom:2px;}}
.kpi{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:15px 17px;
height:100%;box-shadow:0 1px 3px var(--shadow);}}
.kpi-label{{color:var(--quiet);font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;font-weight:600;}}
.kpi-value{{color:var(--text);font-size:26px;line-height:1.15;font-weight:650;margin-top:10px;
font-variant-numeric:tabular-nums;letter-spacing:-.015em;}}
.kpi-sub{{color:var(--muted);font-size:13px;margin-top:7px;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;}}

/* ---------- section headers ---------- */
.section-head{{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin:1.9rem 0 .85rem;}}
.section-head h2{{font-size:21px;margin:0;font-weight:650;}}
.section-head p{{color:var(--muted);font-size:13.5px;margin:6px 0 0;line-height:1.55;}}
.section-count{{color:var(--muted);font-size:13px;white-space:nowrap;}}

/* ---------- callout ---------- */
.callout{{border-radius:10px;padding:13px 16px;font-size:13.5px;line-height:1.6;margin:.3rem 0 1rem;
border:1px solid var(--warn-line);background:var(--warn-soft);color:var(--warn);}}
.callout b{{color:var(--warn);font-weight:700;}}

/* ---------- table ---------- */
.panel{{background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:2px 2px 8px;box-shadow:0 1px 3px var(--shadow);overflow-x:auto;}}
table.rank{{width:100%;border-collapse:collapse;font-size:14px;}}
table.rank th{{color:var(--quiet);font-size:11px;letter-spacing:.07em;text-transform:uppercase;
text-align:left;padding:14px 14px;border-bottom:1px solid var(--line);font-weight:600;
white-space:nowrap;background:var(--surface);position:sticky;top:0;z-index:1;}}
table.rank td{{padding:13px 14px;border-bottom:1px solid var(--hair);vertical-align:middle;color:var(--text);}}
table.rank tbody tr:last-child td{{border-bottom:none;}}
table.rank tbody tr:hover{{background:var(--hover);}}
td.rk{{color:var(--quiet);width:44px;font-variant-numeric:tabular-nums;font-size:13px;}}
td.pname{{color:var(--text);font-weight:600;min-width:250px;line-height:1.4;}}
td.cval{{font-family:var(--mono);font-weight:650;white-space:nowrap;font-size:14px;
font-variant-numeric:tabular-nums;}}
td.cval.up{{color:var(--pos);}} td.cval.down{{color:var(--neg);}}
td.num{{font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap;font-size:13px;}}
td.reason{{color:var(--muted);font-size:13px;line-height:1.5;}}
.pill{{display:inline-block;color:var(--muted);background:var(--sunken);border:1px solid var(--line);
border-radius:999px;padding:4px 10px;font-size:11.5px;font-weight:500;white-space:nowrap;}}
.pill-ok{{color:var(--ok);background:var(--ok-soft);border-color:var(--ok-line);}}
.pill-warn{{color:var(--warn);background:var(--warn-soft);border-color:var(--warn-line);}}
.track{{width:112px;height:7px;background:var(--track);position:relative;border-radius:4px;}}
.zero{{position:absolute;left:50%;top:-3px;height:13px;border-left:1px solid var(--tick);}}
.fill{{position:absolute;top:0;height:7px;border-radius:4px;}}
.fill.positive{{left:50%;background:var(--pos);}}
.fill.negative{{right:50%;background:var(--neg);}}
.meta{{color:var(--muted);font-size:13px;padding:13px 14px 4px;line-height:1.55;}}

/* ---------- year-wise matrix ---------- */
.panel.scroll{{max-height:72vh;overflow:auto;}}
table.matrix{{font-size:13px;}}
table.matrix th{{text-align:center;white-space:normal;min-width:84px;line-height:1.35;padding:12px 8px;}}
table.matrix th.lead,table.matrix td.pname{{text-align:left;position:sticky;left:0;z-index:2;
background:var(--surface);min-width:230px;}}
table.matrix th.lead{{z-index:3;}}
table.matrix td{{padding:9px 8px;}}
table.matrix td.mv{{font-family:var(--mono);text-align:center;white-space:nowrap;
font-variant-numeric:tabular-nums;color:var(--text);}}
table.matrix td.mv.thin{{color:var(--quiet);font-style:italic;}}
table.matrix td.mv.na{{color:var(--quiet);}}
table.matrix tbody tr:hover td.pname{{background:var(--hover);}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin:.2rem 0 .7rem;}}
.legend i{{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px;}}

/* ---------- appearance switch ---------- */
[data-testid="stButton"]:has(button[kind]) button{{white-space:nowrap;}}
.switch-hint{{color:var(--quiet);font-size:11px;text-align:right;margin-top:4px;}}

/* ---------- streamlit widgets ---------- */
/* The innermost container holding a kicker. An ancestor also "has" one, which
   would otherwise draw a border around the whole page. Streamlit renamed this
   container from stVerticalBlockBorderWrapper to stLayoutWrapper in 1.4x, so
   both are matched and the app styles correctly on either DOM. */
[data-testid="stVerticalBlockBorderWrapper"]:has(.kicker):not(:has([data-testid="stVerticalBlockBorderWrapper"] .kicker)),
[data-testid="stLayoutWrapper"]:has(.kicker):not(:has([data-testid="stLayoutWrapper"] .kicker)){{
background:var(--surface);border:1px solid var(--line)!important;border-radius:12px;
padding:8px 6px;box-shadow:0 1px 3px var(--shadow);}}
[data-testid="stWidgetLabel"] p,.stTextInput label,.stSelectbox label{{color:var(--muted)!important;
font-size:13px!important;font-weight:500;}}
[data-baseweb="select"]>div,[data-testid="stNumberInput"] input,.stTextInput input{{
background:var(--surface)!important;border-color:var(--line)!important;color:var(--text)!important;
border-radius:9px!important;font-size:14px!important;}}
[data-baseweb="select"]>div{{min-height:40px;}}
[data-baseweb="select"] svg{{fill:var(--muted)!important;}}
[data-baseweb="select"] [data-baseweb="tag"]{{background:var(--accent-soft)!important;color:var(--accent)!important;}}
.stTextInput input,[data-testid="stNumberInput"] input{{height:38px;border:none!important;}}
[data-testid="stNumberInput"] [data-baseweb="input"],[data-testid="stTextInput"] [data-baseweb="input"],
[data-testid="stNumberInput"]>div>div{{background:var(--surface)!important;
border:1px solid var(--line)!important;border-radius:9px!important;}}
[data-testid="stNumberInput"] [data-baseweb="input"]:focus-within,
[data-testid="stTextInput"] [data-baseweb="input"]:focus-within{{border-color:var(--accent)!important;}}
.stTextInput input::placeholder{{color:var(--quiet)!important;}}
[data-baseweb="popover"] [data-baseweb="menu"],[data-baseweb="popover"] ul{{background:var(--raised)!important;
border:1px solid var(--line)!important;border-radius:10px;}}
[data-baseweb="popover"] li{{color:var(--text)!important;font-size:14px!important;}}
[data-baseweb="popover"] li:hover,li[aria-selected="true"]{{background:var(--accent-soft)!important;}}
[data-testid="stNumberInputStepUp"],[data-testid="stNumberInputStepDown"]{{background:var(--sunken)!important;
color:var(--muted)!important;border-color:var(--line)!important;}}
[data-testid="stNumberInputStepUp"]:hover,[data-testid="stNumberInputStepDown"]:hover{{color:var(--accent)!important;}}
[data-baseweb="checkbox"] [data-testid="stMarkdownContainer"] p{{font-size:13.5px!important;color:var(--muted)!important;}}
[data-baseweb="checkbox"] span[data-baseweb]{{border-color:var(--line)!important;background:var(--surface)!important;}}
[data-baseweb="checkbox"] input:checked+span{{background:var(--accent)!important;border-color:var(--accent)!important;}}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button{{min-height:40px;border:1px solid var(--line)!important;
color:var(--text)!important;background:var(--surface)!important;border-radius:9px!important;
font-size:13.5px!important;font-weight:550;width:100%;transition:all .12s ease;box-shadow:none!important;}}
[data-testid="stButton"] button p,[data-testid="stDownloadButton"] button p{{
color:var(--text)!important;font-size:13.5px!important;font-weight:550;}}
[data-testid="stDownloadButton"] button:hover{{background:var(--accent)!important;
border-color:var(--accent)!important;}}
[data-testid="stDownloadButton"] button:hover p{{color:#fff!important;}}
[data-testid="stButton"] button:hover{{border-color:var(--accent)!important;background:var(--accent-soft)!important;}}
[data-testid="stButton"] button:hover p{{color:var(--accent)!important;}}
[data-testid="stButton"] button:disabled,[data-testid="stDownloadButton"] button:disabled{{
background:var(--sunken)!important;border-color:var(--line)!important;}}
[data-testid="stButton"] button:disabled p,[data-testid="stDownloadButton"] button:disabled p{{
color:var(--quiet)!important;}}
[data-testid="stTooltipHoverTarget"]{{width:100%;}}
[data-testid="stExpander"]{{background:var(--surface);border:1px solid var(--line)!important;
border-radius:12px;box-shadow:0 1px 3px var(--shadow);}}
[data-testid="stExpander"] summary{{color:var(--text)!important;font-size:14px;font-weight:550;padding:14px 16px;}}
[data-testid="stExpander"] summary:hover{{color:var(--accent)!important;}}
[data-testid="stExpander"] svg{{fill:var(--muted);}}
[data-testid="stExpander"] .stMarkdown,[data-testid="stExpander"] p,[data-testid="stExpander"] li{{
color:var(--muted);font-size:13.5px;line-height:1.68;}}
[data-testid="stExpander"] strong{{color:var(--text);}}
[data-testid="stAlert"]{{background:var(--sunken)!important;border:1px solid var(--line);
border-radius:10px;color:var(--text)!important;}}
[data-testid="stAlert"] p{{color:var(--text)!important;font-size:13.5px;}}
[data-baseweb="tooltip"]{{background:var(--raised)!important;color:var(--text)!important;
border:1px solid var(--line);font-size:12.5px;}}

@media(max-width:900px){{
.block-container{{padding:1rem 1rem 2.5rem;}}
.hero h1{{font-size:25px;}} .hero p{{font-size:13px;}}
.section-head{{align-items:flex-start;flex-direction:column;gap:6px;}}
.track{{width:70px;}} table.rank{{font-size:13px;}} td.pname{{min-width:170px;}}
}}
</style>"""
