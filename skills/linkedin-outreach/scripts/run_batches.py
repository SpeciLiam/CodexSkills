#!/usr/bin/env python3
"""Rotate fresh Codex CLI parents through bounded LinkedIn outreach batches."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/linkedin_outreach_run_state.json")
OUTPUT_DIR = Path("/tmp/linkedin_outreach_batch_outputs")
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_BATCH_SIZE = 3
DEFAULT_TIMEOUT_S = 1200
DEFAULT_CHILD_SANDBOX = "danger-full-access"
DONE_STATES = {"labeled", "verified", "sent", "manual", "blocked", "skipped"}
SYSTEMIC_BLOCKER_TERMS = (
    "apple event error -1743",
    "browser access blocker",
    "chrome computer use unavailable",
    "computer use access denied",
    "computer use approval denied",
    "computer use itself is unavailable",
    "linkedin login",
    "linkedin signed out",
)


BATCH_PROMPT = """\
Read skills/linkedin-outreach/OPERATING_CARD.md before starting. This is a
fresh, bounded LinkedIn outreach parent process. Use Codex Computer Use directly
for Google Chrome in this process. Do not spawn subagents or parallel browser
workers.

Process up to {batch_size} queued item(s) from
/tmp/linkedin_outreach_run_state.json, then exit cleanly. Before each item,
reread the state file and pick the first items[] entry with state == "queued".
Keep one LinkedIn flow active at a time.

The state file mode is "label", "verify", or "send":

LABEL mode:
- Goal: replace missing or fallback contacts with one verified {contact_type}
  profile and a <=300 character note.
- Search LinkedIn in Chrome for the company, role/team context, and lane. Prefer
  current-company people with title/team relevance; for engineers, senior+ or
  adjacent SWE/FDE/backend/full-stack people are preferred.
- Never approve or send in label mode.
- Reject search-result fallback rows as completed contacts. Open/verify the
  actual profile when possible.
- When a credible contact is found, run:
  python3 skills/linkedin-outreach-batch/scripts/mark_batch_decision.py
    --contact-type <contactType>
    --posting-key <postingKey>
    --contact-name <name>
    --contact-profile <linkedin profile URL>
    --contact-position <title>
    --connection-note <short note>
    --approval "Needs approval"
    --notes "<why this person is credible>"
- Then update that state item to state="labeled", result, contactName,
  contactProfile, contactPosition, connectionNote, updatedAt.
- If no credible person can be found quickly, update the state item to
  state="manual" with blocker="No verified {contact_type} found" and a short
  result describing the attempted search.

VERIFY mode:
- Goal: audit an existing named engineer row and make sure the person currently
  works at the row's company before Liam approves outreach.
- Open the stored contactProfile and verify the person's current headline or
  experience section. If LinkedIn blocks access, use web search snippets only as
  secondary evidence; do not call the row verified from stale cached text alone.
- Mark verified only when the current profile/headline/experience explicitly
  indicates the target company and the title is an engineer, software engineer,
  founding engineer, FDE, data/software engineer, or similarly relevant
  technical role.
- If verified, run:
  python3 skills/linkedin-outreach-batch/scripts/mark_batch_decision.py
    --contact-type <contactType>
    --posting-key <postingKey>
    --approval "Needs approval"
    --notes "Verified current <company> <technical title> via LinkedIn profile on <YYYY-MM-DD>."
- Then update the state item to state="verified", result, contactPosition when
  corrected, updatedAt.
- If the profile no longer shows current employment at the company, is a search
  result/fallback, is unrelated, or cannot be verified confidently, run:
  python3 skills/linkedin-outreach-batch/scripts/mark_batch_decision.py
    --contact-type <contactType>
    --posting-key <postingKey>
    --approval "Needs engineer"
    --outcome "Not reached out"
    --notes "Verification failed: <exact reason>. Current-company engineer required before approval/outreach."
- Then update the state item to state="manual" with blocker and result.

SEND mode:
- Goal: send only already-approved connection invites.
- The item must already have approval == Approved, a real linkedin.com/in/
  profile, a contact name, and a non-placeholder connection note. If not, mark
  state="manual" with an exact blocker.
- Open the profile in Chrome. If a free InMail/message flow is available, send
  the existing connection note there. If not, use the normal Connect flow and
  send the existing connection note exactly as written unless LinkedIn's
  character limit forces a shorter version that preserves the same meaning.
- If free InMail/message and Connect are both unavailable, or the profile is
  restricted/gone, or LinkedIn asks for login/security verification, do not work
  around it. Run mark_batch_decision.py with --outcome Blocked or Skipped, then
  mark the state item blocked/skipped with the exact blocker.
