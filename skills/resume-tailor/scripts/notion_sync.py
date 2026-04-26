#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from update_application_tracker import (
    ensure_tracker,
    parse_rows,
    repo_root_from_args,
    row_from_cells,
    split_row,
    tracker_path,
)

NOTION_VERSION = "2025-09-03"
DEFAULT_TOKEN_ENV = "NOTION_TOKEN"


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


def extract_notion_id(value: str) -> str:
    text = value.strip().strip("/")
    if not text:
        raise ValueError("Missing Notion identifier")
    if text.startswith("http://") or text.startswith("https://"):
        path_parts = [part for part in urlparse(text).path.split("/") if part]
        if not path_parts:
            raise ValueError(f"Could not extract Notion id from URL: {value}")
        text = path_parts[-1]
    if "-" in text:
        return text
    if len(text) == 32:
        return (
            f"{text[0:8]}-{text[8:12]}-{text[12:16]}-"
            f"{text[16:20]}-{text[20:32]}"
        )
    return text


def load_notion_config(repo_root: Path) -> NotionConfig:
    path = repo_root / "application-trackers" / "notion-config.md"
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return NotionConfig(
        database_url=values["database_url"],
        data_source_url=values["data_source_url"],
    )


def notion_request(
    method: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"https://api.notion.com{path}"
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Notion-Version", NOTION_VERSION)
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request) as response:
            data = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API {exc.code} {exc.reason}: {details}") from exc
    return json.loads(data) if data else {}


def load_tracker_rows(repo_root: Path) -> list[dict[str, str]]:
    tracker = tracker_path(repo_root)
    ensure_tracker(tracker)
    lines = tracker.read_text().splitlines()
    _, row_lines = parse_rows(lines)
    rows: list[dict[str, str]] = []
    for line in row_lines:
        row = row_from_cells(split_row(line))
        if row is not None:
            rows.append(row)
    return rows


