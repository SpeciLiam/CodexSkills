#!/usr/bin/env python3
"""One-time: create the housing Notion database under a page the integration can
access, with a schema that exactly matches what sync_housing_to_notion.py writes.

Prereqs: NOTION_TOKEN env set; the integration shared with a parent page.
Prints {db_id, data_source_id, url}. Stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import sync_housing_to_notion as sync  # noqa: E402

KIND_TO_SCHEMA = {
    "title": {"title": {}},
    "text": {"rich_text": {}},
    "select": {"select": {}},
    "number": {"number": {}},
    "url": {"url": {}},
    "date": {"date": {}},
}
# Computed properties the sync adds beyond PROPERTY_MAP.
COMPUTED = {
    "Overall Rank": {"number": {}},
    "City Rank": {"number": {}},
    "Commute (min)": {"number": {}},
    "Commute Home (min)": {"number": {}},
    "Car Commute (min)": {"number": {}},
    "How to get there": {"rich_text": {}},
}


def req(method: str, path: str, token: str, body=None, version="2022-06-28"):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(f"https://api.notion.com{path}", data=payload, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Notion-Version", version)
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request) as resp:
            text = resp.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Notion {exc.code} {exc.reason}: {exc.read().decode('utf-8', 'replace')}") from exc
    return json.loads(text) if text else {}


def build_schema() -> dict:
    props: dict = {}
    for notion_name, _column, kind in sync.PROPERTY_MAP:
        props[notion_name] = dict(KIND_TO_SCHEMA[kind])
    props.update(COMPUTED)
    return props


def main() -> int:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set NOTION_TOKEN")
    parent_title = sys.argv[1] if len(sys.argv) > 1 else "Getting Started"
    db_title = sys.argv[2] if len(sys.argv) > 2 else "Bay Area Housing Power Rankings"

    # 1. Find the parent page the integration was granted.
    results = req("POST", "/v1/search", token, {"filter": {"property": "object", "value": "page"}}).get("results", [])
    parent = None
    for page in results:
        title = ""
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in prop.get("title", []))
        if title.strip() == parent_title:
            parent = page
            break
    if parent is None and results:
        parent = results[0]
    if parent is None:
        raise SystemExit("No accessible page found — share a page with the integration first.")
    page_id = parent["id"]

    # 2. Create the database with the full schema.
    db = req("POST", "/v1/databases", token, {
        "parent": {"type": "page_id", "page_id": page_id},
        "title": [{"type": "text", "text": {"content": db_title}}],
        "properties": build_schema(),
    })
    db_id = db["id"]
    db_url = db.get("url", "")

    # 3. Resolve the data source id (new API) for the sync to query/create against.
    full = req("GET", f"/v1/databases/{db_id}", token, version="2025-09-03")
    data_sources = full.get("data_sources", [])
    ds_id = data_sources[0]["id"] if data_sources else db_id

    print(json.dumps({"db_id": db_id, "data_source_id": ds_id, "url": db_url, "parent_page": page_id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
