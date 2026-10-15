"""Interactive dashboard: a tiny local web server (127.0.0.1 only) + one page.

`som app` starts it and opens the browser; if it's already running, it just
opens the browser. registry.json stays the single source of truth, so the CLI
and the app can be used side by side.
"""
import datetime as dt
import json
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import activity, github, registry
from .activity import deadline_days, fmt_gap, humanize_days

PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"
APP_HTML = Path(__file__).with_name("app.html")
_write_lock = threading.Lock()


# ---------- read side ----------

def _entry_json(entry, sig, today):
    c = entry.get("commitment") or {}
    days = deadline_days(entry, today)
    out = {
        "id": entry["id"],
        "name": entry["name"],
        "type": entry["type"],
        "status": entry["status"],
        "repo": entry["source"]["repo"] if entry.get("source") else "",
        "deadline": c.get("deadline") or "",
        "goal": c.get("goal") or "",
        "deadline_text": "" if days is None else (f"in {days}d" if days >= 0 else f"{-days}d ago"),
        "provenance": sig["provenance"],
        "has_data": sig["has_data"],
        "weekly": sig["weekly"],
        "notes": [{"date": n["date"], "note": n["note"]} for n in activity.manual_log(entry["id"])[-2:][::-1]],
    }
    if sig["has_data"]:
        out.update({
            "last": sig["last"].isoformat(),
            "last_human": humanize_days(sig["days_since"]),
            "count_30d": sig["count_30d"],
            "active_days_30d": sig["active_days_30d"],
            "trend": sig["trend"],
            "rhythm": fmt_gap(sig["typical_gap"]) or "",
            "long_break": fmt_gap(sig["long_gap"]) or "",
        })
    return out


def get_state():
    view = activity.build_view(registry.load())
    today = view["today"]
    return {
        "today_label": f"{today:%A, %d %B %Y}",
        "types": registry.TYPES,
        **{group: [_entry_json(e, s, today) for e, s in view[group]] for group in ("active", "parked", "done")},
    }


# ---------- write side ----------

def _date_or_none(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("Dates need to look like 2026-12-31.") from None


def _repo_or_none(value):
    value = (value or "").strip()
    return registry.normalize_repo(value) if value else None


def _find(reg, entry_id):
    for e in reg["entries"]:
        if e["id"] == entry_id:
            return e
    raise LookupError("That entry no longer exists - refresh the page.")


def _type(value):
    if value not in registry.TYPES:
        raise ValueError(f"Type must be one of: {', '.join(registry.TYPES)}.")
    return value


def api_add(body):
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("Give it a name.")
    repo = _repo_or_none(body.get("repo"))
    reg = registry.load()
    entry = registry.add(reg, name, _type(body.get("type") or "other"), repo,
                         _date_or_none(body.get("deadline")), (body.get("goal") or "").strip() or None)
    registry.save(reg)
    return {"name": entry["name"], "messages": github.sync_entries([entry]) if repo else []}


def api_status(body):
    status = body.get("status")
    if status not in registry.STATUSES:
        raise ValueError("Unknown status.")
    reg = registry.load()
    entry = _find(reg, body.get("id"))
    previous = entry["status"]
    registry.set_status(entry, status)
    registry.save(reg)
    return {"name": entry["name"], "previous": previous}


def api_log(body):
    reg = registry.load()
    entry = _find(reg, body.get("id"))
    note = (body.get("note") or "").strip()
    activity.append_log(entry["id"], note, _date_or_none(body.get("date")) or registry.today_iso())
    return {"name": entry["name"], "counts": not entry.get("source")}


def api_edit(body):
    reg = registry.load()
    entry = _find(reg, body.get("id"))
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("Name can't be empty.")
    repo = _repo_or_none(body.get("repo"))
    old_repo = entry["source"]["repo"] if entry.get("source") else None
    entry["name"] = name
    entry["type"] = _type(body.get("type") or entry["type"])
    entry["source"] = {"kind": "github", "repo": repo} if repo else None
    entry["commitment"] = {"deadline": _date_or_none(body.get("deadline")),
                           "goal": (body.get("goal") or "").strip() or None}
    registry.save(reg)
    messages = github.sync_entries([entry]) if repo and repo != old_repo else []
    return {"name": entry["name"], "messages": messages}


def api_sync(body):
    reg = registry.load()
    return {"messages": github.sync_entries([e for e in reg["entries"] if e["status"] != "done"])}


ROUTES = {"/api/add": api_add, "/api/status": api_status, "/api/log": api_log,
          "/api/edit": api_edit, "/api/sync": api_sync}


# ---------- HTTP plumbing ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # no console under pythonw

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _trusted(self):
        # Reject requests addressed to any other hostname (DNS-rebinding guard).
        return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._trusted():
            return self._send(403, {"error": "forbidden"})
        if self.path in ("/", "/index.html"):
            return self._send(200, APP_HTML.read_bytes(), "text/html")
        if self.path == "/api/state":
            return self._send(200, get_state())
        if self.path == "/api/ping":
            return self._send(200, {"app": "state-of-me"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        # Requiring a JSON body means other websites can't post here from your browser.
        if not self._trusted() or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send(403, {"error": "forbidden"})
        handler = ROUTES.get(self.path)
        if not handler:
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            with _write_lock:
                result = handler(body)
            self._send(200, result)
        except (LookupError, ValueError) as e:
            self._send(400, {"error": e.args[0] if e.args else "Bad request."})


def is_running():
    try:
        with urllib.request.urlopen(URL + "api/ping", timeout=1) as resp:
            return json.load(resp).get("app") == "state-of-me"
    except Exception:
        return False


def run(open_browser=True):
    if is_running():
        if open_browser:
            webbrowser.open(URL)
        return
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    if open_browser:
        threading.Timer(0.3, webbrowser.open, [URL]).start()
    server.serve_forever()
