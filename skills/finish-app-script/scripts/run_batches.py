#!/usr/bin/env python3
"""Rotating parent orchestrator for finish-app-script.

This is intentionally different from run_queue.py:

- run_queue.py spawns one tiny child agent per application row.
- run_batches.py spawns one fresh Codex CLI process for a small batch, usually
  two rows, and that process owns the live Chrome/Computer Use workflow.

The goal is to get the context-reset benefit without making every single row a
separate browser-worker process.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import select
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/fa_script_run_state.json")
TODO_PATH = Path("/tmp/fa_script_todo.md")
OUTPUT_DIR = Path("/tmp/fa_script_batch_outputs")
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_BATCH_SIZE = 2
DEFAULT_TIMEOUT_S = 1800
DEFAULT_CHILD_SANDBOX = "danger-full-access"
DONE_STATES = {"submitted", "manual", "archived", "skipped"}
SYSTEMIC_BLOCKER_TERMS = (
    "apple event error -1743",
    "apple event error -10005",
    "browser access blocker",
    "chrome computer use unavailable",
    "chrome/computer use timeout",
    "cgwindownotfound",
    "computer use access denied",
    "computer use approval denied",
    "computer use itself is unavailable",
    "connectioninvalid",
    "google chrome/com.google.chrome",
    "timeout for google chrome",
    "timeoutreached",
    "appnotfound(\"chrome\")",
)


BATCH_PROMPT = """\
Read skills/finish-app-script/OPERATING_CARD.md before starting. Follow the
standing answers and submission rules strictly, with this batch override:

Before doing browser work, read /tmp/fa_script_todo.md. It is the human-readable
handoff file for this monitored run; /tmp/fa_script_run_state.json remains the
machine-readable source of truth. After every row outcome, append one short note
to /tmp/fa_script_todo.md with: company, role, row key, state, confirmation
evidence if submitted, exact blocker/review item if manual, and whether a
handoff tab was left open. Before exiting the batch, append a final batch note
with any unresolved blockers or review tabs still open.

You are a fresh parent application agent, not a per-row subagent. Use Codex
Computer Use directly in this process. Prefer Google Chrome when it is
responsive, using app name "Google Chrome" or bundle id "com.google.Chrome";
if Chrome/Computer Use times out, immediately switch to Firefox using app name
"Firefox" or bundle id "org.mozilla.firefox". If Firefox's native file picker
shows the exact existing PDF selected but keeps Open disabled, treat that as a
browser-specific upload failure and retry the same public ATS form in Safari
using app name "Safari" or bundle id "com.apple.Safari". Do not use bare
"Chrome". Do not spawn subagents or parallel browser workers.

Rows whose notes, result, or blocker mention "upload-error redo", "Document
upload failed", or "Firefox picker" are known document-upload retries. For
those rows, use Safari for the ATS form from the start of the document-upload
step. Do not mark a known upload retry manual for a disabled Firefox Open
button; only mark manual if Safari also cannot attach the exact PDF.

Process up to {batch_size} queued application rows from
/tmp/fa_script_run_state.json, then exit cleanly. Before each row, reread the
state file and pick the first items[] entry with state == "queued". Keep one
browser flow active at a time.

For each row:
- Always open a brand-new browser tab before navigating to the jobLink, including
  the first row in this batch. Never navigate over an existing application,
  email, search, or handoff tab.
- Before drafting any FRQ, "why us" answer, values answer, achievement example,
  or project example, load Liam's factual
  context. Read the row's tailored resume source at <resume directory>/resume.tex
  when available, where <resume directory> is the directory containing resumePdf.
  Also read generic-resume/README.md and generic-resume/resume.tex when those
  files exist in the repo; they are the broader evidence bank. Use only Liam's
  actual resume/profile/project/tracker evidence. Never invent employers,
  internships, projects, tools, metrics, dates, credentials, or responsibilities.
  If a required answer cannot be grounded in those sources, use a supported
  adjacent example or mark the row manual for Liam review.
- Keep browser tabs organized by perceived confidence when possible: High Confidence /
  Ready Submit, Needs Review, Hard Blocker, and Submitted / Archived. If Chrome
  tab groups are not scriptable, leave tabs ordered in that bucket sequence and
  make the outcome note clear enough for Liam to identify the bucket.
