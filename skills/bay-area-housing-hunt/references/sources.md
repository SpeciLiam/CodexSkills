# Housing Sources

## Capture Priority

1. Saved alerts and structured feeds.
2. Official property manager pages and apartment community pages.
3. Public listing pages that can be read without login friction.
4. Visible logged-in browser capture for Facebook Marketplace and groups.
5. Manual review for blocked/high-friction sources.

## Source List

### Flexible / sublease / room sources (highest priority)

- Facebook Marketplace rentals.
- Facebook housing/sublet groups, e.g. "Bay Area Housing, Rooms, Sublets & Roommates", "SF Housing, Rooms, Apartments, Sublets & Roommates", "Gypsy Housing Bay Area", and tech-worker housing groups.
- Craigslist `apa`, `sub`, `roo`, and the relevant Bay Area subareas (`sby` South Bay, `pen` Peninsula, `sfc` SF).
- The Listings Project / The Listing Project (watch only for now: automation retired
  2026-06-29 because public pages resolved to parked/subscription-only surfaces).
- Kopa (watch only for now: automation retired 2026-06-29 because the service
  showed a shutdown/wind-down notice and no live public search).
- Diggz and SpareRoom (roommate/room matching); treat Roomies/Roomster listings with extra scam caution.
- PadSplit (room-by-room, lower-cost).
- Furnished Finder (monthly furnished; travel-nurse stock but flexible terms).
- Reddit housing threads (r/bayarea, r/sanfrancisco, r/sanjose, r/AskSF) and Nextdoor posts where allowed.
- Blind (teamblind) tech-worker sublease/housing threads.

### Coliving and furnished monthly

- Airbnb monthly and VRBO monthly.
- Landing, Blueground, Anyplace, Outsite, June Homes.
- Kasa, Sonder, Mint House and similar aparthotel monthly stays.
- Bungalow / HomeRoom-style coliving where available in the South Bay/SF.

### Corporate and relocation housing (use the one-time relocation support)

- HackerRank's assigned relocation vendor / temporary-housing partner — ask before signing anything.
- Oakwood/Mavik, National Corporate Housing, BridgeStreet, Synergy corporate housing.

### Main apartment / listing sources

- Zillow Rentals, HotPads, Trulia.
- Apartments.com, Apartment List, Rent.com, ApartmentGuide, ForRent.
- Redfin Rentals and Realtor.com rentals.
- Zumper and PadMapper.

### Direct property managers and near-office communities

