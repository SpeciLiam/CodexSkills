#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[3]
NOTION_VERSION = "2025-09-03"


@dataclass
class NotionConfig:
    database_url: str
    data_source_url: str

    @property
    def database_id(self) -> str:
        return extract_notion_id(self.database_url)

    @property
    def data_source_id(self) -> str:
        value = self.data_source_url.strip()
        if value.startswith("collection://"):
            value = value.split("collection://", 1)[1]
        return value.strip().strip("/")


def normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def extract_notion_id(value: str) -> str:
    text = value.strip().strip("/")
    if text.startswith(("http://", "https://")):
        parts = [part for part in urlparse(text).path.split("/") if part]
        text = parts[-1] if parts else ""
    if len(text) == 32:
        return f"{text[0:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:32]}"
    if not text:
        raise ValueError("Missing Notion identifier")
    return text


def load_config(root: Path) -> NotionConfig:
    path = root / "application-trackers" / "notion-config.md"
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    data_source = values.get("data_source_url") or values.get("database_url", "")
    return NotionConfig(database_url=values["database_url"], data_source_url=data_source)


def load_applications(root: Path) -> list[dict[str, Any]]:
    path = root / "application-visualizer" / "src" / "data" / "tracker-data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in data.get("applications", []) if isinstance(row, dict)]


def notion_request(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(f"https://api.notion.com{path}", data=payload, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Notion-Version", NOTION_VERSION)
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request) as response:
            text = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API {exc.code} {exc.reason}: {details}") from exc
    return json.loads(text) if text else {}


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


def title_text(value: dict[str, Any]) -> str:
    return "".join(item.get("plain_text", "") for item in value.get("title", []))


def rich_text(value: dict[str, Any]) -> str:
    return "".join(item.get("plain_text", "") for item in value.get("rich_text", []))


def page_summary(page: dict[str, Any]) -> dict[str, str]:
    props = page.get("properties", {})
    return {
        "id": page["id"],
        "company": title_text(props.get("Company", {})).strip(),
        "role": rich_text(props.get("Role", {})).strip(),
        "postingKey": rich_text(props.get("Posting Key", {})).strip(),
    }


def unique_match(app: dict[str, Any], pages: list[dict[str, str]]) -> dict[str, str] | None:
    posting_key = normalize(str(app.get("postingKey", "")))
    if posting_key:
        matches = [page for page in pages if normalize(page.get("postingKey", "")) == posting_key]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None

    company = normalize(str(app.get("company", "")))
    role = normalize(str(app.get("role", "")))
    matches = [
        page for page in pages
        if normalize(page.get("company", "")) == company and normalize(page.get("role", "")) == role
    ]
    return matches[0] if len(matches) == 1 else None


def text_prop(value: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value or ""}}]}


def url_or_none(value: str) -> str | None:
    return value.strip() or None


def properties_from_app(app: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = {
        "Company": {"title": [{"type": "text", "text": {"content": app.get("company", "")}}]},
        "Role": text_prop(app.get("role", "")),
        "Applied": {"checkbox": bool(app.get("applied"))},
        "Status": {"select": {"name": app.get("status") or "Resume Tailored"}},
        "Fit Score": {"number": int(app.get("fitScore") or 0)},
        "Reach Out": {"checkbox": bool(app.get("reachOut"))},
        "Referral": {"checkbox": bool(app.get("referral"))},
        "Location": text_prop(app.get("location", "")),
        "Source": {"select": {"name": app.get("source") or "Other"}},
        "Job Link": {"url": url_or_none(app.get("jobLink", ""))},
        "Posting Key": text_prop(app.get("postingKey", "")),
        "Resume PDF": {"url": url_or_none(app.get("resumePdf", ""))},
        "Recruiter Contact": text_prop(app.get("recruiterContact", "")),
        "Recruiter Profile": {"url": url_or_none(app.get("recruiterProfile", ""))},
        "Engineer Contact": text_prop(app.get("engineerContact", "")),
        "Engineer Profile": {"url": url_or_none(app.get("engineerProfile", ""))},
        "Notes": text_prop(app.get("notes", "")),
    }
    if app.get("dateAdded"):
        props["Date Added"] = {"date": {"start": app["dateAdded"]}}
    return props


def update_page(token: str, page_id: str, app: dict[str, Any]) -> None:
    notion_request("PATCH", f"/v1/pages/{page_id}", token, {"properties": properties_from_app(app)})


def update_title(token: str, config: NotionConfig, total: int) -> None:
    notion_request(
        "PATCH",
        f"/v1/databases/{config.database_id}",
        token,
        {"title": [{"type": "text", "text": {"content": f"Applications ({total})"}}]},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Optionally sync visualizer application cache to Notion.")
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--token-env", default="NOTION_TOKEN", help="Environment variable holding the Notion token")
    parser.add_argument("--posting-key", default="", help="Limit sync to one posting key")
    parser.add_argument("--dry-run", action="store_true", help="Show matches without changing Notion")
    parser.add_argument("--update-title", action="store_true", help="Update Notion database title count")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else ROOT
    token = os.environ.get(args.token_env, "").strip()
    if not token:
        raise SystemExit(f"Missing Notion token in {args.token_env}")

    config = load_config(root)
    apps = load_applications(root)
    if args.posting_key:
        apps = [app for app in apps if normalize(str(app.get("postingKey", ""))) == normalize(args.posting_key)]

    pages = [page_summary(page) for page in query_pages(token, config.data_source_id)]
    updated = missing = 0

    for app in apps:
        page = unique_match(app, pages)
        label = f"{app.get('company', '')} | {app.get('role', '')}"
        if page is None:
            missing += 1
            print(f"missing: {label}")
            continue
        if args.dry_run:
            print(f"match: {label} -> {page['id']}")
        else:
            update_page(token, page["id"], app)
        updated += 1

    if args.update_title and not args.posting_key and not args.dry_run:
        update_title(token, config, len(load_applications(root)))

    print(json.dumps({"updated": updated, "missing": missing, "rows_considered": len(apps)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
