# Power Rankings View

The power rankings are the primary daily UI. They should answer: "What are the five best current options in each market, what changed, and what should Liam do next?"

## Board Sections

Use this order:

1. Daily summary.
2. Top 5 overall active listings.
3. Top 5 by market/city/neighborhood.
4. New entrants.
5. Expired, unavailable, stale, or replaced listings.
6. Needs manual verification.
7. Source blockers and capture gaps.

## Ranking Row

Each ranked row should include:

- Rank.
- Delta from previous board: `New`, `Same`, `+N`, `-N`, `Re-entered`.
- Score.
- No-car score.
- Car score.
- Rent all-in.
- Market.
- Listing title.
- Lease/flexibility.
- Commute summary.
- Why it ranks here.
- Status.
- Source link.

## Market Buckets

The board should keep separate top-5 lists for markets that have enough active inventory. Default to:

- SF Mission/Valencia
- SF Dogpatch/Potrero/Showplace
- SF SoMa/South Beach/Mission Bay
- SF Hayes/Lower Haight/Castro/Duboce
- Mountain View
- Sunnyvale
- Santa Clara
- North San Jose
- Palo Alto/Menlo Park
- Redwood City/San Carlos/Belmont
- San Mateo/Burlingame/Millbrae
- Oakland/Berkeley
- Other Bay Area

If a market has fewer than five active listings, show all active listings and label the section `Underfilled`.

## Expiration Semantics

Never silently remove a listing from the board.

Use these statuses:

- `Active`: currently viable and should rank.
- `Needs Verification`: promising but missing availability, address, source freshness, or commute facts.
- `Stale`: not verified recently enough; keep out of top ranks unless inventory is thin.
- `Expired`: listing page says unavailable, deleted, rented, or no longer listed.
- `Unavailable`: source is reachable but listing cannot be acted on.
- `Duplicate`: duplicate of a stronger canonical row.
- `Rejected`: bad fit, scam risk, commute too poor, budget too high, or lease incompatible.

Daily expiration checks:

- Verify every current top-5 listing.
- Verify any listing with `Active` status and `last_seen` older than 3 days.
- For Facebook/Craigslist/subleases, be stricter: stale after 48 hours without a fresh source signal.
- Move expired/unavailable listings into the expired/replaced section with the date and reason.

## Tie Breakers

Break close scores in this order:

1. Month-to-month/sublease/furnished flexibility.
2. Shorter and less fragile commute.
3. Lower all-in monthly cost.
4. Better Caltrain/VTA/walkability without car.
5. Stronger availability confidence.
6. Better neighborhood/lifestyle fit.
7. Better source trust and richer listing detail.