- Complete the live application with the row's resumePdf. During file upload,
  the macOS file picker may default to the previous application's file; before
  confirming any upload, verify the selected path exactly matches the current
  row's resumePdf from /tmp/fa_script_run_state.json.
- Known upload-retry rows: if the row notes, result, or blocker mention
  "upload-error redo", "Document upload failed", or "Firefox picker", open the
  application URL in Safari before uploading documents and perform the upload
  there. This path has been verified on Uare.ai Greenhouse for both resume and
  resume. Do not spend the retry on Firefox unless Safari itself is unavailable.
- Robust file-picker method: when a native macOS file picker opens, do not
  navigate by clicking folders. Press Cmd+Shift+G, paste the exact absolute PDF
  path from /tmp/fa_script_run_state.json, press Return, then press Return/Open.
  If the file path contains spaces, still paste the raw absolute path. After the
  dialog closes, verify the rendered attached filename matches the current row's
  exact PDF filename. If the wrong prior resume remains attached, remove it and
  retry once with Cmd+Shift+G. If Firefox leaves Open disabled after pasting a
  full existing PDF path, press Escape, open the same application URL in Safari,
  and repeat the exact nested Browse/Cmd+Shift+G upload flow there before
  declaring the row manual.
- On Greenhouse-style upload widgets, click the nested "Browse..." button
  inside the Resume/CV control, not the outer "Attach" tab or label. The outer
  Attach control can open a picker state where a selected PDF still leaves Open
  disabled. Use "Browse..." first, then the Cmd+Shift+G exact path flow.
- Resume/CV fields are file-upload only. Never click "Enter manually", never
  paste resume text into an ATS form, and never submit with manually entered
  document text.
- Do not generate, render, write, paste, or upload cover letters. If a
  cover-letter field is optional, leave it blank. If a cover-letter field is
  required and cannot be skipped, leave the tab open, mark the row manual with
  blocker "Cover letter required; skipped by no-cover-letter policy", and
  continue.
- If an exact resume PDF cannot be attached after one retry, leave the tab
  open, mark the row manual with blocker "Document upload failed; manual attach
  required", and continue.
- Submit high-confidence applications when every required field is filled
  truthfully from standing answers, obvious profile facts, resume/profile
  evidence, projects, or concise FRQ/custom written drafts. Click the final Submit/Submit application
  button, wait for a confirmation page or confirmation text, capture it in
  confirmationEvidence, and set state to "submitted". Do not leave a
  high-confidence application staged or mark it manual merely because it is at
  the final submit button; final review is the point where high-confidence rows
  should be submitted.
- Before clicking final Submit, make a short explicit decision: "submit is safe
  because <reason>". Base the decision on the row's confidence score: only high
  confidence may submit after truthful completion. Medium and low confidence
  rows must not submit; fill every safe field and all answerable FRQs, mark the
  row manual with the exact item Liam needs to review, and leave the tab open.
- Treat these rendered answers as guardrails before final submit: authorized to
  work in the United States = Yes; now/future sponsorship required = No;
  comfortable working onsite/hybrid/in-office in NYC or San Francisco, including
  San Francisco 5 days/week = Yes. If any present answer differs, correct it. If
  you cannot correct it, mark manual and leave the tab open.
- Treat education dates as strict guardrails before final submit: University of
  Georgia, BS Computer Science, started Aug 2021, graduated Dec 2024. Never
  enter any graduation year before 2024, and never answer that Liam graduated
  before 2020. If a form asks whether Liam graduated before 2020, answer No. If
  any present rendered education answer differs, correct it. If you cannot
  correct it, mark manual and leave the tab open.
- Email 2FA, emailed verification codes, and magic links sent to
  liamvanpj@gmail.com are not blockers. Use Gmail access to retrieve the code
  or click the magic link, then continue the application. Escalate only if the
  email never arrives, expires, or the flow switches to SMS/authenticator-app
  verification.
