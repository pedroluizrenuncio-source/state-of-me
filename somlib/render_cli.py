"""Terminal view: active fronts with their signal, then the quiet parked list."""
from .activity import WEEKS, deadline_days, fmt_gap, humanize_days

BARS = "·▁▂▃▄▅▆▇█"
TREND_ARROWS = {"up": "↑", "down": "↓", "steady": "→", "quiet": "·"}


def sparkline(weekly):
    peak = max(weekly) or 1
    return "".join(BARS[0 if v == 0 else max(1, round(v / peak * 8))] for v in weekly)


def _commitment_line(entry, today):
    c = entry.get("commitment") or {}
    parts = []
    if c.get("goal"):
        parts.append(f"goal: {c['goal']}")
    days = deadline_days(entry, today)
    if days is not None:
        when = f"in {days}d" if days >= 0 else f"{-days}d ago"
        parts.append(f"due {c['deadline']} ({when})")
    return " · ".join(parts)


def render(view):
    today = view["today"]
    out = [f"STATE OF ME — {today:%a %d %b %Y}", ""]
    name_w = max([len(e["name"]) for e, _ in view["active"] + view["parked"]] + [10])

    out.append(f"ACTIVE ({len(view['active'])})")
    if not view["active"]:
        out.append("  nothing active - `som add \"Name\" -t coding` to add a front")
    for entry, s in view["active"]:
        head = f"  {entry['name']:<{name_w}}  {entry['type']:<7}  "
        if s["has_data"]:
            rhythm = fmt_gap(s["typical_gap"])
            rhythm_txt = f"rhythm {rhythm}" if rhythm else "rhythm: learning"
            head += (
                f"{sparkline(s['weekly'])}  last {humanize_days(s['days_since']):<9}  "
                f"{s['count_30d']:>3} in 30d {TREND_ARROWS[s['trend']]}  {rhythm_txt:<14}  [{s['provenance']}]"
            )
        elif entry.get("source"):
            head += f"{'·' * WEEKS}  no commits cached yet - run `som sync`"
        else:
            head += f"{'·' * WEEKS}  nothing logged yet - `som log {entry['id']}`"
        out.append(head)
        commitment = _commitment_line(entry, today)
        if commitment:
            out.append(f"  {'':<{name_w}}  {commitment}")

    out.append("")
    out.append(f"PARKED ({len(view['parked'])})")
    if not view["parked"]:
        out.append("  (none)")
    for entry, s in view["parked"]:
        if s["has_data"]:
            touched = f"last touched {s['last']} ({humanize_days(s['days_since'])})"
        else:
            touched = "no activity on record"
        out.append(f"  {entry['name']:<{name_w}}  {entry['type']:<7}  {touched}")

    if view["done"]:
        out.append("")
        out.append(f"{len(view['done'])} done/retired - `som list --all` to see them")
    out.append(f"\n{WEEKS}-week sparkline, oldest → this week.")
    return "\n".join(out)


def render_list(reg, show_all=False):
    rows = [e for e in reg["entries"] if show_all or e["status"] != "done"]
    if not rows:
        return "Registry is empty. Add one: som add \"Name\" -t coding --repo owner/repo"
    id_w = max(len(e["id"]) for e in rows)
    lines = []
    for e in sorted(rows, key=lambda e: (["active", "parked", "done"].index(e["status"]), e["id"])):
        src = e["source"]["repo"] if e.get("source") else "-"
        c = e.get("commitment") or {}
        extra = "  ".join(x for x in [f"due {c['deadline']}" if c.get("deadline") else "",
                                       f"goal: {c['goal']}" if c.get("goal") else ""] if x)
        lines.append(f"{e['id']:<{id_w}}  {e['status']:<6}  {e['type']:<7}  {src:<28}  {extra}".rstrip())
    return "\n".join(lines)
