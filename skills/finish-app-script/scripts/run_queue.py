#!/usr/bin/env python3
"""Per-row worker orchestrator for finish-app-script.

For each queued row in /tmp/fa_script_run_state.json:
  1. Build a tight per-row prompt
  2. Spawn a Codex or Claude worker for exactly one row
  3. Wait up to --timeout seconds
  4. Re-read the state file → check the row's outcome (submitted|manual|archived)
  5. Update counters; run circuit breaker; commit/push every 5 confirmed
  6. Loop to next queued row

The orchestrator owns: queue iteration, timeouts, circuit breaker, commit/push.
The spawned agent owns: browser flow, form filling, submission, state writeback.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = ROOT / "skills" / "finish-app-script"
OPERATING_CARD = SKILL_DIR / "OPERATING_CARD.md"
STATE_PATH = Path("/tmp/fa_script_run_state.json")
OUTPUT_DIR = Path("/tmp/fa_script_outputs")
TRACKER_PATH = "application-trackers/applications.md"
CACHE_PATH = "application-visualizer/src/data/tracker-data.json"

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_TIMEOUT_S = 1200
DEFAULT_CHILD_SANDBOX = "danger-full-access"
DEFAULT_REASONING_EFFORT = "medium"
CIRCUIT_BREAKER_THRESHOLD = 3
COMMIT_EVERY = 5

DONE_STATES = {"submitted", "manual", "archived", "skipped"}


PROMPT_TEMPLATE = """\
Read skills/finish-app-script/OPERATING_CARD.md before starting. Follow it strictly.

You are completing ONE job application. Single-row mode: process this row, attempt every safe step, write the outcome, and exit. Do not process another application.

Company: {company}
Role: {role}
URL: {jobLink}
Resume PDF: {resumePdf}
Posting key: {postingKey}
Source: {source}
State item key: {key}
Notes carried from tracker: {notes}

If notes say Liam approved a draft/answer from a prior manual handoff, treat
that answer as approved for this retry. Paste or reuse the approved grounded
answer, then submit if the correct resume is attached and no true blocker
remains. Do not re-mark the row manual solely because the approved answer is an
FRQ/custom written response.

Use Liam's Chrome profile for the live application flow. LinkedIn sourcing may
use the Ben profile, but actual applications must use Chrome profile name
"Liam", account liamvanpj@gmail.com, profile directory "Default" -- not Ben /
bendov1010@gmail.com / "Profile 1". Before opening the ATS/application URL,
make sure the active Google Chrome window is Liam's profile. If needed, open it
with: open -na "Google Chrome" --args --profile-directory="Default"; or switch
via Chrome's profile menu. Then use the installed Codex Chrome plugin first for
the live ATS/application flow so Liam's real cookies, saved logins, existing
tabs, extension-backed uploads, and portal state are preserved. Use Codex
Computer Use (computer-use@openai-bundled) only as a fallback if the Chrome
plugin cannot communicate with Chrome or cannot operate the current page.

Before drafting any FRQ, "why us" answer, values answer, achievement example,
or project example, load Liam's factual context. Read the row's tailored resume
source at <resume directory>/resume.tex when available, where <resume directory>
is the directory containing Resume PDF. Also read generic-resume/README.md and
generic-resume/resume.tex when those files exist in the repo; they are the
broader evidence bank. Use only Liam's actual resume/profile/project/tracker
evidence. Never invent employers, internships, projects, tools, metrics, dates,
credentials, or responsibilities. If a required answer cannot be grounded in
those sources, use a supported adjacent example or mark the row manual for Liam
review.

Treat prior answered application questions as known answers. Before marking a routine question uncertain, check skills/linkedin-easy-apply-nodriver/references/application-defaults.md, the operating card, current tracker notes, and prior submitted rows for the same question pattern. If the same question has already been answered safely, reuse that answer and keep moving.

Do not generate, render, write, paste, or upload cover letters. If a
cover-letter field is optional, leave it blank. If a cover-letter field is
required and cannot be skipped, leave the tab open and set state="manual" with
blocker "Cover letter required; skipped by no-cover-letter policy".
If the Chrome plugin reports that resume upload is blocked, leave the tab open
and set state="manual" with blocker "Chrome plugin file upload blocked; enable
file URL access for the Codex Chrome Extension in chrome://extensions".

