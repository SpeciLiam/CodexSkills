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
    canonical post URL is rebuilt from subarea/category/slug/id. The enabled 5+
    Craigslist group-house sweep is SF-only as of 2026-07-01, capped at $13,250/mo
    for 5 people. It includes the `min_bedrooms=5` bucket plus separate SF `apa` and
    `sub` keyword lanes for `5 bedroom`, `5br`, `6 bedroom`, `6br`, and `7 bedroom`
    because posters sometimes omit Craigslist's bedroom field. Title-derived bed
    extraction requires an explicit bedroom token and avoids price/bath bleed.
  - **Zumper** → the `__PRELOADED_STATE__` blob in the search page (apartment-complex
    rent ranges + beds + url). The enabled 5+ group-house lane is SF-only as of
    2026-07-01 and capped at $13,250/mo; prior South Bay, Peninsula, and East Bay
    5+ paths remain disabled in `searches.json` for possible re-enable later.
  - **Direct property managers (`pm`)** → only where the public community page embeds
    real availability state for a normal browser GET. Added 2026-07-01:
    **UDR River Terrace**, **UDR Marina Playa**, and **UDR Birch Creek** via
    `window.udr.jsonObjPropertyViewModel` on the public apartments-pricing pages
    (floorplan/unit rent, beds/baths, availability date, and page lat/lng).
  - **Rent.com** → public search pages expose `__NEXT_DATA__` with listing/floorplan
    rent, beds/baths, availability date, and coordinates. Added 2026-07-01 for
    Santa Clara, Sunnyvale, Mountain View, and Palo Alto corridor pages. SF 5+
    probe on 2026-07-01 tried likely public paths including
    `/california/san-francisco-apartments/5-bedroom` and query-filter variants; they
    returned public HTML without clean `__NEXT_DATA__`, so no SF 5+ Rent.com lane was
    added. A 2026-07-09 full-city fallback produced 60 studio-2bd floorplans across
    only three property URLs and zero 5+ rows, so that experimental lane remains
    disabled. The adapter now honors `min_bedrooms` and keeps explicit floorplan
    identities instead of collapsing every floorplan onto the building URL.
- **Free + headless JSON `apis` — `capture_api.py`:** keyless/keyed JSON endpoints.
  - **Reddit JSON is retired (2026-07-02):** the public `.json` endpoints now 403
    even from a residential IP (probed www/old/api hosts, multiple UAs). Reddit
    moved to the `rss` tier: the public **`.rss` Atom feeds** still serve search
    results per subreddit. They 429 on back-to-back requests, so `run.py` spaces
    RSS fetches 45s apart and honors one `Retry-After` per feed — polite pacing
    within the published limit, never a bypass; a second 429 records
    `Source Blocked`. As of 2026-07-09 the RSS adapter keeps only recent
    offer-shaped titles (sublet, lease takeover, room/home available, or a
    specific group-house roommate offer) inside a 21-day window. General advice,
    policy/news, moving sales, tickets, car rentals, and housing seekers no longer
    enter the ranked ledger; legacy noise is marked `Rejected` on refresh.
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
  - **HotPads** → headless HTTP 403 in the 2026-07-01 probe with a realistic
    desktop-Chrome UA; do not fight it.
  - **Apartment List** → 2026-07-01 probe returned public HTML but no
    `__PRELOADED_STATE__` / `__NEXT_DATA__` / equivalent clean listing state for the
    Santa Clara search page; no handler added.
- **Retired/watch-only sources:** do not re-add unless they relaunch a usable public
  search.
  - **The Listings Project / The Listing Project** → public web paths were parked or
    subscription-only in the 2026-06-29 browser probe.
  - **Kopa** → public site showed a shutdown/wind-down notice in the 2026-06-29
    browser probe.

2026-07-02 probe notes (new-source sweep):

- **Redfin Rentals** → HTTP 200 with per-listing schema.org **ld+json**
  (`Accommodation` name/url/address/geo/beds + `Product` offers.price) for the
  Santa Clara, Sunnyvale, and Mountain View city pages (~41 listings each); added
  as the `redfin_ldjson` handler. San Jose and San Francisco city pages returned
  **HTTP 202 challenge pages** in the same probe — not added. Redfin also 202s
  rapid back-to-back city requests, so `capture_web.py` spaces same-host Redfin
  fetches 10s apart; any 202/challenge still records `Source Blocked` and stops.