- After sending, run:
  python3 skills/linkedin-outreach-batch/scripts/mark_batch_decision.py
    --contact-type <contactType> --posting-key <postingKey> --outcome Sent
    --notes "Invite sent via bounded outreach runner"
- Also run:
  python3 skills/linkedin-outreach/scripts/update_outreach_status.py
    --contact-type <contactType> --posting-key <postingKey>
    --outcome sent --company <company> --role <role>
    --contact-name <contactName> --profile-url <contactProfile>
- Then update the state item to state="sent", result, updatedAt.

For every outcome, write the item update directly into
/tmp/linkedin_outreach_run_state.json. Include blocker for manual/blocked items
and result for all items. Stop early if Chrome/Computer Use or LinkedIn login is
systemically unavailable; mark only the current item with the exact blocker and
exit so the outer runner can stop safely.

Do not commit or push. The outer orchestrator owns commits.
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        raise SystemExit(
            f"Missing run state at {STATE_PATH}.\n"
            "Run: python3 skills/linkedin-outreach/scripts/build_script_state.py"
        )
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def queued_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in state.get("items", []) if item.get("state") == "queued"]


def state_counts(state: dict[str, Any]) -> dict[str, int]:
    counts = {"queued": 0, "labeled": 0, "verified": 0, "sent": 0, "manual": 0, "blocked": 0, "skipped": 0}
    for item in state.get("items", []):
        value = str(item.get("state") or "")
        if value in counts:
            counts[value] += 1
    return counts


def completed_keys(state: dict[str, Any]) -> set[str]:
    return {
        str(item.get("key") or "")
        for item in state.get("items", [])
        if item.get("state") in DONE_STATES
    }


def is_systemic_blocker(item: dict[str, Any]) -> bool:
    if item.get("state") not in {"manual", "blocked"}:
        return False
    haystack = " ".join(
        str(item.get(field) or "")
        for field in ("blocker", "result", "notes")
    ).lower()
    return any(term in haystack for term in SYSTEMIC_BLOCKER_TERMS)


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "batch"


def child_prompt(batch_size: int, contact_type: str) -> str:
    return BATCH_PROMPT.format(batch_size=batch_size, contact_type=contact_type)


def run_codex_batch(
    *,
    batch_number: int,
    batch_size: int,
    contact_type: str,
    model: str,
    timeout_s: int,
    child_sandbox: str,
    dry_run: bool,
) -> tuple[int, str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"batch_{batch_number:03d}_{safe_filename(now_iso())}.txt"
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--cd",
        str(ROOT),
        "--sandbox",
        child_sandbox,
        "-m",
        model,
        "-o",
        str(output_file),
        child_prompt(batch_size, contact_type),
    ]
    if dry_run:
        print("  dry run command:")
        print("  " + " ".join(cmd[:10]) + " ...")
        return 0, "dry-run", output_file
    try:
        result = subprocess.run(cmd, timeout=timeout_s, capture_output=True, text=True)
        combined = (result.stdout or "") + (result.stderr or "")
        if combined and not output_file.exists():
            output_file.write_text(combined, encoding="utf-8")
        elif combined:
            with output_file.open("a", encoding="utf-8") as handle:
                handle.write("\n\n--- codex exec stdout/stderr ---\n")
                handle.write(combined)
        return result.returncode, combined, output_file
    except subprocess.TimeoutExpired as exc:
        message = f"timeout after {timeout_s}s"
        if exc.stdout:
            message += f"\n{exc.stdout}"
        if exc.stderr:
            message += f"\n{exc.stderr}"
        output_file.write_text(message, encoding="utf-8")
        return -1, message, output_file


