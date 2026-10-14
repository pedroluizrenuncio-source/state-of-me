"""The manual registry: your current "fronts", curated by hand.

Stored as registry.json next to som.py. Retiring or parking an entry only
changes its status - nothing is ever deleted, so history stays intact.
"""
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "registry.json"
DATA_DIR = ROOT / "data"

TYPES = ["coding", "course", "habit", "fitness", "other"]
STATUSES = ["active", "parked", "done"]


def today_iso():
    return dt.date.today().isoformat()


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "entry"


def normalize_repo(value):
    """Accept 'owner/repo' or a github.com URL; return 'owner/repo'."""
    value = value.strip().removesuffix(".git").rstrip("/")
    value = re.sub(r"^(https?://)?(www\.)?github\.com/", "", value)
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", value):
        raise ValueError(f"'{value}' is not an owner/repo path (e.g. octocat/hello-world)")
    return value


def load():
    if not REGISTRY_PATH.exists():
        return {"version": 1, "entries": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save(reg):
    # Write to a temp file first so a crash can't leave a half-written registry.
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(REGISTRY_PATH)


def find(reg, key):
    """Look up an entry by id, exact name, or an unambiguous partial match."""
    key_l = key.lower()
    entries = reg["entries"]
    for e in entries:
        if e["id"] == key_l or e["name"].lower() == key_l:
            return e
    matches = [e for e in entries if e["id"].startswith(slugify(key)) or key_l in e["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LookupError(f"No entry matches '{key}'. Try `som list --all`.")
    raise LookupError(f"'{key}' matches several entries: " + ", ".join(e["id"] for e in matches))


def add(reg, name, type_, repo=None, deadline=None, goal=None, status="active"):
    taken = {e["id"] for e in reg["entries"]}
    base = slugify(name)
    entry_id, n = base, 2
    while entry_id in taken:
        entry_id, n = f"{base}-{n}", n + 1
    entry = {
        "id": entry_id,
        "name": name,
        "type": type_,
        "status": status,
        "source": {"kind": "github", "repo": repo} if repo else None,
        "commitment": {"deadline": deadline, "goal": goal},
        "created": today_iso(),
        "history": [{"date": today_iso(), "status": status}],
    }
    reg["entries"].append(entry)
    return entry


def set_status(entry, status):
    """Change status and record when it happened. Returns False if unchanged."""
    if entry["status"] == status:
        return False
    entry["status"] = status
    entry.setdefault("history", []).append({"date": today_iso(), "status": status})
    return True