- **PadMapper** → HTTP 200 with the same `__PRELOADED_STATE__` as Zumper (same
  backend; listings resolve to zumper.com URLs). NOT added: it would only
  duplicate the existing Zumper lanes.
- **Realtor.com rentals** → HTTP 429 to a normal desktop-Chrome UA; recorded
  blocked, no handler.
- **Roomies.com** → HTTP 403; recorded blocked, no handler.
- **SpareRoom** → HTTP 200 public HTML but no clean embedded listing state
  (`__PRELOADED_STATE__`/`__NEXT_DATA__` absent); no handler added.
- **UDR Bay Area index sweep** → 9 more communities with the same public
  `jsonObjPropertyViewModel` state added to the `pm` handler: Verve (Mountain
  View), Channel Mission Bay / 388 Beale / 399 Fremont / HQ Apartments /
  Edgewater / 2000 Post (San Francisco — Channel verified with 37 units, exact
  rents/dates/coords), CitySouth / Bay Terrace (San Mateo). Skipped as
  out-of-search-area: 5421 at Dublin Station, Residences at Lake Merritt,
  Highlands of Marin (San Rafael), Almaden Lake Village (south San Jose).

2026-07-01 direct property-manager probe notes:

- **Irvine Company Santa Clara Square / Monticello** → HTTP 403 to a normal
  desktop-Chrome UA on public community/availability paths; recorded blocked, no
  handler entry.
- **Avalon Santa Clara** → probed likely public Avalon Santa Clara / Silicon Valley /
  Morrison Park paths; returned HTTP 404, no clean public availability path found.
- **Domain / Centerra (Essex)** → Essex public paths returned HTTP 429; recorded
  blocked and stopped. The standalone `domainapts.com` page only redirected to a
  thin lander, with no availability state.
- **Nineteen800 (Prometheus)** → HTTP 403 on public community/floorplan paths;
  recorded blocked, no handler entry.
- **Mio** → `mioliving.com` resolved to an Afternic parked-domain page, not a live
  apartment availability source.
- **RentCafe/Yardi near-office candidates** (The Benton, Elan at River Oaks,
  River Mark, Solera, Solstice, Encasa) → HTTP 403 to a normal desktop-Chrome UA;
  recorded blocked, no handler entry.
- **UDR River Terrace, Marina Playa, Birch Creek** → HTTP 200 public pages with
  embedded `window.udr.jsonObjPropertyViewModel`; added to the `web` tier through
  the `pm` handler.

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
- Every kickoff writes `housing-trackers/run-health.json` with per-source
  attempt/success timestamps, row counts, blocked/empty/missing outcomes, and
  pending browser captures. It retains unselected lanes and marks them with
  `selectedThisRun: false`, so alternating solo/group runs do not erase history.
  Source aging defaults to `--decay-scope covered`: every enabled lane in a portal
  family must return a fresh, non-blocked, non-empty capture before omitted rows
  from that family can age. A zero-row result is health degradation until a future
  schema-aware empty sentinel exists; it never decays inventory by itself.
- `run.py` takes one non-blocking conductor lock across capture → ledger → health,
  while the exporter waits for the same lock. Scheduled agents must still use
  distinct capture directories so `--fresh-capture-dir` is scoped to one task.
- `--sources 5br` / `5plus` and `--sources sf5plus` are operationally equivalent
  for the current enabled group-house search because all enabled 5+ lanes are
  SF-only. Non-SF 5+ lanes are kept disabled, not deleted, for future re-enable.
- Old `ai-*.json` files discovered by capture-dir glob are skipped after 18 hours so
  stale browser captures cannot refresh `Last Seen`. Explicit `--input ai-...json`
  still replays a file intentionally; `--allow-stale-captures` exists for rare audits.
- For the `ai_browser` tier only, the conductor (Codex Chrome plugin /
  Claude-in-Chrome / Computer Use) writes one JSON array per source into the capture
  dir, then re-runs `run.py`. `run.py` prints the exact plan for these to stderr.