def commit_and_push(*, push: bool, message: str) -> bool:
    paths = [
        "application-trackers/applications.md",
        "application-trackers/linkedin-engineer-batches.md",
        "application-trackers/linkedin-recruiter-batches.md",
        "application-visualizer/src/data/tracker-data.json",
    ]
    existing_paths = [path for path in paths if (ROOT / path).exists()]
    add = subprocess.run(["git", "-C", str(ROOT), "add", *existing_paths], capture_output=True, text=True)
    if add.returncode != 0:
        print(f"  git add failed: {add.stderr.strip()}")
        return False
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"], capture_output=True)
    if diff.returncode == 0:
        print("  Nothing staged for outreach trackers; skipping commit.")
        return False
    commit = subprocess.run(["git", "-C", str(ROOT), "commit", "-m", message], capture_output=True, text=True)
    if commit.returncode != 0:
        print(f"  git commit failed: {commit.stderr.strip()}")
        return False
    print(f"  committed: {message}")
    if push:
        branch = subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"], capture_output=True, text=True)
        branch_name = branch.stdout.strip() or "HEAD"
        pushed = subprocess.run(["git", "-C", str(ROOT), "push", "origin", branch_name], capture_output=True, text=True)
        if pushed.returncode != 0:
            print(f"  git push failed: {pushed.stderr.strip()}")
            return False
        print(f"  pushed origin/{branch_name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate fresh Codex CLI parents through LinkedIn outreach batches.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Rows per fresh Codex process")
    parser.add_argument("--max-batches", type=int, default=0, help="Stop after N batches; 0 drains the queue")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model for codex exec (default: {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-batch timeout in seconds")
    parser.add_argument(
        "--child-sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default=DEFAULT_CHILD_SANDBOX,
        help=f"Sandbox for each fresh Codex process (default: {DEFAULT_CHILD_SANDBOX})",
    )
    parser.add_argument("--no-commit", action="store_true", help="Skip auto-commit")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push")
    parser.add_argument("--dry-run", action="store_true", help="Print the batches without invoking codex exec")
    args = parser.parse_args()

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")

    state = load_state()
    contact_type = str(state.get("contactType") or "engineer")
    mode = str(state.get("mode") or "label")
    counts = state_counts(state)
    print(
        "linkedin-outreach rotating batch runner | "
        f"mode: {mode} | contact-type: {contact_type} | queued: {counts['queued']} | "
        f"batch-size: {args.batch_size} | model: {args.model} | timeout: {args.timeout}s"
    )

    batch_number = 0
    done_since_commit = 0
    summary: list[str] = []

    while True:
        before = load_state()
        pending = queued_items(before)
        if not pending:
            print("\nQueue drained.")
            break
        if args.max_batches and batch_number >= args.max_batches:
            print(f"\nReached --max-batches {args.max_batches}, stopping.")
            break

        batch_number += 1
        batch_preview = pending[: args.batch_size]
        print(f"\nBatch {batch_number}:")
        for item in batch_preview:
            print(f"  - {item.get('company')} | {item.get('role')} | {item.get('key')}")

        before_done = completed_keys(before)
        started = time.time()
        rc, output, output_file = run_codex_batch(
            batch_number=batch_number,
            batch_size=args.batch_size,
            contact_type=contact_type,
            model=args.model,
            timeout_s=args.timeout,
            child_sandbox=args.child_sandbox,
            dry_run=args.dry_run,
        )
        elapsed = time.time() - started
        after = load_state()
        after_done = completed_keys(after)
        newly_done = after_done - before_done
        done_since_commit += len(newly_done)

        print(f"  exit rc={rc} after {elapsed:.0f}s | output: {output_file}")
        if newly_done:
            by_key = {str(item.get("key") or ""): item for item in after.get("items", [])}
            systemic_blocked = False
            for key in sorted(newly_done):
                item = by_key.get(key, {})
                state_value = item.get("state")
                detail = item.get("blocker") or item.get("result") or ""
                line = f"{item.get('company')} | {state_value}"
                if detail:
                    line += f" | {detail}"
                summary.append(line)
                print(f"  {line}")
                systemic_blocked = systemic_blocked or is_systemic_blocker(item)
            if systemic_blocked:
                print("  systemic browser/LinkedIn blocker detected; stopping before launching another batch.")
                break
        else:
            tail = output.strip().splitlines()[-3:]
            print("  no state progress detected")
            if tail:
                print("  last output:")
                for line in tail:
                    print(f"    {line}")
            break

        if rc != 0:
            print("  child exited non-zero; stopping for inspection.")
            break

        if not args.no_commit and done_since_commit >= 10:
            today = dt.date.today().isoformat()
            print(f"\nCommitting {done_since_commit} outreach update(s)...")
            commit_and_push(
                push=not args.no_push,
                message=f"Outreach: {done_since_commit} {contact_type} {mode} updates {today}",
            )
            done_since_commit = 0

    if not args.no_commit and done_since_commit:
        today = dt.date.today().isoformat()
        print(f"\nFinal commit for {done_since_commit} outreach update(s)...")
        commit_and_push(
            push=not args.no_push,
            message=f"Outreach: {done_since_commit} {contact_type} {mode} updates {today}",
        )

    final_counts = state_counts(load_state())
    print("\nSummary")
    print("=" * 7)
    print(
        f"queued={final_counts['queued']} labeled={final_counts['labeled']} verified={final_counts['verified']} sent={final_counts['sent']} "
        f"manual={final_counts['manual']} blocked={final_counts['blocked']} skipped={final_counts['skipped']}"
    )
    for line in summary:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
