# Daily Housing Rankings

Automation: a **Claude scheduled task** `housing-power-rankings-6h` runs this every
6 hours (cron `0 */6 * * *`, local time) inside the Claude Code app — so it can do
the browser/AI capture that needs a logged-in Chrome. Runs only while the app is
open (otherwise on next launch). **Codex runs the same flow manually** by reading
this prompt and running `scripts/run.py`. Manage/pause the schedule from the
"Scheduled" sidebar; the task file lives at
`~/.claude/scheduled-tasks/housing-power-rankings-6h/SKILL.md`.

Prompt:

```text
Use the bay-area-housing-hunt skill.

Task: refresh Liam's Bay Area housing power rankings for flexible subleases, month-to-month options, apartments, and strong commute/value candidates around the HackerRank Santa Clara office.

Setup:
1. `git pull --ff-only origin main` (read-only sync; do not push).
2. Read `skills/bay-area-housing-hunt/references/preferences.md`, `sources.md`, and `power-rankings.md`.

Kickoff:
3. Run `python3 skills/bay-area-housing-hunt/scripts/run.py --notion`. It creates the capture dir, does the safe headless capture (Craigslist RSS + Reddit/free JSON APIs in `searches.json`), ingests any existing captures, rescores, rebuilds the board, and mirrors the ledger into Notion when `housing-trackers/notion-config.md` + `NOTION_TOKEN` are set (no-op otherwise). `stdout` is a JSON summary; the AI-capture plan prints to `stderr`.

Capture (fulfil the AI plan — go through ALL sources):
4. Capture EVERY source the plan prints (all 12: Craigslist South Bay rooms/sublets/apartments, Craigslist SF sublets, Craigslist Peninsula sublets, Facebook Marketplace, Facebook housing groups, The Listing Project, Zillow, Kopa, Furnished Finder, Zumper) into the JSON file each names (schema in `references/sources.md`). Codex uses the Chrome plugin (Computer Use fallback); Claude uses Claude-in-Chrome / Computer Use. The browser playbook (Craigslist `.cl-search-result` selectors, the `<pre>@@BEGIN@@…@@END@@</pre>` + get_page_text trick for output truncation, and the Facebook set-location-to-Santa-Clara steps) is in the `_ai_browser_comment` of `scripts/searches.json`. This browser pass is REQUIRED — Craigslist RSS always 403s headlessly, so it's the only path listings reach the board.
5. Do not bypass CAPTCHA, login walls, rate limits, or platform restrictions. If a source hard-blocks, record it Source Blocked and continue the rest. Do not message posters or submit applications.
6. Re-run `python3 .../run.py --notion` (re-ingests the whole capture dir and re-syncs Notion).

Verify + status:
7. Verify every current top-5 listing and any `Needs Verification` row in a visible browser before recommending action.
8. Set statuses explicitly via `python3 .../housing_pipeline.py --mark "STATUS=<url or key>"` (Expired/Unavailable/Duplicate/Rejected/Active). Never hand-edit the generated table; never delete rows.

Report:
9. Summarize markets refreshed, new top-5 entrants, rank movers, expired/replaced listings, best no-car options, best car-enabled options, and manual verification needs.
10. Do NOT commit or push. Leave the updated `housing-trackers/` files for Liam to review and commit manually.

Hard rules: no CAPTCHA/rate-limit/login bypass, no landlord messages without Liam approval, no deposits/applications submitted, no invented rents/addresses/availability, no commits or pushes, and do not touch unrelated recruiting files.
```