def query_all_notion_pages(token: str, data_source_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        response = notion_request("POST", f"/v1/data_sources/{data_source_id}/query", token, body)
        results.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
        if not cursor:
            break
    return results


def title_text(property_value: dict[str, Any]) -> str:
    return "".join(item.get("plain_text", "") for item in property_value.get("title", []))


def rich_text_text(property_value: dict[str, Any]) -> str:
    return "".join(item.get("plain_text", "") for item in property_value.get("rich_text", []))


def checkbox_value(property_value: dict[str, Any]) -> bool:
    return bool(property_value.get("checkbox", False))


def number_value(property_value: dict[str, Any]) -> int | None:
    value = property_value.get("number")
    if value is None:
        return None
    return int(value)


def page_summary(page: dict[str, Any]) -> dict[str, Any]:
    props = page.get("properties", {})
    return {
        "id": page["id"],
        "company": title_text(props.get("Company", {})).strip(),
        "role": rich_text_text(props.get("Role", {})).strip(),
        "posting_key": rich_text_text(props.get("Posting Key", {})).strip(),
        "fit_score": number_value(props.get("Fit Score", {})),
        "reach_out": checkbox_value(props.get("Reach Out", {})),
    }


def markdown_url(value: str) -> str:
    value = value.strip()
    if "](" in value and value.endswith(")"):
        return value.rsplit("](", 1)[1][:-1].strip()
    return value


def normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def match_page(
    tracker_row: dict[str, str],
    pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    posting_key = normalize(tracker_row.get("Posting Key", ""))
    company = normalize(tracker_row.get("Company", ""))
    role = normalize(tracker_row.get("Role", ""))

    exact = [
        page for page in pages
        if normalize(page["posting_key"]) == posting_key and posting_key
    ]
    if len(exact) == 1:
        return exact[0]

    company_role = [
        page for page in pages
        if normalize(page["company"]) == company and normalize(page["role"]) == role
    ]
    if len(company_role) == 1:
        return company_role[0]

    return None


def update_page_scores(
    token: str,
    page_id: str,
    fit_score: int,
    reach_out: bool,
) -> None:
    notion_request(
        "PATCH",
        f"/v1/pages/{page_id}",
        token,
        {
            "properties": {
                "Fit Score": {"number": fit_score},
                "Reach Out": {"checkbox": reach_out},
            }
        },
    )


def page_properties_from_tracker_row(row: dict[str, str]) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "Company": {"title": [{"type": "text", "text": {"content": row.get("Company", "")}}]},
        "Role": {"rich_text": [{"type": "text", "text": {"content": row.get("Role", "")}}]},
        "Applied": {"checkbox": truthy_text(row.get("Applied", ""))},
        "Status": {"select": {"name": row.get("Status", "") or "Resume Tailored"}},
        "Fit Score": {"number": int(row.get("Fit Score", "").strip() or "0")},
        "Reach Out": {"checkbox": truthy_text(row.get("Reach Out", ""))},
        "Referral": {"checkbox": truthy_text(row.get("Referral", ""))},
        "Location": {"rich_text": [{"type": "text", "text": {"content": row.get("Location", "")}}]},
        "Source": {"select": {"name": row.get("Source", "") or "Other"}},
        "Job Link": {"url": markdown_url(row.get("Job Link", "")) or None},
        "Posting Key": {"rich_text": [{"type": "text", "text": {"content": row.get("Posting Key", "")}}]},
        "Resume PDF": {"url": markdown_url(row.get("Resume PDF", "")) or None},
        "Recruiter Contact": {
            "rich_text": [{"type": "text", "text": {"content": row.get("Recruiter Contact", "")}}]
        },
        "Recruiter Profile": {"url": markdown_url(row.get("Recruiter Profile", "")) or None},
        "Notes": {"rich_text": [{"type": "text", "text": {"content": row.get("Notes", "")}}]},
    }
    if row.get("Date Added", "").strip():
        properties["Date Added"] = {"date": {"start": row["Date Added"].strip()}}
    return properties


def truthy_text(value: str) -> bool:
    return normalize(value) in {"yes", "true", "1", "x"}


def update_page_from_tracker_row(token: str, page_id: str, row: dict[str, str]) -> None:
    notion_request(
        "PATCH",
        f"/v1/pages/{page_id}",
        token,
        {"properties": page_properties_from_tracker_row(row)},
    )


def update_database_title(token: str, config: NotionConfig, total_count: int) -> None:
    notion_request(
        "PATCH",
        f"/v1/databases/{config.database_id}",
        token,
        {"title": [{"type": "text", "text": {"content": f"Applications ({total_count})"}}]},
    )


def sync_tracker_to_notion(
    repo_root: Path,
    token: str,
    posting_key: str | None = None,
    update_title: bool = False,
    dry_run: bool = False,
    full: bool = False,
) -> dict[str, int]:
    config = load_notion_config(repo_root)
    tracker_rows = load_tracker_rows(repo_root)
    if posting_key:
        tracker_rows = [
            row for row in tracker_rows if normalize(row.get("Posting Key", "")) == normalize(posting_key)
        ]

    notion_pages = [page_summary(page) for page in query_all_notion_pages(token, config.data_source_id)]
    updated = 0
    skipped = 0
    missing = 0

    for row in tracker_rows:
        fit_score = int(row.get("Fit Score", "").strip() or "0")
        reach_out = normalize(row.get("Reach Out", "")) in {"yes", "true", "1"}
        page = match_page(row, notion_pages)
        if page is None:
            missing += 1
            continue

        if not full and page["fit_score"] == fit_score and page["reach_out"] == reach_out:
            skipped += 1
            continue

        if not dry_run:
            if full:
                update_page_from_tracker_row(token, page["id"], row)
            else:
                update_page_scores(token, page["id"], fit_score, reach_out)
        updated += 1

    if update_title and not posting_key and not dry_run:
        update_database_title(token, config, len(load_tracker_rows(repo_root)))

    return {
        "updated": updated,
        "skipped": skipped,
        "missing": missing,
        "rows_considered": len(tracker_rows),
    }


def token_from_env(env_name: str = DEFAULT_TOKEN_ENV) -> str:
    token = os.environ.get(env_name, "").strip()
    if not token:
        raise RuntimeError(
            f"Missing Notion token in environment variable {env_name}. "
            "Create a Notion internal integration, share the tracker database with it, "
            "and export the token before running sync."
        )
    return token
