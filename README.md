# State of Me

Spotlight, not scoreboard. Shows what you're actually working on, using real data where it exists,
and keeps everything else in a quiet parked list. No flags, no streaks.

## Daily use

```
som                 # sync sources, then show the picture
som report --open   # same picture as a local HTML page
```

## Maintaining the registry (the only manual part)

```
som add "Python practice" -t coding --repo owner/Python_practice
som add "Calculus II" -t course --deadline 2026-12-15 --goal "pass the final"
som log calc "chapter 4"          # fronts with no data source: log what you did
som park python                   # quiet list, history kept
som retire calc                   # done: out of the view, history kept
som activate python               # back into the spotlight
som set python --goal "finish the OOP module"
som list --all
```

Names can be any unambiguous part of the name or id. Types: coding, course, habit, fitness, other.

## How the signal works

- **Fronts with a source (GitHub):** only commits count. `som log` on these is kept as a note but never
  stands in for verified activity.
- **Fronts without a source:** shows exactly what you logged, labelled `self-logged`.
- **Rhythm:** the median gap between days you touched it over the last year (needs 4+ active days).
  The HTML report also shows the "normal long break" (80th percentile gap). This is the per-front
  baseline that later flagging will compare against.
- **Trend:** last 30 days vs the 30 before.
- Commits are counted on the repo's default branch, by author date, in your local time zone.

## Files

- `registry.json` - your fronts (hand-editable JSON)
- `data/github/*.json` - cached commits, fetched incrementally (`som sync --full` to rebuild)
- `data/manual_log.jsonl` - manual log lines
- `report.html` - generated report

## GitHub token

Create a fine-grained token (read-only, Contents + Metadata on the repos you track), then set it once:

```
[Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "<token>", "User")
```

Without it, public repos still work (60 requests/hour).
