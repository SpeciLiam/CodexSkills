#!/usr/bin/env python3
"""Write a durable manual-application handoff entry."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HANDOFF = ROOT / "application-trackers" / "manual-application-handoffs.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upsert a manual application handoff block.")
    parser.add_argument("--company", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--posting-key", required=True)
    parser.add_argument("--job-url", default="")
    parser.add_argument("--apply-url", default="")
    parser.add_argument("--resume-pdf", default="")
    parser.add_argument("--blocker", required=True)
    parser.add_argument("--next-action", required=True)
    parser.add_argument(
        "--answer",
        action="append",
        default=[],
        help="Filled answer summary, repeatable. Example: 'Work authorization: Yes'",
    )
    parser.add_argument(
        "--frq",
        action="append",
        default=[],
        help="FRQ draft, repeatable. Use 'Question ::: Draft answer'.",
    )
    parser.add_argument("--notes", default="")
    parser.add_argument("--handoff-file", type=Path, default=DEFAULT_HANDOFF)
    return parser.parse_args()


def block_for(args: argparse.Namespace) -> str:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [
        f"<!-- posting-key: {args.posting_key} -->",
        f"## {args.company} - {args.role}",
        f"Updated: {now}",
        f"Posting Key: {args.posting_key}",
        f"Job URL: {args.job_url or 'not recorded'}",
        f"Apply URL: {args.apply_url or 'not recorded'}",
        f"Resume PDF: {args.resume_pdf or 'not recorded'}",
        "",
        "Blocker:",
        args.blocker.strip(),
        "",
        "Next Action:",
        args.next_action.strip(),
        "",
        "Filled / Selected Answers:",
    ]
    if args.answer:
        lines.extend(f"- {answer.strip()}" for answer in args.answer if answer.strip())
    else:
        lines.append("- not recorded")
    lines.extend(["", "FRQ Drafts:"])
    if args.frq:
        for frq in args.frq:
            question, sep, draft = frq.partition(":::")
            if sep:
                lines.append(f"- Question: {question.strip()}")
                lines.append(f"  Draft: {draft.strip()}")
            else:
                lines.append(f"- {frq.strip()}")
    else:
        lines.append("- none")
    lines.extend(["", "Notes:", args.notes.strip() or "none", ""])
    return "\n".join(lines)


def upsert(existing: str, marker: str, block: str) -> str:
    if not existing.strip():
        header = (
            "# Manual Application Handoffs\n\n"
            "Use this file to quickly resume applications that automation could not safely submit.\n"
            "Each block is keyed by posting key and can be replaced by later retry attempts.\n\n"
        )
        return header + block + "\n"
    start = existing.find(marker)
    if start == -1:
        return existing.rstrip() + "\n\n" + block + "\n"
    next_start = existing.find("\n<!-- posting-key:", start + len(marker))
    if next_start == -1:
        return existing[:start].rstrip() + "\n\n" + block + "\n"
    return existing[:start].rstrip() + "\n\n" + block + "\n" + existing[next_start:]


def main() -> int:
    args = parse_args()
    args.handoff_file.parent.mkdir(parents=True, exist_ok=True)
    marker = f"<!-- posting-key: {args.posting_key} -->"
    block = block_for(args)
    existing = args.handoff_file.read_text(encoding="utf-8") if args.handoff_file.exists() else ""
    args.handoff_file.write_text(upsert(existing, marker, block), encoding="utf-8")
    print(args.handoff_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
