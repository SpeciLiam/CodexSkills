---
name: bay-area-housing-hunt
description: Find, normalize, score, and maintain Liam Van's Bay Area housing search around the HackerRank Santa Clara office. Use when Liam asks to search Bay Area housing, scrape or review Facebook Marketplace/Craigslist/apartment listings, compare SF neighborhoods or Peninsula/South Bay cities, compute commute and car scenarios, refresh daily top-5 power rankings by city/neighborhood, mark expired listings, or manage housing automation/tracker files.
---

# Bay Area Housing Hunt

## Overview

Maintain a daily, ranked Bay Area housing board rather than a raw pile of listings. Optimize for flexible subleases/month-to-month options first, commute to HackerRank's Santa Clara office second, and all-in value third.

## Sources Of Truth

- Canonical listing ledger: `housing-trackers/listings.md`
- Daily power rankings: `housing-trackers/power-rankings.md`
- Capture scratch files: `/tmp/codexskills-housing-hunt/`
- Automation runbook: `.agents/automations/daily-housing-rankings.md`
- Preferences and budget: `references/preferences.md`
- Source rules: `references/sources.md`
- Ranking UX contract: `references/power-rankings.md`
- Notion mirror (optional, downstream): `housing-trackers/notion-config.md` (database id; token is `NOTION_TOKEN`, never committed)

Markdown trackers are authoritative. Do not delete expired listings from the ledger; mark them `Expired`, `Unavailable`, `Duplicate`, `Rejected`, or `Stale` and let the rankings board move them to the expired/replaced lane.

## First Read

Read these selectively:

- Read `references/preferences.md` before scoring, budgeting, or deciding whether SF/sublease/car tradeoffs make sense.
- Read `references/sources.md` before scraping, opening logged-in sites, or configuring a capture automation.
- Read `references/power-rankings.md` before changing tracker columns or digest format.

## Default Workflow

One kickoff script orchestrates the daily run. It is agent-agnostic — the same
script and files work whether Claude or Codex is the conductor.

1. Check `git status --short` and avoid unrelated changes.
2. Kick off the run (does safe headless capture + scoring, then prints the AI-capture plan to stderr):

```bash
python3 skills/bay-area-housing-hunt/scripts/run.py
```

`run.py` fetches the headless free sources in `scripts/searches.json` — Craigslist
RSS plus Reddit / free JSON APIs via `capture_api.py` (any block is recorded as
`Source Blocked`) — ingests every capture file in `/tmp/codexskills-housing-hunt/`,
rescores, and rebuilds the board. Add `--notion` to also mirror the ledger into
Notion (no-op unless `housing-trackers/notion-config.md` + `NOTION_TOKEN` are set).
`stdout` is a clean JSON summary; the AI-capture plan goes to `stderr`.

3. Fulfil the AI-capture plan. For each dynamic/logged-in source it lists, open
   the search and capture **visible facts only** into the JSON file it names,
   using the schema in `references/sources.md`:
   - **Codex**: Chrome plugin (Computer Use fallback).
   - **Claude**: Claude-in-Chrome / Computer Use.
   Never bypass CAPTCHA/login/rate limits, never message posters, never submit.
4. Re-run with the AI captures: `python3 .../run.py --input <ai-*.json ...>`
   (or just re-run `run.py` — it re-ingests everything in the capture dir).
5. Verify every current top-5 and any `Needs Verification` row in a visible
   browser before recommending a tour/contact.
6. Set statuses explicitly (never hand-edit the generated table):

```bash
python3 skills/bay-area-housing-hunt/scripts/housing_pipeline.py \
  --mark "Rejected=https://…"  --mark "Unavailable=<listing key>"
```

7. Report: new top-5 entrants, rank movers, expirations, best no-car / car-enabled
   options, and what still needs manual verification.

Offline / no-network rebuild (skip the RSS fetch, just rescore from existing captures):

```bash
python3 skills/bay-area-housing-hunt/scripts/run.py --no-network
python3 skills/bay-area-housing-hunt/scripts/housing_pipeline.py --refresh-only
```

The engine never deletes rows: re-capturing a listing you marked `Rejected` or
`Duplicate` keeps that decision (it will not silently flip back to `Active`).
Add your own prose to `listings.md` only OUTSIDE the generated block.

## Capture Rules

Prefer structured or alert-based sources first, then visible browser capture:

- Gmail listing alerts and saved-search emails.
- Official/public property-manager pages.
- Craigslist saved searches/RSS-style captures when available.
- Facebook Marketplace and housing groups through a visible signed-in browser using nodriver/Chrome plugin; capture only visible listing facts.
- Zillow/HotPads/Trulia, Apartments.com, Redfin Rentals, Realtor.com, Zumper/PadMapper, Rent.com, ApartmentGuide, ForRent, Apartment List, Roomies, SpareRoom, Furnished Finder, Airbnb monthly, Landing/Blueground, Reddit/community posts, and direct property managers.
- Curated sublease/coliving/community sources: The Listing Project, Kopa, PadSplit, Diggz, Anyplace/Outsite/June Homes, corporate/relocation housing, Blind/Nextdoor, and the SCU/Stanford off-campus boards. See `references/sources.md` for the full grouped list.

Never add CAPTCHA bypass, login bypass, rate-limit bypass, proxy rotation, or stealth-circumvention code. If a site blocks automation, use saved alerts, manual browser review, or mark the source blocked.

## Ranking Contract

The primary user-facing output is the daily power rankings board:

- Keep exactly the top 5 active listings per city/neighborhood market when at least 5 active candidates exist.
- Preserve rank movement with `New`, `+N`, `-N`, `Same`, or `Re-entered`.
- Keep expired/unavailable listings in a separate expired/replaced section with the date and reason.
- Include a short reason cell explaining why each listing ranks there.
- Track car scenario separately from transit/walk/bike commute so Liam can compare "no car SF/Peninsula" against "car-enabled South Bay".
- Flag missing rent/address/lease/availability fields instead of inventing them.

## Budget Defaults

Use recurring base salary for rent decisions. Do not rely on variable compensation or one-time relocation money to make monthly rent work.

- Sweet spot for solo/flexible housing: about `$3,000-$3,750` monthly all-in.
- Stretch for a very strong solo option: about `$4,200-$4,500` all-in.
- Room/sublease target: about `$1,600-$2,800`, with higher tolerance for prime SF/Peninsula month-to-month flexibility.
- Car scenario: subtract an estimated `$800-$1,200` monthly from housing capacity unless employer parking or very low car costs are confirmed.

See `references/preferences.md` for details.

## Notion Mirror (optional)

`run.py --notion` (or `scripts/sync_housing_to_notion.py` directly) upserts every
ledger row into a Notion database keyed by `Listing Key` — carrying overall/city
power rank, commute minutes + "how to get there", rent, status, source, and notes.
Re-syncs update rows in place (no duplicates).

- DB id lives in `housing-trackers/notion-config.md`; the token is `NOTION_TOKEN`
  (stored outside the repo, e.g. `~/.config/codexskills/notion_token.env`).
- To (re)create the database with the full schema: `scripts/notion_setup.py`.
- For the cloud GitHub Actions job, set `NOTION_TOKEN` as a repo secret and the repo
  variable `HOUSING_SYNC_ENABLED=true`.

## Final Report

Report:

- markets refreshed
- active listings ingested
- new top-5 entrants
- expirations/unavailable listings
- strongest top 5 overall
- best SF options if any remain commute-reasonable
- best no-car options
- best car-enabled options
- files changed
- blockers from source access or missing data