- FRQ/custom written prompts should be completed whenever they can be answered
  truthfully from Liam's profile, resume, projects, standing answers, tracker
  notes, and the posting. Draft concise, specific, truthful answers and review
  them against the resume/profile evidence before final submit. Submit only if
  the row is high confidence; otherwise leave the tab open at the cleanest
  review point, mark manual with the exact FRQ/review item, and continue to the
  next row.
- Medium and low confidence rows must not be submitted. Fill safe fields,
  upload the correct resume when possible, complete answerable FRQs, leave the
  tab open at the cleanest review point, mark manual with the exact blocker or
  review item, and continue to the next row.
- Do not stall on a final-submit decision. Once the form is as complete as it
  safely can be, either submit with confirmation evidence or mark manual and
  exit/continue. Never hover at a staged final form waiting for confidence to
  improve.
- If submitted successfully and confirmation evidence is captured, close that
  application tab before starting the next row.
- For medium confidence, do not submit. Fill all safe fields and answerable
  FRQs, leave the tab at the cleanest review point, and mark manual with an
  exact review item. Keep that handoff tab open even if this Codex process is
  about to exit.
- For account creation, login, SMS/authenticator 2FA, interactive CAPTCHA,
  Workday, AI-deterrent verification, or other impossible-to-complete steps,
  mark manual with the exact blocker, leave any useful partially completed tab
  open for Liam, and continue to the next queued row. These are per-row outcomes,
  not hard stops for the batch.
- For closed/404/mismatched postings, mark archived.
- After any outcome, continue the next row from a brand-new tab when batch
  capacity remains. Do not reuse a submitted, partially completed, or handoff
  tab for another application.
- After every outcome, update /tmp/fa_script_run_state.json for that row:
  state, result, blocker when manual, confirmationEvidence when submitted,
  updatedAt.
- When submitted, run:
  python3 skills/gmail-application-refresh/scripts/update_application_status.py
  with --company, --role, --posting-key, --status Applied, --applied Yes, and a
  short application-submitted note; then refresh the visualizer cache with:
  python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

If Chrome/Computer Use itself is unavailable for a row, mark only the current
row manual with the exact browser-access blocker, then exit the batch cleanly.
Do not continue burning queued rows when the browser automation layer is
systemically unavailable.

Do not commit or push. The outer orchestrator owns commits.

Exit after {batch_size} row outcomes.
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        raise SystemExit(
            f"Missing run state at {STATE_PATH}.\n"
            "Run: python3 skills/finish-app-script/scripts/build_queue.py"
        )
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def queued_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in state.get("items", []) if item.get("state") == "queued"]


def state_counts(state: dict[str, Any]) -> dict[str, int]:
    counts = {"queued": 0, "submitted": 0, "manual": 0, "archived": 0, "skipped": 0}
    for item in state.get("items", []):
        value = str(item.get("state") or "")
        if value in counts:
            counts[value] += 1
    return counts


def format_counts(counts: dict[str, int]) -> str:
    return (
        f"queued={counts['queued']} submitted={counts['submitted']} "
        f"manual={counts['manual']} archived={counts['archived']} skipped={counts['skipped']}"
    )


def append_todo(note: str) -> None:
    TODO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TODO_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"- {now_iso()} - {note}\n")


def completed_keys(state: dict[str, Any]) -> set[str]:
    return {
        str(item.get("key") or "")
        for item in state.get("items", [])
        if item.get("state") in DONE_STATES
    }


def is_systemic_blocker(item: dict[str, Any]) -> bool:
    if item.get("state") != "manual":
        return False
    haystack = " ".join(
        str(item.get(field) or "")
        for field in ("blocker", "result", "notes")
    ).lower()
    return any(term in haystack for term in SYSTEMIC_BLOCKER_TERMS)


def mark_manual(item: dict[str, Any], blocker: str) -> None:
    state = load_state()
    key = str(item.get("key") or "")
    changed = False
    for row in state.get("items", []):
        if str(row.get("key") or "") != key:
            continue
        if row.get("state") in DONE_STATES:
            return
        row["state"] = "manual"
        row["blocker"] = blocker
        row["result"] = f"Manual: {blocker}"
        row["updatedAt"] = now_iso()
        changed = True
        break
    if changed:
        STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        append_todo(f"{item.get('company')} | manual | {blocker}")


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "batch"


