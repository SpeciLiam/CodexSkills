# Daily Housing Rankings

Automation: two **Claude scheduled tasks** run this local browser-capable workflow
with SPLIT ROLES (since 2026-07-01):

- `housing-power-rankings-6h` at 0/6/12/18 — **Liam solo refresh**
  (`run.py --fresh-capture-dir --sources solo`): every lane EXCEPT the 5+ group
  lanes. Focus: rooms/studios/1bd flexible subleases, month-to-month, and strong
  commute/value candidates near the HackerRank Santa Clara office.
- `housing-refresh-3h-offset` at 3/9/15/21 — **Group SF 5+ refresh**
  (`run.py --fresh-capture-dir --sources group`): SF-only 5+ bedroom lanes for the
  5-person household at $2,650/person = $13,250/mo total (see
  `references/preferences.md`). Much lighter run; browser lanes are only
  Facebook SF 5+, Zillow SF 5+, and Apartments.com SF 5+.

`solo` + `group` partition the enabled lanes exactly (no overlap, full coverage);
`liam` is an alias for `solo`, and `group` aliases `sf5plus`. The 3-hour stagger
means neither lane goes long without a refresh while Claude Code is open
(otherwise on next launch). **Codex app currently has no housing cron**; Codex runs
either flow manually by reading this prompt and running `scripts/run.py` with the
matching `--sources` token.

Cloud backstop: `.github/workflows/housing-rankings-sync.yml` runs the headless
web/API tier every 6 hours only when `HOUSING_SYNC_ENABLED=true`. It cannot use the
logged-in browser tier and does not commit.

Manage/pause the local schedule from Claude's "Scheduled" sidebar. Task prompts live
at (kept in sync with the role split above):

- `~/.claude/scheduled-tasks/housing-power-rankings-6h/SKILL.md`
- `~/.claude/scheduled-tasks/housing-refresh-3h-offset/SKILL.md`

Shared workflow (both prompts follow this; only `--sources`, the browser-capture
scope, and the report focus differ):

```text
Setup:
1. Check `git status --short`; if the worktree has no conflicting tracked edits,
   run `git pull --ff-only origin main` (read-only sync; do not push).
2. Load the Notion token when available: `set -a; . ~/.config/codexskills/notion_token.env 2>/dev/null; set +a`.
3. Read `skills/bay-area-housing-hunt/references/preferences.md`, `sources.md`, and `power-rankings.md`.

Kickoff:
4. Run `python3 skills/bay-area-housing-hunt/scripts/run.py --fresh-capture-dir --sources <solo|group>`.
   It clears old scratch JSON from `/tmp/codexskills-housing-hunt/`, then runs the
   safe headless tiers configured in `searches.json` for the selected lanes: `web`
   via `capture_web.py` (Craigslist `sapi.craigslist.org` JSON + Zumper
   `__PRELOADED_STATE__` + property-manager JSON + Rent.com) and `apis` via
   `capture_api.py` (Reddit/free APIs where reachable, keyed APIs only when
   enabled). `stdout` is a JSON summary; the AI-capture plan prints to `stderr`.
   Use `--list-sources` to see selectable tokens.

Capture (fulfil the AI plan — go through every source the plan prints):
5. Capture every `ai_browser` source printed by the plan into the JSON file it
   names (schema in `references/sources.md`). Claude uses Claude-in-Chrome /
   Computer Use; Codex uses the Chrome plugin (Computer Use fallback).
6. Do not bypass CAPTCHA, login walls, rate limits, or platform restrictions. If a
   source hard-blocks, write a Source Blocked capture row for that source and keep
   going. Do not message posters or submit applications.
7. Re-run `python3 skills/bay-area-housing-hunt/scripts/run.py --notion --sources <solo|group>`
   (re-ingests the freshly captured scratch dir and re-syncs Notion).
8. Refresh the dashboard data with
   `python3 skills/bay-area-housing-hunt/scripts/export_housing_data.py`. Deploy
   with `cd housing-visualizer && vercel --prod --yes` only from the local scheduled
   task when Vercel auth is available; skip deployment in cloud/headless contexts
   and report that it was skipped.

Verify + status:
9. Verify the relevant current top-5 listings and any `Needs Verification` row in a
   visible browser before recommending action (solo run: overall/no-car/car boards;
   group run: SF 5+ rows only).
10. Set statuses explicitly via `python3 skills/bay-area-housing-hunt/scripts/housing_pipeline.py --mark "STATUS=<url or key>"` (Expired/Unavailable/Duplicate/Rejected/Active). Never hand-edit the generated table; never delete rows.

Report:
11. Solo run: markets refreshed, new top-5 entrants, rank movers, expired/replaced
    listings, best no-car options, best car-enabled options, Notion sync result,
    dashboard deploy URL or skip reason, and manual verification needs.
    Group run: new/changed SF 5+ listings with per-person price (rent ÷ 5 vs the
    $2,650 target), bed counts, term fit vs the 2026-07-16 need window, scam/verify
    flags, plus the same Notion/deploy/verification notes.
12. Do NOT commit or push. Leave the updated `housing-trackers/` files for Liam to review and commit manually.

Hard rules: no CAPTCHA/rate-limit/login bypass, no landlord messages without Liam approval, no deposits/applications submitted, no invented rents/addresses/availability, no commits or pushes, and do not touch unrelated recruiting files.
```
