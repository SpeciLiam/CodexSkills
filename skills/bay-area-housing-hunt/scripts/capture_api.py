#!/usr/bin/env python3
"""Config-driven listings-API capture.

Pulls listings from any JSON HTTP API (RentCast, a RapidAPI real-estate wrapper,
etc.) defined in the `apis` array of searches.json, and writes them into the
capture dir in the standard capture format so the pipeline ingests them like any
other source. This deliberately contains NO scraping / CAPTCHA / proxy / stealth
logic — it only makes authenticated API requests with a key. Each API is a no-op
until its key env var is set, and any error is recorded as a Source Blocked row.

Stdlib only (urllib) so it runs in CI/cloud. Importable for tests:
    map_items(cfg, payload) -> list[capture records]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import housing_pipeline as hp  # noqa: E402

FETCH_TIMEOUT = 15
USER_AGENT = "CodexSkills-housing-hunt/1.0 (personal housing search)"


def _dig(obj, path: str):
    """Navigate a dot path ('' = obj itself) to reach the listings array/value."""
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def map_items(cfg: dict, payload) -> list[dict]:
    """Map an API JSON payload into capture records using cfg['field_map']."""
    items = _dig(payload, cfg.get("list_path", ""))
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []
    field_map: dict[str, str] = cfg.get("field_map", {})
    id_field = cfg.get("id_field")
    source = cfg.get("source") or cfg.get("name") or "API"
    records: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        record: dict = {"source": source}
        for capture_field, response_field in field_map.items():
            value = _dig(item, response_field)
            if value is not None and value != "":
                record[capture_field] = value
        if id_field:
            ident = _dig(item, id_field)
            if ident not in (None, ""):
                record["listing_key"] = f"{hp.slug(source)}-{ident}"
        if record.get("title") or record.get("address") or record.get("url"):
            records.append(record)
    return records


def fetch_api(cfg: dict, city: str | None) -> tuple[list[dict], str | None]:
    url = cfg["url"].replace("{city}", quote(city) if city else "")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    key_env = cfg.get("key_env")
    token = os.environ.get(key_env, "").strip() if key_env else ""
    if key_env and token:
        headers[cfg.get("key_header", "X-Api-Key")] = token
        # RapidAPI wrappers also want the host header; pass it through if configured.
        if cfg.get("rapidapi_host"):
            headers["X-RapidAPI-Host"] = cfg["rapidapi_host"]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            if resp.status != 200:
                raise urllib.error.HTTPError(url, resp.status, "non-200", resp.headers, None)
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 - any failure -> Source Blocked, never retry/bypass
        reason = f"Source Blocked: {type(exc).__name__}: {exc}"
        return ([{
            "source": cfg.get("source") or cfg.get("name", "API"),
            "status": "source blocked",
            "title": f"{cfg.get('name','API')} request failed",
            "url": url,
            "description": reason,
            "market": cfg.get("market_hint", ""),
        }], reason)
    return map_items(cfg, payload), None


def run_api_capture(capture_dir: Path, searches: dict) -> list[Path]:
    written: list[Path] = []
    for cfg in searches.get("apis", []):
        if not cfg.get("enabled", False):
            continue
        key_env = cfg.get("key_env")
        if key_env and not os.environ.get(key_env, "").strip():
            print(f"  api {cfg.get('name')}: skipped (no {key_env})", file=sys.stderr)
            continue
        cities = cfg.get("cities") or [None]
        for city in cities:
            records, error = fetch_api(cfg, city)
            label = (city or "all").lower().replace(" ", "-")
            out = capture_dir / f"api-{hp.slug(cfg.get('name','api'))}-{label}.json"
            out.write_text(json.dumps(records, indent=2), encoding="utf-8")
            written.append(out)
            status = "blocked" if error else f"{len(records)} items"
            print(f"  api {cfg.get('name')} [{city or 'all'}]: {status}", file=sys.stderr)
    return written


if __name__ == "__main__":
    # Standalone smoke test against the real config + capture dir.
    cap = Path(os.environ.get("HOUSING_CAPTURE_DIR", "/tmp/codexskills-housing-hunt"))
    cap.mkdir(parents=True, exist_ok=True)
    cfg_path = SCRIPT_DIR / "searches.json"
    searches = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    paths = run_api_capture(cap, searches)
    print(json.dumps({"wrote": [str(p) for p in paths]}, indent=2))
