#!/usr/bin/env python3
"""Mirror the housing ledger into a Notion database (optional, additional output).

Notion is a slower external mirror; housing-trackers/{listings,power-rankings}.md
stay authoritative. This reads the ledger via housing_pipeline.load_listing_rows()
and UPSERTS one Notion page per listing, keyed by "Listing Key" (create new +
update existing — unlike the recruiting sync which only updates).

Config (mirrors the recruiting pattern):
  - NOTION_TOKEN env var: internal integration token shared with the housing DB.
  - housing-trackers/notion-config.md: `database_url:` and `data_source_url:` lines.

Run:
  python3 sync_housing_to_notion.py --dry-run        # preview (offline if no token)
  NOTION_TOKEN=secret_... python3 sync_housing_to_notion.py
Stdlib only (urllib) so it runs in CI/cloud with no pip install.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import housing_pipeline as hp  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
NOTION_VERSION = "2025-09-03"
MATCH_KEY = "Listing Key"

# Notion property name -> (ledger column, kind). Create this DB with these exact
# property names; "Listing" is the title and "Listing Key" is the match key.
PROPERTY_MAP = [
    ("Listing", "Title", "title"),
    ("Listing Key", "Listing Key", "text"),
    ("Market", "Market", "select"),
    ("City", "City", "text"),
    ("Neighborhood", "Neighborhood", "text"),
    ("Rent", "Rent", "number"),
    ("All-In", "All-In Estimate", "number"),
    ("Beds", "Beds", "text"),
    ("Baths", "Baths", "text"),
    ("Lease", "Lease", "text"),
    ("Available", "Available", "text"),
    ("Status", "Status", "select"),
    ("Score", "Score", "number"),
    ("No-Car Score", "No-Car Score", "number"),
    ("Car Score", "Car Score", "number"),
    ("Commute", "Commute", "text"),
    ("Why", "Why", "text"),
    ("Source", "Source", "select"),
    ("First Seen", "First Seen", "date"),
    ("Last Seen", "Last Seen", "date"),
    ("URL", "URL", "url"),
    ("Notes", "Notes", "text"),
]


@dataclass
class NotionConfig:
    database_url: str
    data_source_url: str

    @property
    def database_id(self) -> str:
        return extract_notion_id(self.database_url)

    @property
    def data_source_id(self) -> str:
        value = (self.data_source_url or "").strip()
        if value.startswith("collection://"):
            value = value.split("collection://", 1)[1]
        return value.strip().strip("/")


def extract_notion_id(value: str) -> str:
    text = (value or "").strip().strip("/")
    if text.startswith(("http://", "https://")):
        parts = [p for p in urlparse(text).path.split("/") if p]
        text = parts[-1] if parts else ""
    # a notion id can be suffixed onto a slug: take the trailing 32 hex chars
    compact = text.replace("-", "")
    if len(compact) >= 32 and all(c in "0123456789abcdefABCDEF" for c in compact[-32:]):
        h = compact[-32:]
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
    if not text:
        raise ValueError("Missing Notion identifier")
    return text


def load_config(root: Path) -> NotionConfig | None:
    path = root / "housing-trackers" / "notion-config.md"
    if not path.exists():
        return None
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    db = values.get("database_url", "").strip()
    if not db or db.startswith("<"):  # placeholder not filled in yet
        return None
    data_source = values.get("data_source_url") or db
    return NotionConfig(database_url=db, data_source_url=data_source)


# Notion rate-limits (429) and, on a flaky network, single requests among the
# thousands this sync makes can hit transient connection resets/timeouts. Retry
# those with exponential backoff so one blip does not abort the whole run. 4xx
# other than 429 are real request errors and are raised immediately.
TRANSIENT_HTTP = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 5


def notion_request(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    for attempt in range(MAX_ATTEMPTS):
        request = Request(f"https://api.notion.com{path}", data=payload, method=method)
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Notion-Version", NOTION_VERSION)
        request.add_header("Content-Type", "application/json")
        try:
            with urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
        except HTTPError as exc:
            if exc.code in TRANSIENT_HTTP and attempt < MAX_ATTEMPTS - 1:
                retry_after = (exc.headers.get("Retry-After") or "").strip()
                delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2 ** attempt
                time.sleep(min(delay, 30))
                continue
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Notion API {exc.code} {exc.reason}: {details}") from exc
        except (URLError, OSError) as exc:
            # OSError covers ConnectionResetError, socket.timeout, and TimeoutError.
            # (In Python 3.9 socket.timeout is NOT a subclass of TimeoutError, so we
            # must catch OSError rather than TimeoutError to retry read timeouts.)
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"Notion request failed after {MAX_ATTEMPTS} attempts: {exc}") from exc
    raise RuntimeError("Notion request exhausted retries")  # unreachable, satisfies type checkers


def query_pages(token: str, data_source_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        response = notion_request("POST", f"/v1/data_sources/{data_source_id}/query", token, body)
        results.extend(response.get("results", []))
        if not response.get("has_more"):
            return results
        cursor = response.get("next_cursor")


def rich_text_value(prop: dict[str, Any]) -> str:
    return "".join(item.get("plain_text", "") for item in prop.get("rich_text", []))


def existing_key(page: dict[str, Any]) -> str:
    return hp.normalize(rich_text_value(page.get("properties", {}).get(MATCH_KEY, {})))


def _date(value: str) -> str | None:
    d = hp.parse_date(value)
    return d.isoformat() if d else None


def commute_fields(commute_text: str, market: str) -> tuple[str, int | None, int | None, int | None]:
    """Parse (how_to_get_there, no_car_to_work, no_car_from_work, car_to_work) minutes
    from the Commute cell, falling back to the market default. Commute format is:
    '{summary}; no-car ~{to}m to work / ~{from}m home, car ~{to}m / ~{from}m'."""
    text = hp.clean(commute_text)
    how = text.split("; no-car", 1)[0].strip() if "; no-car" in text else text

    def grab(pattern: str) -> int | None:
        match = re.search(pattern, text)
        return int(match.group(1)) if match else None

    no_car_to = grab(r"no-car ~?(\d+)\s*m to work")
    no_car_from = grab(r"to work / ~?(\d+)\s*m home")
    car_to = grab(r"car ~?(\d+)\s*m")
    default = hp.COMMUTE_DEFAULTS.get(market)
    if default:
        no_car_to = no_car_to if no_car_to is not None else default["no_car"]
        car_to = car_to if car_to is not None else default["car"]
        how = how or default["summary"]
    return how, no_car_to, no_car_from, car_to


def compute_ranks(rows: list[dict[str, str]]) -> tuple[dict[str, int], dict[str, int]]:
    """Overall and per-market (city) power rank among ACTIVE listings, matching the
    board's ordering (housing_pipeline.rank_sort_key)."""
    active = sorted(hp.active_rows(rows), key=hp.rank_sort_key)
    overall = {r.get("Listing Key", ""): i for i, r in enumerate(active, 1)}
    by_market: dict[str, list[dict[str, str]]] = {}
    for row in active:
        by_market.setdefault(row.get("Market", ""), []).append(row)
    city: dict[str, int] = {}
    for market_rows in by_market.values():
        for i, row in enumerate(sorted(market_rows, key=hp.rank_sort_key), 1):
            city[row.get("Listing Key", "")] = i
    return overall, city