Dropdowns / typeahead / combo boxes / multi-select: open the menu, click the actual option, verify the rendered chip/value. Never just type into a typeahead and move on — the field will be silently rejected.

Email 2FA / verification codes / magic links sent to liamvanpj@gmail.com are NOT blockers. Use the gmail@openai-curated MCP to read the inbox, extract the code or click the magic link in Chrome (already signed in), and continue. Only escalate to manual if the email never arrives, expires, or the verification switches to SMS / authenticator-app 2FA.

Confidence decision after final review:
- HIGH (every required field covered, no blocker): click submit. Standing answers, prior answered same-question patterns, and routine acknowledgements such as privacy/data-processing, equal-opportunity, recruiting contact consent, background-check disclosure notices, at-will employment notices, electronic communication notices, and truthful application-accuracy certifications count as covered and should not downgrade confidence. If a verification code is emailed, retrieve it via Gmail MCP and complete. Capture confirmation evidence. Run skills/gmail-application-refresh/scripts/update_application_status.py with --status Applied --applied Yes. Set state="submitted".
- FRQ REVIEW OK: If an FRQ/custom written answer is drafted but should get Liam review, do not submit. Leave the tab open at the cleanest pre-submit point, set state="manual" with blocker/result containing the exact FRQ question, the drafted answer, and "awaiting Liam approval". In your final response, say why it was not submitted and include the FRQ draft. If Liam approves that FRQ answer in chat later, a follow-up worker may return to the open tab, submit the prepared application, capture confirmation, update tracker/cache, close the tab, and set state="submitted".
- MEDIUM (one uncertain or unsupported field): fill all safe fields, generate best-effort grounded answers from Liam's profile and resume evidence, leave the tab open at the cleanest review point, set state="manual" with blocker like "Review needed: <question>".
- HARD blocker after attempt (account creation, fresh login when not authenticated, SMS/authenticator-app 2FA, interactive CAPTCHA, Workday account/profile gate, non-routine legal signature/contract terms, AI-deterrent verification): leave the tab open at the exact blocker, set state="manual" with the exact blocker, and exit. Do not skip a queued row merely because it is Workday/manual; attempt as far as safely possible first.
- Posting closed/404/redirected to a different role: set state="archived".

Education dates are strict: University of Georgia, BS Computer Science, started
Aug 2021, graduated Dec 2024. Never enter any graduation year before 2024, and
never answer that Liam graduated before 2020. If a form asks whether Liam
graduated before 2020, answer No. If a rendered education answer differs,
correct it before final submit or mark manual if it cannot be corrected.

Then UPDATE /tmp/fa_script_run_state.json — find the items[] entry where key == "{key}" and set:
  state: submitted | manual | archived
  result: short factual note
  blocker: exact blocker text (when manual)
  confirmationEvidence: confirmation page text / email / portal status (when submitted)
  updatedAt: ISO 8601 timestamp (UTC)

Refresh the visualizer cache when submitted:
  python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

Tab rule:
- If submitted and confirmation evidence is captured, close that application tab before exiting.
- If not submitted, leave the most useful partially completed application tab open at the exact review/blocker point for Liam, then exit.

Do NOT commit or push. The orchestrator owns commits.

Exit when done.
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


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def next_queued(state: dict[str, Any]) -> dict[str, Any] | None:
    for item in state.get("items", []):
        if item.get("state") == "queued":
            return item
    return None


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "row"


def build_prompt(item: dict[str, Any]) -> str:
    return PROMPT_TEMPLATE.format(
        company=item.get("company") or "",
        role=item.get("role") or "",
        jobLink=item.get("jobLink") or "",
        resumePdf=item.get("resumePdf") or "",
        postingKey=item.get("postingKey") or "",
        source=item.get("source") or "",
        notes=item.get("notes") or item.get("manualReason") or "",
        key=item.get("key") or "",
    )


def mark_outcome_in_state(key: str, *, state_value: str, **fields: Any) -> None:
    state = load_state()
    for item in state.get("items", []):
        if item.get("key") == key:
            item["state"] = state_value
            item["updatedAt"] = now_iso()
            for k, v in fields.items():
                if v is not None:
                    item[k] = v
            break
    write_state(state)


def get_outcome(key: str) -> dict[str, Any] | None:
    state = load_state()
    for item in state.get("items", []):
        if item.get("key") == key:
            return item
    return None