def child_prompt(batch_size: int) -> str:
    return BATCH_PROMPT.format(batch_size=batch_size)


def run_codex_batch(
    *,
    batch_number: int,
    batch_size: int,
    model: str,
    reasoning_effort: str,
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
        "-c",
        f'model_reasoning_effort="{reasoning_effort}"',
        "-o",
        str(output_file),
        child_prompt(batch_size),
    ]
    if dry_run:
        print("  dry run command:")
        print("  " + " ".join(cmd[:10]) + " ...")
        return 0, "dry-run", output_file
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    chunks: list[str] = []
    started = time.time()
    last_heartbeat = started
    try:
        while True:
            now = time.time()
            if now - started > timeout_s:
                process.kill()
                message = f"timeout after {timeout_s}s"
                chunks.append(message)
                output_file.write_text("\n".join(chunks) + "\n", encoding="utf-8")
                return -1, "\n".join(chunks), output_file

            ready, _, _ = select.select([process.stdout], [], [], 1)
            if ready:
                line = process.stdout.readline()
                if line:
                    chunks.append(line)
            rc = process.poll()
            if rc is not None:
                remainder = process.stdout.read()
                if remainder:
                    chunks.append(remainder)
                combined = "".join(chunks)
                if combined and not output_file.exists():
                    output_file.write_text(combined, encoding="utf-8")
                elif combined:
                    with output_file.open("a", encoding="utf-8") as handle:
                        handle.write("\n\n--- codex exec stdout/stderr ---\n")
                        handle.write(combined)
                return rc, combined, output_file

            if now - last_heartbeat >= 30:
                elapsed = int(now - started)
                print(f"  child still running after {elapsed}s | output: {output_file}", flush=True)
                last_heartbeat = now
    finally:
        if process.poll() is None:
            process.kill()


