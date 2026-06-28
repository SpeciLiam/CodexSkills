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
- The Listing Project (curated SF/Bay sublets and shares).
- Kopa (furnished short-term sublets; strong near Stanford/SCU and for early-career movers).
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

Scraping public/free data for Liam's own move is fine. Concretely:

- **Free + headless (cloud-ok):** public RSS (Craigslist) and public JSON APIs
  (Reddit, and any free endpoint added to `searches.json` → `apis`). `capture_api.py`
  fetches these with no key.
- **Anti-bot portals (Zillow, Apartments.com, Realtor.com, Facebook, Nextdoor):**
  do NOT try to defeat them headlessly. Capture them with the **local real signed-in
  browser** (Claude-in-Chrome / Computer Use / Chrome plugin) — it's free and robust
  because it's a genuine browser session.
- **Keyed data APIs (RentCast, RapidAPI wrappers):** optional, off by default; enable
  by setting the key env var. Only use free tiers unless Liam opts into paying.

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

- `scripts/run.py` is the kickoff. It reads `scripts/searches.json` (public RSS
  feeds it fetches headlessly + the dynamic/logged-in sources it lists for AI
  capture), ingests every JSON in the capture dir, and rebuilds the board.
- The conductor (Codex Chrome plugin / Claude-in-Chrome / Computer Use) writes one
  JSON array per dynamic source into the capture dir, then re-runs `run.py`.