- AvalonBay, Equity Residential, Essex, Prometheus, Greystar, UDR, Irvine Company, Windsor, Sares Regis, Woodmont, Hanover, Fairfield, Camden, Trinity SF, Veritas-style SF managers, and building-specific sites near Caltrain/VTA.
- Large Santa Clara/Sunnyvale communities near the office (e.g. Irvine Company's Santa Clara Square, Avalon Santa Clara, Domain, Centerra, Nineteen800, Mosso, Verandas, Mio, NorthPark) — verify current names/availability on each site.

### Community and employer channels

- HackerRank internal employee Slack/housing channel and employee sublet/referral leads — ask Liam to surface these once onboarded; often the highest-signal, lowest-scam source.
- Santa Clara University off-campus housing board (SCU is in Santa Clara, minutes from the office) and Stanford R&DE off-campus/sublet board.

### Transit and commute data

- Caltrain GTFS/developer resources and the weekday (Mon/Wed/Thu) timetable.
- VTA GTFS, plus the Orange Line and the Mission College/Great America bus and shuttle stops.
- 511 Bay Area transit data and the 511.org trip planner.
- Google Maps directions (transit and drive) timed to the actual Mon/Wed/Thu morning peak, and a door-to-door app (Transit/Citymapper) for short-list verification.
- Ask about a Caltrain Go Pass / commuter benefit and any company shuttle.

## Browser Rules

Use the local nodriver MCP or Chrome plugin for visible browsing. Capture facts from visible pages: title, price, location, URL, photos count if visible, availability, lease terms, listed date, poster/building, and notes.

### Access policy (Liam's personal search)

Scraping public/free data for Liam's own move is fine. Sources fall into three
capture tiers (configured in `searches.json`; reachability re-probed 2026-06-28 with
a realistic desktop-Chrome UA). Prefer the highest tier a source supports:

- **Free + headless `web` (cloud/CI-ok) — `capture_web.py`:** sites that serve their
  own PUBLIC JSON/SSR data to a normal browser request. We identify as a browser and
  read the public response — this is **not** a CAPTCHA/login/rate-limit bypass; on any
  403/429/challenge we record `Source Blocked` and stop.
  - **Craigslist** → its own `sapi.craigslist.org` v8 JSON search API. (The legacy RSS
    feed 403s even with a browser UA, so Craigslist no longer uses the `rss` tier.)
    Posting ids are delta-encoded: real id = `decode.minPostingId + item[0]`; the
    canonical post URL is rebuilt from subarea/category/slug/id. All 5–6 CL searches
    run here with **no browser** — this is the bulk of the inventory. The 5+ bedroom
    sweep covers SF, South Bay, Peninsula, and East Bay, and the pipeline re-buckets
    explicit city spillover instead of treating every SF-section result as SF.
  - **Zumper** → the `__PRELOADED_STATE__` blob in the search page (apartment-complex
    rent ranges + beds + url). The 5+ sweep includes SF, South Bay, Peninsula, and
    Oakland/Berkeley paths where public SSR data is available.
- **Free + headless JSON `apis` — `capture_api.py`:** keyless/keyed JSON endpoints.
  - **Reddit** is best-effort: it returns 403 to plain UAs from datacenter IPs (no UA
    variant helped in probing). It works from a **residential IP** (the local scheduled
    run) or with a free Reddit **OAuth** app token; until then cloud/CI runs log it
    `Source Blocked`.
  - **RentCast / RapidAPI wrappers:** optional, off by default; enable via key env var.
    Free tiers only unless Liam opts into paying.
- **Visible/logged-in browser `ai_browser`:** sources that genuinely block headless
  reads. Captured with the **local real signed-in browser** (Claude-in-Chrome /
  Computer Use / Chrome plugin). Current configured status:
  - **Facebook Marketplace + groups** → login wall (headless 400 / login redirect).
  - **Zillow** → PerimeterX anti-bot (headless 403); no keyless JSON path.
    For SF 5+ specifically, the 2026-07-01 Chrome probe found that
    `/san-francisco-ca/rentals/5-_beds/` loaded unfiltered listings, while the UI's
    5+ beds state generated a `beds.min=5` URL that triggered Zillow's human
    verification. Capture Zillow 5+ only after the real browser loads the exact
    result set without that challenge.
  - **Apartments.com** → headless HTTP 403 with a realistic desktop-Chrome UA in
    the 2026-06-30 probe; capture visible listing cards in a real browser. For SF
    5+, the route may show a 4+ heading; scrape visible `article[data-listingid]`
    cards and keep only cards whose visible bed text is 5 or higher. The 2026-07-01
    Chrome probe found 34 cards and 9 verified SF 5+ rows.
  - **Furnished Finder** → no reliable keyless public JSON path; current site is an
    interactive map/search and needs manual visible-browser capture.
- **Retired/watch-only sources:** do not re-add unless they relaunch a usable public
  search.
  - **The Listings Project / The Listing Project** → public web paths were parked or
    subscription-only in the 2026-06-29 browser probe.
  - **Kopa** → public site showed a shutdown/wind-down notice in the 2026-06-29
    browser probe.

Do NOT try to defeat the `ai_browser` sources headlessly — use the local browser.

Still off-limits (these are not about access, they're about conduct):

- Do not build CAPTCHA-solvers, proxy rotation, fake-account generation, or stealth
  evasion into this repo — it's futile for free and a maintenance trap; use the local
  browser instead.
- Do not message landlords or posters without Liam's approval.
- Do not submit applications or pay deposits automatically.
- Do not store unnecessary personal data from individual posters.

If a source blocks automation, record `Source Blocked` with the exact reason and fall
back to the local browser or saved email alerts.

## Capture Format

Scripts accept JSON arrays or objects containing a `listings`, `results`, `items`, or `data` array. Prefer these fields:

```json
{
  "source": "Facebook Marketplace",
  "title": "Furnished Mission sublease near 22nd St Caltrain",
  "url": "https://...",
  "city": "San Francisco",
  "neighborhood": "Mission",
  "address": "optional",
  "rent": "$3,200",
  "bedrooms": "1",
  "bathrooms": "1",
  "lease": "month-to-month",
  "available": "2026-07-15",
  "description": "furnished sublease, utilities included",
  "posted": "2 hours ago",
  "contact": "manual review"
}
```

Never invent missing fields. Leave blank and let scoring penalize uncertainty. A
classifieds title that leads with the price (e.g. `$2,400 / 1br …`) is fine to
capture as-is — the pipeline reads the visible leading `$` amount.

Extra fields the pipeline understands:

- `rent`/`price` (base rent) and `all_in`/`monthly_total` are read separately, so
  send both when the listing distinguishes them — the base-vs-all-in spread is kept.
- `status`: pass a hint like `expired`, `unavailable`, `pending`, `duplicate`,
  `rejected`, or `source blocked` and the pipeline routes the row to the right lane.

Orchestration:

- `scripts/run.py` is the kickoff. It reads `scripts/searches.json` and runs the
  headless tiers itself — `capture_web.py` (`web`: Craigslist sapi + Zumper) and
  `capture_api.py` (`apis`: Reddit etc.) — then ingests every JSON in the capture dir
  and rebuilds the board. With the `web` tier, a fully headless run (cloud/CI, no
  browser) already covers Craigslist + Zumper.
- `--sources 5br` / `5plus` now selects every configured 5+ lane across all tiers.
  Use `--sources sf5plus` for the narrower SF-only sweep.
- Old `ai-*.json` files discovered by capture-dir glob are skipped after 18 hours so
  stale browser captures cannot refresh `Last Seen`. Explicit `--input ai-...json`
  still replays a file intentionally; `--allow-stale-captures` exists for rare audits.
- For the `ai_browser` tier only, the conductor (Codex Chrome plugin /
  Claude-in-Chrome / Computer Use) writes one JSON array per source into the capture
  dir, then re-runs `run.py`. `run.py` prints the exact plan for these to stderr.