def commit_and_push(*, push: bool, message: str) -> bool:
    paths = [
        "application-trackers/applications.md",
        "application-trackers/outcomes.jsonl",
        "application-visualizer/src/data/tracker-data.json",
        "application-visualizer/src/data/pipeline-metrics.json",
    ]
    add = subprocess.run(["git", "-C", str(ROOT), "add", *paths], capture_output=True, text=True)
    if add.returncode != 0:
        print(f"  git add failed: {add.stderr.strip()}")
        return False
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet"], capture_output=True)
    if diff.returncode == 0:
        print("  Nothing staged for tracker/cache; skipping commit.")
        return False
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        print(f"  git commit failed: {commit.stderr.strip()}")
        return False
    print(f"  committed: {message}")
    if push:
        branch = subprocess.run(
            ["git", "-C", str(ROOT), "branch", "--show-current"],
            capture_output=True,
            text=True,
        )
        branch_name = branch.stdout.strip() or "HEAD"
        pushed = subprocess.run(
            ["git", "-C", str(ROOT), "push", "origin", branch_name],
            capture_output=True,
            text=True,
        )
        if pushed.returncode != 0:
            print(f"  git push failed: {pushed.stderr.strip()}")
            return False
        print(f"  pushed origin/{branch_name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate fresh Codex CLI parents through application batches.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Rows per fresh Codex process")
    parser.add_argument("--max-batches", type=int, default=0, help="Stop after N batches; 0 drains the queue")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model for codex exec (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh"),
        default="medium",
        help="Reasoning effort for child codex exec processes (default: medium)",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-batch timeout in seconds")
    parser.add_argument(
        "--child-sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default=DEFAULT_CHILD_SANDBOX,
        help=f"Sandbox for each fresh Codex process (default: {DEFAULT_CHILD_SANDBOX})",
    )
    parser.add_argument("--no-commit", action="store_true", help="Skip auto-commit every 5 submitted/archived outcomes")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push")
    parser.add_argument("--dry-run", action="store_true", help="Print the batches without invoking codex exec")
    args = parser.parse_args()

    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")

    state = load_state()
    counts = state_counts(state)
    print(
        "finish-app-script rotating batch runner | "
        f"queued: {counts['queued']} | batch-size: {args.batch_size} | "
        f"model: {args.model} | timeout: {args.timeout}s"
    )

    batch_number = 0
    terminal_success_since_commit = 0
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
        append_todo(
            "Batch "
            f"{batch_number} starting with {len(batch_preview)} row(s); "
            f"counts {format_counts(state_counts(before))}; "
            f"rows: "
            + "; ".join(
                f"{item.get('company')} | {item.get('role')} | {item.get('key')}"
                for item in batch_preview
            )
        )

        before_done = completed_keys(before)
        before_counts = state_counts(before)
        started = time.time()
        rc, output, output_file = run_codex_batch(
            batch_number=batch_number,
            batch_size=args.batch_size,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_s=args.timeout,
            child_sandbox=args.child_sandbox,
            dry_run=args.dry_run,
        )
        elapsed = time.time() - started
        after = load_state()
        after_counts = state_counts(after)
        after_done = completed_keys(after)
        newly_done = after_done - before_done
        new_submitted = max(0, after_counts["submitted"] - before_counts["submitted"])
        new_archived = max(0, after_counts["archived"] - before_counts["archived"])
        terminal_success_since_commit += new_submitted + new_archived

        print(f"  exit rc={rc} after {elapsed:.0f}s | output: {output_file}")
        append_todo(
            f"Batch {batch_number} finished rc={rc} after {elapsed:.0f}s; "
            f"child output `{output_file}`; counts {format_counts(after_counts)}."
        )
        if newly_done:
            by_key = {str(item.get("key") or ""): item for item in after.get("items", [])}
            for key in sorted(newly_done):
                item = by_key.get(key, {})
                state_value = item.get("state")
                blocker = item.get("blocker") or item.get("result") or ""
                line = f"{item.get('company')} | {state_value}"
                if blocker:
                    line += f" | {blocker}"
                summary.append(line)
                print(f"  {line}")
                append_todo(
                    f"{item.get('company')} | {item.get('role')} | {key} | "
                    f"{state_value} | {blocker or 'no blocker'}"
                )
        else:
            tail = output.strip().splitlines()[-3:]
            print("  no state progress detected")
            if tail:
                print("  last output:")
                for line in tail:
                    print(f"    {line}")
            if batch_preview:
                blocker = "Batch made no state progress; manual review required, runner continuing"
                print(f"  marking current row manual: {batch_preview[0].get('company')} | {blocker}")
                mark_manual(batch_preview[0], blocker)
                after = load_state()
                after_counts = state_counts(after)
                after_done = completed_keys(after)
                newly_done = after_done - before_done
            else:
                continue

        if rc != 0:
            print("  child exited non-zero; treating as a per-row/batch blocker and continuing.")
            append_todo(f"Batch {batch_number} child exited non-zero; runner continuing.")
            continue

        if not args.no_commit and terminal_success_since_commit >= 5:
            today = dt.date.today().isoformat()
            print(f"\nCommitting {terminal_success_since_commit} submitted/archived application outcome(s)...")
            committed = commit_and_push(
                push=not args.no_push,
                message=f"Apply: {terminal_success_since_commit} submitted or archived outcomes {today}",
            )
            append_todo(
                f"Commit threshold reached for {terminal_success_since_commit} submitted/archived outcome(s); "
                f"commit/push {'succeeded' if committed else 'had no committed changes or failed'}."
            )
            terminal_success_since_commit = 0

    if not args.no_commit and terminal_success_since_commit:
        today = dt.date.today().isoformat()
        print(f"\nFinal commit for {terminal_success_since_commit} submitted/archived application outcome(s)...")
        committed = commit_and_push(
            push=not args.no_push,
            message=f"Apply: {terminal_success_since_commit} submitted or archived outcomes {today}",
        )
        append_todo(
            f"Final commit for {terminal_success_since_commit} submitted/archived outcome(s); "
            f"commit/push {'succeeded' if committed else 'had no committed changes or failed'}."
        )

    final_counts = state_counts(load_state())
    append_todo(f"run_batches complete with final counts {format_counts(final_counts)}.")
    print("\nSummary")
    print("=" * 7)
    print(
        f"queued={final_counts['queued']} submitted={final_counts['submitted']} "
        f"manual={final_counts['manual']} archived={final_counts['archived']} skipped={final_counts['skipped']}"
    )
    for line in summary:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
