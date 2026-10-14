"""Turns raw activity (commits, manual log lines) into an honest picture.

Rule: if an entry has a real data source, only that source counts. Manual
log lines are kept as notes but never stand in for verified activity. Entries
without a source show exactly what you logged, labelled as self-logged.
"""
import datetime as dt
import json
import statistics

from . import github
from .registry import DATA_DIR

LOG_PATH = DATA_DIR / "manual_log.jsonl"
WEEKS = 12
CADENCE_WINDOW_DAYS = 365  # rhythm is learned from the last year, since habits change


def append_log(entry_id, note, date):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": entry_id, "date": date, "note": note}, ensure_ascii=False) + "\n")


def manual_log(entry_id):
    if not LOG_PATH.exists():
        return []
    rows = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["id"] == entry_id:
                rows.append(row)
    return rows


def events(entry):
    """Return (dates, provenance) for an entry."""
    source = entry.get("source")
    if source and source.get("kind") == "github":
        return github.commit_dates(source["repo"]), "github"
    dates = [dt.date.fromisoformat(r["date"]) for r in manual_log(entry["id"])]
    return dates, ("self-logged" if dates else "none")


def _trend(recent, previous):
    if recent == 0 and previous == 0:
        return "quiet"
    if previous == 0:
        return "up"
    ratio = recent / previous
    if ratio >= 1.25:
        return "up"
    if ratio <= 0.8:
        return "down"
    return "steady"


def compute(entry, today=None):
    today = today or dt.date.today()
    dates, provenance = events(entry)
    dates = [d for d in dates if d <= today]
    sig = {"provenance": provenance, "has_data": bool(dates)}
    if not dates:
        sig["weekly"] = [0] * WEEKS
        return sig

    active_days = sorted(set(dates))
    age = lambda d: (today - d).days
    last = active_days[-1]
    recent30 = sum(1 for d in dates if age(d) < 30)
    prev30 = sum(1 for d in dates if 30 <= age(d) < 60)

    weekly = [0] * WEEKS  # oldest week first, current week last
    for d in dates:
        w = age(d) // 7
        if w < WEEKS:
            weekly[WEEKS - 1 - w] += 1

    # Cadence = gaps between days you actually touched it. The median is the
    # "usual" gap; the 80th percentile is a "normal long break" for this front.
    window = [d for d in active_days if age(d) <= CADENCE_WINDOW_DAYS]
    gaps = [(b - a).days for a, b in zip(window, window[1:])]
    typical_gap = long_gap = None
    if len(gaps) >= 3:
        typical_gap = statistics.median(gaps)
        long_gap = statistics.quantiles(gaps, n=5, method="inclusive")[-1]

    sig.update({
        "last": last,
        "days_since": age(last),
        "first": active_days[0],
        "count_30d": recent30,
        "active_days_30d": sum(1 for d in active_days if age(d) < 30),
        "count_prev_30d": prev30,
        "trend": _trend(recent30, prev30),
        "weekly": weekly,
        "typical_gap": typical_gap,
        "long_gap": long_gap,
        "gap_samples": len(gaps),
    })
    return sig


def deadline_days(entry, today=None):
    deadline = (entry.get("commitment") or {}).get("deadline")
    if not deadline:
        return None
    return (dt.date.fromisoformat(deadline) - (today or dt.date.today())).days


def build_view(reg, today=None):
    """Split entries into active (ranked by signal), parked, and done."""
    today = today or dt.date.today()
    rows = [(e, compute(e, today)) for e in reg["entries"]]

    def rank(row):
        _, s = row
        if not s["has_data"]:
            return (1, 0, 0)
        return (0, s["days_since"], -s["count_30d"])

    active = sorted((r for r in rows if r[0]["status"] == "active"), key=rank)
    parked = sorted((r for r in rows if r[0]["status"] == "parked"), key=rank)
    done = [r for r in rows if r[0]["status"] == "done"]
    return {"today": today, "active": active, "parked": parked, "done": done}


def humanize_days(n):
    if n == 0:
        return "today"
    if n == 1:
        return "yesterday"
    if n < 14:
        return f"{n}d ago"
    if n < 60:
        return f"{n // 7}w ago"
    if n < 730:
        return f"{n // 30}mo ago"
    return f"{n // 365}y ago"


def fmt_gap(days):
    if days is None:
        return None
    days = round(days)
    if days <= 1:
        return "daily"
    if days < 14:
        return f"~{days}d"
    return f"~{round(days / 7)}w"