def _rich_text(content: str) -> list[dict[str, Any]]:
    """Notion caps each rich_text/title item's content at 2000 chars and rejects the
    whole request (HTTP 400 validation_error) if any item exceeds it. Split long text
    into consecutive ≤2000-char items so the full content is preserved without error."""
    if not content:
        return []
    return [
        {"type": "text", "text": {"content": content[i : i + 2000]}}
        for i in range(0, len(content), 2000)
    ]


def build_properties(row: dict[str, str], overall_rank: int | None = None, city_rank: int | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for notion_name, column, kind in PROPERTY_MAP:
        value = hp.clean(row.get(column, ""))
        if kind == "title":
            props[notion_name] = {"title": _rich_text(value) or [{"type": "text", "text": {"content": "(untitled)"}}]}
        elif kind == "text":
            props[notion_name] = {"rich_text": _rich_text(value)}
        elif kind == "select":
            props[notion_name] = {"select": {"name": value}} if value else {"select": None}
        elif kind == "number":
            n = hp.to_int(value)
            props[notion_name] = {"number": n if value else None}
        elif kind == "url":
            props[notion_name] = {"url": value or None}
        elif kind == "date":
            iso = _date(value)
            props[notion_name] = {"date": {"start": iso} if iso else None}

    # Computed: rankings + parsed commute (rank is blank for non-active rows).
    how, no_car_to, no_car_from, car_to = commute_fields(row.get("Commute", ""), row.get("Market", ""))
    props["Overall Rank"] = {"number": overall_rank}
    props["City Rank"] = {"number": city_rank}
    props["Commute (min)"] = {"number": no_car_to}
    props["Commute Home (min)"] = {"number": no_car_from}
    props["Car Commute (min)"] = {"number": car_to}
    props["How to get there"] = {"rich_text": _rich_text(how)}
    return props


def parent_for_create(config: NotionConfig) -> dict[str, Any]:
    # Notion 2025-09-03 multi-source DBs parent new pages on the data source.
    return {"type": "data_source_id", "data_source_id": config.data_source_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="Upsert the housing ledger into a Notion database.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--token-env", default="NOTION_TOKEN")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing (offline if no token)")
    parser.add_argument("--limit", type=int, default=0, help="Only sync the first N rows (0 = all)")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else ROOT
    if args.root:
        os.environ.setdefault("HOUSING_TRACKER_DIR", str(root / "housing-trackers"))
    # Rank over the FULL active set, then optionally limit which rows we push.
    all_rows = hp.load_listing_rows()
    overall_ranks, city_ranks = compute_ranks(all_rows)
    rows = all_rows[:args.limit] if args.limit else all_rows

    token = os.environ.get(args.token_env, "").strip()
    config = load_config(root)

    # Offline preview: no token or no DB configured yet — show what would sync.
    if not token or config is None:
        reason = "no token" if not token else "no notion-config.md / database_url"
        print(f"[offline preview — {reason}] {len(rows)} ledger rows would sync:", file=sys.stderr)
        for row in rows[:25]:
            lk = row.get("Listing Key", "")
            how, no_car_to, _, _ = commute_fields(row.get("Commute", ""), row.get("Market", ""))
            orank = overall_ranks.get(lk)
            crank = city_ranks.get(lk)
            print(
                f"  overall #{orank or '-':<3} city #{crank or '-':<3} {row.get('Source',''):11.11} {row.get('Status',''):16} "
                f"{(str(no_car_to)+'m') if no_car_to else '-':>5} via {how[:24]:24}  {hp.compact_title(row.get('Title',''))}",
                file=sys.stderr,
            )
        print(json.dumps({"created": 0, "updated": 0, "rows": len(rows), "configured": False}, indent=2))
        return 0

    pages = query_pages(token, config.data_source_id)
    by_key = {existing_key(p): p["id"] for p in pages if existing_key(p)}
    created = updated = 0
    for row in rows:
        lk = row.get("Listing Key", "")
        key = hp.normalize(lk)
        props = build_properties(row, overall_ranks.get(lk), city_ranks.get(lk))
        page_id = by_key.get(key)
        if args.dry_run:
            print(f"{'update' if page_id else 'create'}: {hp.compact_title(row.get('Title',''))} [{row.get('Listing Key','')}]")
            (updated if page_id else created)  # no-op counters in dry-run
            if page_id:
                updated += 1
            else:
                created += 1
            continue
        if page_id:
            notion_request("PATCH", f"/v1/pages/{page_id}", token, {"properties": props})
            updated += 1
        else:
            notion_request("POST", "/v1/pages", token, {"parent": parent_for_create(config), "properties": props})
            created += 1

    print(json.dumps({"created": created, "updated": updated, "rows": len(rows), "configured": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
