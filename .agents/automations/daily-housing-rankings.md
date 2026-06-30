# Daily Housing Rankings

Automation: two **Claude scheduled tasks** run this local browser-capable workflow:
`housing-power-rankings-6h` at 0/6/12/18 and `housing-refresh-3h-offset` at
3/9/15/21. Together they refresh about every 3 hours while Claude Code is open
(otherwise on next launch). **Codex app currently has no housing cron**; Codex runs
the same flow manually by reading this prompt and running `scripts/run.py`.

Cloud backstop: `.github/workflows/housing-rankings-sync.yml` runs the headless
web/API tier every 6 hours only when `HOUSING_SYNC_ENABLED=true`. It cannot use the
logged-in browser tier and does not commit.

Manage/pause the local schedule from Claude's "Scheduled" sidebar. Task prompts live
at:

- `~/.claude/scheduled-tasks/housing-power-rankings-6h/SKILL.md`
- `~/.claude/scheduled-tasks/housing-refresh-3h-offset/SKILL.md`

Prompt:

```text
Use the bay-area-housing-hunt skill.

Task: refresh Liam's Bay Area housing power rankings for flexible subleases, month-to-month options, apartments, and strong commute/value candidates around the HackerRank Santa Clara office.

Setup:
1. Check `git status --short`; if the worktree has no conflicting tracked edits,
   run `git pull --ff-only origin main` (read-only sync; do not push).
2. Load the Notion token when available: `set -a; . ~/.config/codexskills/notion_token.env 2>/dev/null; set +a`.
3. Read `skills/bay-area-housing-hunt/references/preferences.md`, `sources.md`, and `power-rankings.md`.

Kickoff:
4. Run `python3 skills/bay-area-housing-hunt/scripts/run.py --fresh-capture-dir`.
   It clears old scratch JSON from `/tmp/codexskills-housing-hunt/`, then runs the
   safe headless tiers configured in `searches.json`: `web` via `capture_web.py`
   (Craigslist `sapi.craigslist.org` JSON + Zumper `__PRELOADED_STATE__`) and
   `apis` via `capture_api.py` (Reddit/free APIs where reachable, keyed APIs only
   when enabled). Craigslist RSS is intentionally unused because it 403s. `stdout`
   is a JSON summary; the AI-capture plan prints to `stderr`.
   Optional manual narrowing: add `--sources craigslist zillow facebook` (or any
   subset such as `--sources apartments.com`, `--sources zumper reddit`, etc.) to
   run/plan only those configured source rows. The scheduled default is all
   sources. Use `--list-sources` to see the selectable configured names/tokens.

Capture (fulfil the AI plan - go through every source the plan prints):
5. Capture every `ai_browser` source printed by the plan into the JSON file it
   names (schema in `references/sources.md`). As of 2026-06-30 this means
   Facebook Marketplace corridor rentals, Facebook housing groups, Zillow Rentals
   corridor, Apartments.com Rentals corridor, and Furnished Finder. Codex uses the
   Chrome plugin (Computer Use fallback); Claude uses Claude-in-Chrome / Computer Use. Do not hard-code the old
   12-source list: Craigslist and Zumper are now headless, while Kopa and The
   Listings Project are retired/dead sources unless they relaunch public search.
6. Do not bypass CAPTCHA, login walls, rate limits, or platform restrictions. If a
   source hard-blocks, write a Source Blocked capture row for that source and keep
   going. Do not message posters or submit applications.
7. Re-run `python3 skills/bay-area-housing-hunt/scripts/run.py --notion`
   (re-ingests the freshly captured scratch dir and re-syncs Notion).
8. Refresh the dashboard data with
   `python3 skills/bay-area-housing-hunt/scripts/export_housing_data.py`. Deploy
   with `cd housing-visualizer && vercel --prod --yes` only from the local scheduled
   task when Vercel auth is available; skip deployment in cloud/headless contexts
   and report that it was skipped.

Verify + status:
9. Verify every current top-5 listing and any `Needs Verification` row in a visible
   browser before recommending action.
10. Set statuses explicitly via `python3 skills/bay-area-housing-hunt/scripts/housing_pipeline.py --mark "STATUS=<url or key>"` (Expired/Unavailable/Duplicate/Rejected/Active). Never hand-edit the generated table; never delete rows.

Report:
11. Summarize markets refreshed, new top-5 entrants, rank movers, expired/replaced
    listings, best no-car options, best car-enabled options, Notion sync result,
    dashboard deploy URL or skip reason, and manual verification needs.
12. Do NOT commit or push. Leave the updated `housing-trackers/` files for Liam to review and commit manually.

Hard rules: no CAPTCHA/rate-limit/login bypass, no landlord messages without Liam approval, no deposits/applications submitted, no invented rents/addresses/availability, no commits or pushes, and do not touch unrelated recruiting files.
```
