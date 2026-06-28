# Housing Notion Mirror — config

Optional. Fill this in to mirror the housing ledger into a Notion database. Until
`database_url` is set to a real URL (not the `<placeholder>`), the Notion sync is a
no-op and the rest of the housing flow is unaffected.

## Setup (one time)

1. Create a Notion database (a "table") with these properties — names must match exactly:
   - `Listing` (Title)  ·  `Listing Key` (Text, the match key)
   - `Market` (Select)  ·  `City` (Text)  ·  `Neighborhood` (Text)
   - `Rent` (Number)  ·  `All-In` (Number)  ·  `Beds` (Text)  ·  `Baths` (Text)
   - `Lease` (Text)  ·  `Available` (Text)  ·  `Status` (Select)
   - `Score` (Number)  ·  `No-Car Score` (Number)  ·  `Car Score` (Number)
   - `Commute` (Text)  ·  `Why` (Text)  ·  `Source` (Select)  ·  `Notes` (Text)
   - `First Seen` (Date)  ·  `Last Seen` (Date)  ·  `URL` (URL)
   - `Overall Rank` (Number)  ·  `City Rank` (Number)  — power ranks among active listings
   - `Commute (min)` (Number)  ·  `Commute Home (min)` (Number)  ·  `Car Commute (min)` (Number)  ·  `How to get there` (Text)
2. Create/Use a Notion internal integration and **share the database with it**.
3. Put the integration token in the `NOTION_TOKEN` env var (locally) and/or as a
   GitHub Actions secret named `NOTION_TOKEN` (for the cloud job).
4. Paste the database URL below. The data source URL is optional — for a simple
   single-source database it equals the database URL.

## Suggested views (build these in Notion after the first sync)

- **Overall Power Ranking** — Filter `Status = Active`; Sort by `Overall Rank` ascending. (Table or Board.)
- **By City Power Ranking** — Group by `Market` (or `City`); within each group, Sort by `City Rank` ascending.
- **By Commute** — Filter `Status = Active`; Sort by `Commute (min)` ascending; show `How to get there`, `Rent`, `Score`. (Add a `Commute (min) ≤ 40` filter for a "close to office" view.)

`Overall Rank` / `City Rank` are blank for non-active rows. `Commute (min)` is the no-car
door-to-door *to-work* time; `How to get there` is the route (e.g. "bike+Caltrain (~7m bike)",
"near office; local bus/bike/drive").

## Values

database_url: https://app.notion.com/p/38de4796acaf8172b41bdfe7a0b245e6
data_source_url: 38de4796-acaf-81fa-961a-000b4c19c201
