#!/usr/bin/env python3
"""Export the housing ledger into housing-visualizer/src/data/housing-data.json.

Reuses housing_pipeline (ledger load) + sync_housing_to_notion (rank/commute logic)
so the website, the Notion mirror, and the markdown board all agree. Stdlib only.
Run directly, or via the visualizer's `npm run dev/build`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import housing_pipeline as hp  # noqa: E402
import sync_housing_to_notion as sync  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "housing-visualizer" / "src" / "data" / "housing-data.json"


def num(value: str):
    n = hp.to_int(value)
    return n if value not in (None, "") and n != 0 else (0 if value in ("0",) else None)


def export() -> dict:
    rows = hp.load_listing_rows()
    overall_ranks, city_ranks = sync.compute_ranks(rows)

    listings = []
    for row in rows:
        lk = row.get("Listing Key", "")
        how, nc_to, nc_from, car_to = sync.commute_fields(row.get("Commute", ""), row.get("Market", ""))
        listings.append({
            "listingKey": lk,
            "title": row.get("Title", ""),
            "market": row.get("Market", ""),
            "city": row.get("City", ""),
            "neighborhood": row.get("Neighborhood", ""),
            "rent": num(row.get("Rent", "")),
            "allIn": num(row.get("All-In Estimate", "")),
            "beds": row.get("Beds", ""),
            "baths": row.get("Baths", ""),
            "lease": row.get("Lease", ""),
            "available": row.get("Available", ""),
            "status": row.get("Status", ""),
            "score": hp.to_int(row.get("Score", "")),
            "noCarScore": hp.to_int(row.get("No-Car Score", "")),
            "carScore": hp.to_int(row.get("Car Score", "")),
            "overallRank": overall_ranks.get(lk),
            "cityRank": city_ranks.get(lk),
            "commuteMin": nc_to,
            "commuteHomeMin": nc_from,
            "carCommuteMin": car_to,
            "howToGetThere": how,
            "why": sync.hp.clean(row.get("Why", "")),
            "source": row.get("Source", ""),
            "firstSeen": row.get("First Seen", ""),
            "lastSeen": row.get("Last Seen", ""),
            "url": row.get("URL", ""),
            "notes": row.get("Notes", ""),
        })

    active = [x for x in listings if x["status"] in hp.ACTIVE_STATUSES]
    needs = [x for x in listings if x["status"] == "Needs Verification"]
    replaced = [x for x in listings if x["status"] in hp.REPLACED_STATUSES]
    markets = sorted({x["market"] for x in active if x["market"]}, key=hp.market_sort_key)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total": len(listings),
            "active": len(active),
            "needsVerification": len(needs),
            "replaced": len(replaced),
            "markets": len(markets),
        },
        "marketOrder": [m for m in hp.MARKET_ORDER if m in markets],
        "listings": listings,
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = export()
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), **data["stats"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
