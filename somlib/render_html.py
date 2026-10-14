"""Static HTML report: one self-contained file, no server, no external assets."""
import datetime as dt
import html

from .activity import WEEKS, deadline_days, fmt_gap, humanize_days

TREND_TEXT = {"up": "↑ picking up", "down": "↓ easing off", "steady": "→ steady", "quiet": "· quiet this month"}

CSS = """
:root{--bg:#f7f6f3;--card:#fff;--ink:#1d1d1b;--muted:#6b6a65;--line:#e4e2dc;--bar:#3d6fb6;--bar-dim:#d9d6ce;--chip:#efede7}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe7;--muted:#9a988f;--line:#2e2d2a;--bar:#7aa5e6;--bar-dim:#3a3935;--chip:#2a2926}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0}
.date{color:var(--muted);margin:2px 0 28px}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:32px 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px;display:grid;grid-template-columns:1fr auto;gap:4px 16px;align-items:center}
.name{font-weight:600;font-size:16px}
.meta{color:var(--muted);font-size:13px}
.chip{display:inline-block;background:var(--chip);border-radius:99px;padding:1px 8px;font-size:12px;color:var(--muted);margin-right:4px}
.stats{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px 18px;font-size:13px}
.stats b{font-weight:600}
.commit{grid-column:1/-1;font-size:13px;color:var(--muted);border-top:1px dashed var(--line);padding-top:6px;margin-top:4px}
svg{display:block}
.empty{color:var(--muted);font-style:italic}
table{width:100%;border-collapse:collapse;font-size:14px}
td{padding:7px 4px;border-bottom:1px solid var(--line)}
td.r{text-align:right;color:var(--muted)}
details{margin-top:28px;color:var(--muted);font-size:14px}
footer{margin-top:40px;color:var(--muted);font-size:12px}
@media (max-width:560px){.card{grid-template-columns:1fr}}
"""


def _spark_svg(weekly):
    w, h, gap = 10, 34, 3
    peak = max(weekly) or 1
    bars = []
    for i, v in enumerate(weekly):
        bh = 2 if v == 0 else max(4, round(v / peak * h))
        color = "var(--bar-dim)" if v == 0 else "var(--bar)"
        bars.append(f'<rect x="{i * (w + gap)}" y="{h - bh}" width="{w}" height="{bh}" rx="2" fill="{color}"><title>{v}</title></rect>')
    total_w = WEEKS * (w + gap) - gap
    return (f'<svg width="{total_w}" height="{h}" viewBox="0 0 {total_w} {h}" role="img" '
            f'aria-label="Activity per week, last {WEEKS} weeks">{"".join(bars)}</svg>')


def _active_card(entry, s, today):
    e = html.escape
    chips = f'<span class="chip">{e(entry["type"])}</span><span class="chip">{e(s["provenance"])}</span>'
    if entry.get("source"):
        chips += f'<span class="chip">{e(entry["source"]["repo"])}</span>'
    if s["has_data"]:
        rhythm = fmt_gap(s["typical_gap"])
        long_break = fmt_gap(s["long_gap"])
        rhythm_txt = (f"usually {rhythm}" + (f", breaks up to {long_break} are normal" if long_break else "")
                      if rhythm else "still learning its rhythm")
        stats = (f'<div class="stats"><span>last touched <b>{humanize_days(s["days_since"])}</b></span>'
                 f'<span><b>{s["count_30d"]}</b> in 30 days ({s["active_days_30d"]} days)</span>'
                 f'<span>{TREND_TEXT[s["trend"]]}</span><span>rhythm: {rhythm_txt}</span></div>')
    elif entry.get("source"):
        stats = '<div class="stats empty">No commits cached yet — run som sync.</div>'
    else:
        stats = f'<div class="stats empty">Nothing logged yet — som log {e(entry["id"])}</div>'

    c = entry.get("commitment") or {}
    commit_parts = []
    if c.get("goal"):
        commit_parts.append(f"Goal: {e(c['goal'])}")
    days = deadline_days(entry, today)
    if days is not None:
        commit_parts.append(f"Due {e(c['deadline'])} ({'in ' + str(days) + 'd' if days >= 0 else str(-days) + 'd ago'})")
    commitment = f'<div class="commit">{" · ".join(commit_parts)}</div>' if commit_parts else ""

    return (f'<div class="card"><div><div class="name">{e(entry["name"])}</div><div class="meta">{chips}</div></div>'
            f'{_spark_svg(s["weekly"])}{stats}{commitment}</div>')


def render(view):
    today = view["today"]
    e = html.escape
    parts = [f"<h1>State of Me</h1><p class='date'>{today:%A, %d %B %Y}</p>",
             f"<h2>Active · {len(view['active'])}</h2>"]
    if view["active"]:
        parts += [_active_card(entry, s, today) for entry, s in view["active"]]
    else:
        parts.append('<p class="empty">Nothing active right now.</p>')

    parts.append(f"<h2>Parked · {len(view['parked'])}</h2>")
    if view["parked"]:
        rows = []
        for entry, s in view["parked"]:
            touched = (f"{s['last']} · {humanize_days(s['days_since'])}" if s["has_data"] else "no activity on record")
            rows.append(f"<tr><td>{e(entry['name'])}</td><td class='r'>{e(entry['type'])}</td><td class='r'>{touched}</td></tr>")
        parts.append(f"<table>{''.join(rows)}</table>")
    else:
        parts.append('<p class="empty">Nothing parked.</p>')

    if view["done"]:
        names = ", ".join(e(entry["name"]) for entry, _ in view["done"])
        parts.append(f"<details><summary>{len(view['done'])} done / retired</summary><p>{names}</p></details>")

    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts.append(f"<footer>Bars = activity per week, last {WEEKS} weeks (oldest left). Generated {generated}.</footer>")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>State of Me</title><style>{CSS}</style></head><body><main>{"".join(parts)}</main></body></html>')
