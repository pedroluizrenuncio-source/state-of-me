"""State of Me - spotlight, not scoreboard.

  som                         sync sources, then show the picture
  som add "Name" -t coding --repo owner/repo [--deadline YYYY-MM-DD] [--goal "..."]
  som park NAME | retire NAME | activate NAME
  som set NAME [--repo ...|--no-repo] [--deadline ...] [--goal ...] [--type ...] [--name ...]
  som log NAME ["note"] [--date YYYY-MM-DD]   (for fronts with no real data source)
  som list [--all]   som sync [--full]   som show   som report [--open]
"""
import argparse
import datetime as dt
import os
import sys

from somlib import activity, github, registry, render_cli, render_html, server

REPORT_PATH = registry.ROOT / "report.html"


def _date(value):
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a YYYY-MM-DD date")


def _repo(value):
    try:
        return registry.normalize_repo(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def cmd_add(args, reg):
    status = "parked" if args.parked else "active"
    entry = registry.add(reg, args.name, args.type, args.repo, args.deadline, args.goal, status)
    registry.save(reg)
    print(f"Added '{entry['name']}' as {status} (id: {entry['id']}).")
    if entry["source"]:
        _sync_entries([entry])


def cmd_status(args, reg, status, verb):
    entry = registry.find(reg, args.entry)
    if registry.set_status(entry, status):
        registry.save(reg)
        print(f"{verb} '{entry['name']}'. Its history is kept.")
    else:
        print(f"'{entry['name']}' is already {status}.")


def cmd_set(args, reg):
    entry = registry.find(reg, args.entry)
    if args.name:
        entry["name"] = args.name
    if args.type:
        entry["type"] = args.type
    if args.repo:
        entry["source"] = {"kind": "github", "repo": args.repo}
    if args.no_repo:
        entry["source"] = None
    commitment = entry.setdefault("commitment", {})
    if args.deadline is not None:
        commitment["deadline"] = args.deadline or None
    if args.goal is not None:
        commitment["goal"] = args.goal or None
    registry.save(reg)
    print(f"Updated '{entry['name']}'.")
    if args.repo:
        _sync_entries([entry])


def cmd_log(args, reg):
    entry = registry.find(reg, args.entry)
    activity.append_log(entry["id"], args.note or "", args.date or registry.today_iso())
    print(f"Logged for '{entry['name']}' on {args.date or 'today'}.")
    if entry.get("source"):
        print("  (Kept as a note - this front has a real data source, so only that counts as activity.)")


def _sync_entries(entries, full=False):
    for line in github.sync_entries(entries, full=full):
        print(f"  {line}")


def cmd_sync(args, reg):
    # Done entries are left alone; parked ones still sync so last-touched stays true.
    _sync_entries([e for e in reg["entries"] if e["status"] != "done"], full=args.full)


def cmd_show(args, reg):
    print(render_cli.render(activity.build_view(reg)))


def cmd_report(args, reg):
    REPORT_PATH.write_text(render_html.render(activity.build_view(reg)), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")
    if args.open:
        os.startfile(REPORT_PATH)


def cmd_daily(args, reg):
    """Unattended run for Task Scheduler: sync, rewrite the report, log the outcome."""
    log_path = registry.DATA_DIR / "daily.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        sys.stdout = sys.stderr = log
        print(f"--- {dt.datetime.now():%Y-%m-%d %H:%M}")
        _sync_entries([e for e in reg["entries"] if e["status"] != "done"])
        args.open = False
        cmd_report(args, reg)


def main(argv=None):
    # Windows consoles/pipes may not default to UTF-8; the sparklines need it.
    # (Under pythonw there is no console at all, so stdout is None.)
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="som", description="State of Me - spotlight, not scoreboard.")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="add a new front")
    a.add_argument("name")
    a.add_argument("-t", "--type", choices=registry.TYPES, default="other")
    a.add_argument("--repo", type=_repo, help="GitHub owner/repo (or URL)")
    a.add_argument("--deadline", type=_date)
    a.add_argument("--goal")
    a.add_argument("--parked", action="store_true", help="add it as parked instead of active")

    for name, help_ in [("park", "move to the quiet parked list"),
                        ("retire", "mark done - drops out of the view, history kept"),
                        ("activate", "bring back into the active spotlight")]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("entry", help="id or (part of the) name")

    s = sub.add_parser("set", help="edit an entry")
    s.add_argument("entry")
    s.add_argument("--name")
    s.add_argument("-t", "--type", choices=registry.TYPES)
    s.add_argument("--repo", type=_repo)
    s.add_argument("--no-repo", action="store_true")
    s.add_argument("--deadline", type=lambda v: "" if v == "" else _date(v), help='YYYY-MM-DD, or "" to clear')
    s.add_argument("--goal", help='text, or "" to clear')

    lg = sub.add_parser("log", help="log manual activity (fronts without a data source)")
    lg.add_argument("entry")
    lg.add_argument("note", nargs="?")
    lg.add_argument("--date", type=_date)

    ls = sub.add_parser("list", help="list registry entries")
    ls.add_argument("--all", action="store_true", help="include done/retired")

    sy = sub.add_parser("sync", help="pull activity from data sources")
    sy.add_argument("--full", action="store_true", help="re-download history instead of incremental")

    sub.add_parser("show", help="show the picture (no sync)")
    r = sub.add_parser("report", help="write report.html")
    r.add_argument("--open", action="store_true", help="open it in the browser")
    sub.add_parser("daily", help="sync + report, logged to data/daily.log (for Task Scheduler)")
    sub.add_parser("app", help="open the interactive dashboard in your browser")

    args = p.parse_args(argv)
    reg = registry.load()
    try:
        match args.cmd:
            case None:
                _sync_entries([e for e in reg["entries"] if e["status"] != "done"])
                print()
                cmd_show(args, reg)
            case "add": cmd_add(args, reg)
            case "park": cmd_status(args, reg, "parked", "Parked")
            case "retire": cmd_status(args, reg, "done", "Retired")
            case "activate": cmd_status(args, reg, "active", "Activated")
            case "set": cmd_set(args, reg)
            case "log": cmd_log(args, reg)
            case "list": print(render_cli.render_list(reg, args.all))
            case "sync": cmd_sync(args, reg)
            case "show": cmd_show(args, reg)
            case "report": cmd_report(args, reg)
            case "daily": cmd_daily(args, reg)
            case "app": server.run()
    except LookupError as e:
        print(e.args[0], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
