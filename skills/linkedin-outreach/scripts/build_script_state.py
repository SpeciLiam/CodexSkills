#!/usr/bin/env python3
"""Build a durable run state for bounded LinkedIn outreach batches.

This mirrors the finish-app-script pattern: turn the markdown batch tracker into
a compact /tmp state file, then let a rotating runner give fresh Codex processes
small, explicit chunks of work.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
BATCH_SCRIPTS = ROOT / "skills" / "linkedin-outreach-batch" / "scripts"
if str(BATCH_SCRIPTS) not in sys.path:
    sys.path.append(str(BATCH_SCRIPTS))

from build_recruiter_batch import CONTACT_CONFIG, first_link  # type: ignore
from mark_batch_decision import extract_rows  # type: ignore


DEFAULT_STATE_PATH = Path("/tmp/linkedin_outreach_run_state.json")
DEFAULT_MODE = "label"
OUTCOME_DONE = {"sent", "skipped", "blocked"}


def norm(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def has_real_profile(row: dict[str, str], config: dict[str, object]) -> bool:
    name = row.get(str(config["name_column"]), "").strip()
    profile = first_link(row.get(str(config["profile_column"]), "")).strip()
    if not name or not profile:
        return False
    return "/search/" not in profile and "linkedin.com/in/" in profile


def item_key(row: dict[str, str], contact_type: str) -> str:
    posting_key = row.get("Posting Key", "").strip()
    return f"{contact_type}:{posting_key}" if posting_key else f"{contact_type}:{row.get('Company', '')}:{row.get('Role', '')}"


def row_item(row: dict[str, str], contact_type: str, mode: str, config: dict[str, object]) -> dict[str, Any]:
    return {
        "key": item_key(row, contact_type),
        "state": "queued",
        "mode": mode,
        "contactType": contact_type,
        "batch": row.get("Batch", ""),
        "company": row.get("Company", ""),
        "role": row.get("Role", ""),
        "postingKey": row.get("Posting Key", ""),
        "fitScore": row.get("Fit Score", ""),
        "status": row.get("Status", ""),
        "contactName": row.get(str(config["name_column"]), ""),
        "contactProfile": first_link(row.get(str(config["profile_column"]), "")),
        "contactPosition": row.get(str(config["position_column"]), ""),
        "route": row.get("Route", ""),
        "connectionNote": row.get("Connection Note", ""),
        "approval": row.get("Approval", ""),
        "outcome": row.get("Outcome", ""),
        "lastChecked": row.get("Last Checked", ""),
        "notes": row.get("Notes", ""),
    }


def should_queue(row: dict[str, str], *, mode: str, config: dict[str, object]) -> bool:
    approval = norm(row.get("Approval", ""))
    outcome = norm(row.get("Outcome", ""))
    if outcome in OUTCOME_DONE:
        return False

    if mode == "send":
        return (
            approval == "approved"
            and has_real_profile(row, config)
            and bool(row.get("Connection Note", "").strip())
            and outcome in {"", "not reached out"}
        )

    if mode == "verify":
        if not has_real_profile(row, config):
            return False
        notes = norm(row.get("Notes", ""))
        today_marker = f"verified current {norm(row.get('Company', ''))}"
        if today_marker in notes and date.today().isoformat() in row.get("Notes", ""):
            return False
        if "current-company engineer verification required" in notes:
            return True
        if "verified current" not in notes and "not a verified person" not in notes:
            return True
        return approval in {"needs approval", "approved"}

    missing_label = norm(str(config["missing_approval"]))
    if approval == missing_label:
        return True
    if approval == "needs approval" and not has_real_profile(row, config):
        return True
    return False


def load_rows(contact_type: str) -> tuple[list[dict[str, str]], dict[str, object], Path]:
    if contact_type not in CONTACT_CONFIG:
        raise SystemExit(f"Unknown contact type '{contact_type}'. Known: {', '.join(sorted(CONTACT_CONFIG))}")
    config = CONTACT_CONFIG[contact_type]
    path = Path(config["output"])
    if not path.exists():
        raise SystemExit(
            f"Missing batch tracker: {path}\n"
            f"Run: python3 skills/linkedin-outreach-batch/scripts/build_recruiter_batch.py --contact-type {contact_type}"
        )
    rows = extract_rows(path.read_text(encoding="utf-8"), str(config["heading"]))
    return rows, config, path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build /tmp state for bounded LinkedIn outreach work.")
    parser.add_argument("--contact-type", choices=sorted(CONTACT_CONFIG), default="engineer")
    parser.add_argument("--mode", choices=("label", "send", "verify"), default=DEFAULT_MODE)
    parser.add_argument("--limit", type=int, default=0, help="Optional max queued rows")
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    args = parser.parse_args()

    rows, config, path = load_rows(args.contact_type)
    items = [
        row_item(row, args.contact_type, args.mode, config)
        for row in rows
        if should_queue(row, mode=args.mode, config=config)
    ]
    if args.limit > 0:
        items = items[: args.limit]

    payload = {
        "schema": "linkedin-outreach-script/v1",
        "contactType": args.contact_type,
        "mode": args.mode,
        "source": str(path),
        "items": items,
    }
    args.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Wrote {args.state_path} with {len(items)} queued {args.contact_type} "
        f"{args.mode} item(s) from {path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