def spawn_worker(
    prompt: str,
    output_file: Path,
    worker_agent: str,
    model: str,
    reasoning_effort: str,
    timeout_s: int,
    child_sandbox: str,
) -> tuple[int, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if worker_agent == "codex":
        cmd = [
            "codex", "exec",
            "--cd", str(ROOT),
            "--sandbox", child_sandbox,
            "-m", model,
            "-c", f'model_reasoning_effort="{reasoning_effort}"',
            "-o", str(output_file),
            prompt,
        ]
        stdin_data = None
    elif worker_agent == "claude":
        cmd = [
            "claude", "-p",
            "--permission-mode", "acceptEdits",
            "--add-dir", str(ROOT),
        ]
        if model:
            cmd.extend(["--model", model])
        stdin_data = prompt
    else:
        raise ValueError(f"unsupported worker_agent: {worker_agent}")
    try:
        result = subprocess.run(
            cmd,
            input=stdin_data,
            timeout=timeout_s,
            capture_output=True,
            text=True,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if worker_agent == "claude":
            output_file.write_text(output, encoding="utf-8")
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return -1, f"timeout after {timeout_s}s"


def commit_and_push(*, push: bool, message: str) -> bool:
    add = subprocess.run(
        ["git", "-C", str(ROOT), "add", TRACKER_PATH, CACHE_PATH],
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        print(f"  git add failed: {add.stderr.strip()}")
        return False
    diff = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if diff.returncode == 0:
        print("  Nothing staged for tracker/cache; skipping commit.")
        return False
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "commit", "-m", message],
        capture_output=True, text=True,
    )
    if commit.returncode != 0:
        print(f"  git commit failed: {commit.stderr.strip()}")
        return False
    print(f"  ✓ committed: {message}")
    if push:
        push_result = subprocess.run(
            ["git", "-C", str(ROOT), "push", "origin", "main"],
            capture_output=True, text=True,
        )
        if push_result.returncode != 0:
            print(f"  git push failed: {push_result.stderr.strip()}")
            return False
        print("  ✓ pushed origin/main")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-row worker orchestrator for finish-app-script")
    parser.add_argument(
        "--worker-agent",
        choices=("codex", "claude"),
        default="codex",
        help="Worker CLI to spawn for each one-application child (default: codex)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model for child worker (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        choices=("minimal", "low", "medium", "high", "xhigh"),
        help=f"Reasoning effort for each one-application child worker (default: {DEFAULT_REASONING_EFFORT})",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-row timeout in seconds")
    parser.add_argument(
        "--child-sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default=DEFAULT_CHILD_SANDBOX,
        help=f"Sandbox for each one-application child worker (default: {DEFAULT_CHILD_SANDBOX})",
    )
    parser.add_argument("--max-rows", type=int, default=0, help="Cap rows processed (0 = drain queue)")
    parser.add_argument("--no-commit", action="store_true", help="Skip auto-commit every 5 confirmed submissions")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push to origin/main")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without invoking a worker")
    args = parser.parse_args()

    state = load_state()
    queue_total = sum(1 for it in state.get("items", []) if it.get("state") == "queued")
    print(
        "finish-app-script per-application orchestrator | "
        f"queue: {queue_total} | worker_agent: {args.worker_agent} | model: {args.model} | "
        f"reasoning_effort: {args.reasoning_effort} | "
        f"timeout: {args.timeout}s | child_sandbox: {args.child_sandbox}"
    )
    if args.dry_run:
        print(f"(dry run — no {args.worker_agent} worker invocations)")

    processed = 0
    consecutive_manual = 0
    submitted_since_push = 0
    summary = {"submitted": [], "manual": [], "archived": [], "skipped": []}

    while True:
        if args.max_rows and processed >= args.max_rows:
            print(f"\nReached --max-rows {args.max_rows}, stopping.")
            break

        item = next_queued(load_state())
        if not item:
            print("\nQueue drained.")
            break

        key = item.get("key") or ""
        company = item.get("company") or "?"
        role = item.get("role") or "?"
        confidence = item.get("confidenceBand") or "?"
        action = item.get("action") or "?"
        url = item.get("jobLink") or ""
        print(f"\n[{processed + 1}] {company} | {role}")
        print(f"  key={key}  confidence={confidence}  action={action}")
        print(f"  url={url}")

        if args.dry_run:
            print(f"  (would spawn {args.worker_agent} worker; skipping)")
            mark_outcome_in_state(key, state_value="skipped", result="dry-run")
            summary["skipped"].append(f"{company} | {role}")
            processed += 1
            continue

        prompt = build_prompt(item)
        out_file = OUTPUT_DIR / f"{safe_filename(key)}.txt"
        started_at = time.time()
        rc, _err = spawn_worker(
            prompt,
            out_file,
            args.worker_agent,
            args.model,
            args.reasoning_effort,
            args.timeout,
            args.child_sandbox,
        )
        elapsed = time.time() - started_at
        processed += 1

        if rc == -1:
            print(f"  ✗ timeout after {args.timeout}s — marking manual")
            mark_outcome_in_state(
                key,
                state_value="manual",
                blocker=f"Exec timeout {args.timeout}s",
                result="orchestrator timeout",
            )
            summary["manual"].append(f"{company} | exec timeout")
            consecutive_manual += 1
        elif rc != 0:
            print(f"  ✗ {args.worker_agent} worker exited rc={rc} after {elapsed:.0f}s — marking manual")
            mark_outcome_in_state(
                key,
                state_value="manual",
                blocker=f"{args.worker_agent} worker rc={rc}",
                result="orchestrator non-zero exit",
            )
            summary["manual"].append(f"{company} | {args.worker_agent} worker rc={rc}")
            consecutive_manual += 1
        else:
            outcome = get_outcome(key) or {}
            outcome_state = outcome.get("state")
            if outcome_state not in DONE_STATES:
                print(f"  ✗ agent exited without writing outcome (still 'queued') — marking manual")
                mark_outcome_in_state(
                    key,
                    state_value="manual",
                    blocker="Agent exited without writing outcome",
                    result="no state writeback",
                )
                summary["manual"].append(f"{company} | no state writeback")
                consecutive_manual += 1
            elif outcome_state == "submitted":
                print(f"  ✓ submitted in {elapsed:.0f}s")
                summary["submitted"].append(f"{company} | {role}")
                submitted_since_push += 1
                consecutive_manual = 0
            elif outcome_state == "manual":
                blocker = outcome.get("blocker") or outcome.get("result") or "no blocker recorded"
                print(f"  → manual ({elapsed:.0f}s): {blocker}")
                summary["manual"].append(f"{company} | {blocker}")
                consecutive_manual += 1
            elif outcome_state == "archived":
                reason = outcome.get("result") or "archived"
                print(f"  ≡ archived ({elapsed:.0f}s): {reason}")
                summary["archived"].append(f"{company} | {reason}")
                consecutive_manual = 0
            else:
                print(f"  ? state={outcome_state} ({elapsed:.0f}s)")
                summary["skipped"].append(f"{company} | state={outcome_state}")

        if consecutive_manual >= CIRCUIT_BREAKER_THRESHOLD:
            print(f"\n⚠ Circuit breaker tripped: {consecutive_manual} consecutive manual outcomes. Stopping.")
            break

        if not args.no_commit and submitted_since_push >= COMMIT_EVERY:
            today = dt.date.today().isoformat()
            print(f"\n→ {submitted_since_push} confirmed submissions since last push, committing...")
            commit_and_push(
                push=not args.no_push,
                message=f"Apply: {submitted_since_push} confirmed submissions {today}",
            )
            submitted_since_push = 0

    if not args.no_commit and submitted_since_push > 0:
        today = dt.date.today().isoformat()
        print(f"\n→ Final commit: {submitted_since_push} pending submissions")
        commit_and_push(
            push=not args.no_push,
            message=f"Apply: {submitted_since_push} confirmed submissions {today}",
        )

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Submitted: {len(summary['submitted'])}")
    for s in summary["submitted"]:
        print(f"  • {s}")
    print(f"Manual: {len(summary['manual'])}")
    for m in summary["manual"]:
        print(f"  • {m}")
    print(f"Archived: {len(summary['archived'])}")
    for a in summary["archived"]:
        print(f"  • {a}")
    if summary["skipped"]:
        print(f"Skipped: {len(summary['skipped'])}")
        for sk in summary["skipped"]:
            print(f"  • {sk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
