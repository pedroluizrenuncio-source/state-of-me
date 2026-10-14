"""GitHub commit-activity puller (official REST API, no scraping).

Commits are cached per repo in data/github/<owner>__<repo>.json and fetched
incrementally, so daily runs only ask GitHub for what's new.

Auth: set the GITHUB_TOKEN environment variable to a read-only fine-grained
token. Without it, public repos still work at 60 requests/hour.
"""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from .registry import DATA_DIR

API = "https://api.github.com"
CACHE_DIR = DATA_DIR / "github"
MAX_PAGES = 30  # 3000 commits on a first sync is plenty for cadence purposes


class GitHubError(Exception):
    pass


def _get(url, token):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "state-of-me",
    })
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp), resp.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        if e.code == 409:  # repository exists but has no commits yet
            return [], ""
        if e.code == 404:
            raise GitHubError("repo not found (typo, or private and no GITHUB_TOKEN)") from None
        if e.code == 401:
            raise GitHubError("GITHUB_TOKEN was rejected (expired or mistyped?)") from None
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubError("GitHub rate limit reached - set GITHUB_TOKEN or try later") from None
        raise GitHubError(f"GitHub returned HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise GitHubError(f"network problem: {e.reason}") from None


def _next_link(link_header):
    m = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    return m.group(1) if m else None


def cache_path(repo):
    return CACHE_DIR / (repo.replace("/", "__") + ".json")


def load_cache(repo):
    path = cache_path(repo)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def sync_repo(repo, full=False, token=None):
    """Fetch new commits on the default branch; returns number of new commits."""
    token = token if token is not None else os.environ.get("GITHUB_TOKEN")
    cache = None if full else load_cache(repo)
    known = {c["sha"]: c for c in cache["commits"]} if cache else {}

    params = {"per_page": 100}
    if known:
        # Re-ask from the newest known commit; duplicates are dropped by sha.
        params["since"] = max(c["date"] for c in known.values())
    url = f"{API}/repos/{repo}/commits?" + urllib.parse.urlencode(params)

    new = 0
    for _ in range(MAX_PAGES):
        page, link = _get(url, token)
        for item in page:
            if item["sha"] in known:
                continue
            commit = item["commit"]
            known[item["sha"]] = {
                "sha": item["sha"],
                # Author date = when the work was written, not when it was pushed.
                "date": commit["author"]["date"],
                "message": commit["message"].splitlines()[0][:100] if commit["message"] else "",
            }
            new += 1
        url = _next_link(link)
        if not url:
            break

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    commits = sorted(known.values(), key=lambda c: c["date"], reverse=True)
    cache_path(repo).write_text(json.dumps({
        "repo": repo,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commits": commits,
    }, indent=1) + "\n", encoding="utf-8")
    return new


def commit_dates(repo):
    """Local calendar dates of every cached commit (one per commit)."""
    cache = load_cache(repo)
    if not cache:
        return []
    return [
        dt.datetime.fromisoformat(c["date"].replace("Z", "+00:00")).astimezone().date()
        for c in cache["commits"]
    ]
