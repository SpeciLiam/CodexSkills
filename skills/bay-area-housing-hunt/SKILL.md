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
2. Kick off the run (does safe headless capture + scoring, then prints the AI-capture plan to stderr). For scheduled runs, start from a clean scratch capture dir so stale browser captures cannot refresh `Last Seen`:

```bash
# Manual/default run
python3 skills/bay-area-housing-hunt/scripts/run.py

# Run only selected configured sources; default is all
python3 skills/bay-area-housing-hunt/scripts/run.py --sources craigslist zillow facebook
python3 skills/bay-area-housing-hunt/scripts/run.py --sources apartments.com
python3 skills/bay-area-housing-hunt/scripts/run.py --list-sources

# Scheduled-run kickoff
python3 skills/bay-area-housing-hunt/scripts/run.py --fresh-capture-dir
```

`run.py` runs the **headless** tiers in `scripts/searches.json` itself (no browser,
cloud/CI-ok): the `web` tier via `capture_web.py` — **Craigslist** (its own
`sapi.craigslist.org` JSON API; the legacy Craigslist RSS feed 403s so it's no
longer used), **Zumper** (embedded `__PRELOADED_STATE__`), **Redfin Rentals**
(schema.org ld+json on city pages), and **direct property managers** (UDR
`jsonObjPropertyViewModel`, Rent.com `__NEXT_DATA__`) — plus the `rss` tier
(**Reddit** `.rss` Atom search feeds, paced 45s apart because Reddit 429s bursts;
its public JSON endpoints 403 everywhere as of 2026-07-02) and the `apis` tier via
`capture_api.py` (keyed JSON endpoints such as RentCast, off by default). It then ingests every capture file in
`/tmp/codexskills-housing-hunt/`, rescores, and rebuilds the board. Add `--notion`
to mirror the ledger into Notion (no-op unless `housing-trackers/notion-config.md` +
`NOTION_TOKEN` are set). `stdout` is a clean JSON summary; the AI-capture plan goes
to `stderr`. A headless run already covers the bulk of the inventory (Craigslist +
Zumper) before any browser step.

Use `--sources` to select one or many configured sources; omitting it is the same
as `--sources all`. This works across every configured tier/source row, not just
the common examples: `craigslist`, `zumper`, `reddit`, `rentcast`, `facebook`,
`zillow`, `apartments.com`, `furnished`, labels like `sf-sublets`, and aliases or
minor typos like `cl`, `cragislist`, `fb`, and `faceb`. Source filtering affects
headless capture, the printed AI-browser plan, and the capture-dir JSON glob so old
scratch files from unselected sources do not sneak into a narrowed run. Use
`--list-sources` to print the currently selectable configured sources/tokens.
`--sources 5br` / `5plus` runs the Bay Area-wide 5+ bedroom sweep; use
`--sources sf5plus` for the narrower SF-only 5+ sweep.

3. Fulfil the AI-capture plan for the `ai_browser` tier only — sources that block
   headless reads and need a visible/signed-in browser. As of 2026-06-30 this is
   **Facebook Marketplace + groups** (login wall), **Zillow** (PerimeterX 403),
   **Apartments.com** (HTTP 403 to headless browser-like requests), and
   **Furnished Finder** (interactive map/search). For each, open the search and
   capture **visible facts only** into the JSON file it names, using the schema in
   `references/sources.md`:
   - **Codex**: Chrome plugin (Computer Use fallback).
   - **Claude**: Claude-in-Chrome / Computer Use.
   Never bypass CAPTCHA/login/rate limits, never message posters, never submit.
   The Listings Project and Kopa are currently retired/dead sources in
   `searches.json`; do not re-add them unless they relaunch a usable public search.
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

Offline / no-network rebuild (skip the headless fetch, just rescore from existing captures):

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
- Craigslist via its public `sapi.craigslist.org` JSON API (headless, no browser — see `capture_web.py`).
- Facebook Marketplace and housing groups through a visible signed-in browser using nodriver/Chrome plugin; capture only visible listing facts.
- Zillow/HotPads/Trulia, Apartments.com, Redfin Rentals, Realtor.com, Zumper/PadMapper, Rent.com, ApartmentGuide, ForRent, Apartment List, Roomies, SpareRoom, Furnished Finder, Airbnb monthly, Landing/Blueground, Reddit/community posts, and direct property managers.
- Curated sublease/coliving/community sources: PadSplit, Diggz, Anyplace/Outsite/June Homes, corporate/relocation housing, Blind/Nextdoor, and the SCU/Stanford off-campus boards. The Listings Project and Kopa remain useful concepts to watch, but are retired from automation until they relaunch usable public search. See `references/sources.md` for the full grouped list.

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
