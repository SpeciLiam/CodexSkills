#!/usr/bin/env python3
"""Run fresh Claude or Codex workers through the LinkedIn apply-all queue."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/linkedin_apply_all_state.json")
OUTPUT_DIR = Path("/tmp/linkedin_apply_all_worker_outputs")
DONE_STATES = {
    "submitted",
    "applied",
    "manual",
    "manual_apply_needed",
    "archived",
    "skipped",
    "duplicate",
    "queued_for_tailoring",
}
SYSTEMIC_BLOCKER_TERMS = (
    "chrome computer use unavailable",
    "computer use access denied",
    "appnotfound(\"google chrome\")",
    "linkedin login unavailable",
    "linkedin rate limit",
    "account restricted",
)


WORKER_PROMPT = """\
Read skills/linkedin-apply-all/OPERATING_CARD.md before starting. Follow it strictly.

You are a fresh {worker} worker launched by the LinkedIn apply-all queue runner.
Use the authenticated Liam Chrome profile for live LinkedIn/application work.
Do not spawn subagents. Process up to {batch_size} LinkedIn application outcome(s),
then exit cleanly.

Durable state file: {state_path}

Before starting and before each job, reread the state file. Respect:
- runPolicy.mode must be "linkedin-apply-all" applications-only.
- runPolicy.worker is "{worker}".
- runPolicy.missingResumePolicy controls what to do when a realistic new posting
  lacks a tailored resume. Default "queue_for_tailoring" means record the job
  and move on; do not run the full sourcing/recruiter pipeline.
- runPolicy.outreachAllowed=false means no recruiter search and no LinkedIn
  connection invites.
- search.url is the LinkedIn search to keep open. It already includes the chosen
  f_TPR freshness window.
- search.currentResultIndex and visitedJobUrls are durable cursor hints. Update
  them after each inspected card.
- Stop only if search.stopRequested, maxJobs is reached, the manual circuit
  breaker is hit, or a systemic LinkedIn/Chrome/auth/rate-limit blocker appears.

Per result, in order:
1. Open or return to search.url in Chrome. Inspect the next unvisited visible
   LinkedIn job card at/after search.currentResultIndex.
2. Capture title, company, location, LinkedIn URL/id, posted age, apply mode,
   and salary/applicant count if visible. Add the URL/id to visitedJobUrls and
   append/update a state item before application work.
3. Dedupe against application-trackers/applications.md, application-trackers/job-intake.md,
   and state items by Posting Key, LinkedIn job id, canonical URL, ATS URL, and
   normalized company + title. If already handled/completed, mark duplicate and
   continue if capacity remains.
4. Skip obvious bad fits: non-SWE, senior/staff/principal/manager, sales/support,
   internship-only, closed/stale, or outside Liam's cared-about locations.
5. If a valid tailored resume exists for this exact posting, apply with it. If
   not, follow runPolicy.missingResumePolicy exactly. In default apply-only mode,
   mark queued_for_tailoring with the captured job details and continue.
6. Attempt the application using finish-applications guardrails. Verify LinkedIn
   Easy Apply email is liamvanpj@gmail.com. Do not submit Workday applications.
   Do not solve CAPTCHA, create accounts, bypass bot checks, guess legal/salary
   commitments, or answer unsupported eligibility questions.
7. Record one durable item outcome with:
   key, company, role, jobUrl, linkedinJobId, location, source, applyMode,
   resumePdf, applicationConfidence, state, result, blocker,
   confirmationEvidence, updatedAt.
8. Update application-trackers/applications.md and generated visualizer cache
   only when source-of-truth status changed. Use existing status/outcome helpers
   when they are already part of the application workflow.
9. If no more usable jobs are visible/loadable, set search.stopRequested=true
   with search.saturationReason.

Exit after {batch_size} non-duplicate application outcome(s), after search
saturation, after the manual circuit breaker, or after a systemic blocker.
Do not commit or push.
"""


def now_tag() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        raise SystemExit(
            f"Missing run state at {STATE_PATH}. Run: "
            "python3 skills/linkedin-apply-all/scripts/build_run_state.py"
        )
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def done_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in DONE_STATES)


def submitted_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in {"submitted", "applied"})


def manual_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in {"manual", "manual_apply_needed"})


def stop_requested(state: dict[str, Any]) -> bool:
    return bool(state.get("search", {}).get("stopRequested"))


def hit_manual_circuit_breaker(state: dict[str, Any]) -> bool:
    limit = int(state.get("runPolicy", {}).get("manualCircuitBreaker") or 0)
    return bool(limit and manual_count(state) >= limit)


def has_systemic_blocker(state: dict[str, Any]) -> bool:
    for item in state.get("items", []):
        haystack = " ".join(str(item.get(field) or "") for field in ("blocker", "result")).lower()
        if any(term in haystack for term in SYSTEMIC_BLOCKER_TERMS):
            return True
    return False


def prompt(worker: str, batch_size: int) -> str:
    return WORKER_PROMPT.format(worker=worker, batch_size=batch_size, state_path=STATE_PATH)


def codex_cmd(prompt_text: str, output_file: Path, model: str | None, sandbox: str) -> list[str]:
    cmd = [
        "codex",
        "exec",
        "--ephemeral",
        "--cd",
        str(ROOT),
        "--sandbox",
        sandbox,
        "-o",
        str(output_file),
    ]
    if model:
        cmd.extend(["-m", model])
    cmd.append(prompt_text)
    return cmd


def claude_cmd(model: str | None, permission: str) -> list[str]:
    cmd = ["claude", "-p", "--permission-mode", permission, "--add-dir", str(ROOT)]
    if model:
        cmd.extend(["--model", model])
    return cmd


def run_worker(batch_no: int, worker: str, batch_size: int, args: argparse.Namespace) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{worker}_{batch_no:03d}_{now_tag()}.txt"
    prompt_text = prompt(worker, batch_size)
    if worker == "codex":
        cmd = codex_cmd(prompt_text, output_file, args.codex_model, args.child_sandbox)
        stdin_data = None
    else:
        cmd = claude_cmd(args.claude_model, args.claude_permission)
        stdin_data = prompt_text

    print(f"\nWorker {batch_no} ({worker}): output -> {output_file}")
    if args.dry_run:
        print("  dry run command:")
        print("  " + " ".join(cmd[:14]) + (" ..." if len(cmd) > 14 else ""))
        print(f"  prompt preview: {prompt_text.splitlines()[0]}")
        return 0

    if not shutil.which(worker):
        message = f"missing worker CLI: {worker}"
        print(message)
        output_file.write_text(message + "\n", encoding="utf-8")
        return 127

    try:
        result = subprocess.run(
            cmd,
            input=stdin_data,
            timeout=args.timeout,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
    except subprocess.TimeoutExpired as exc:
        output_file.write_text(f"timeout after {args.timeout}s\n{exc.stdout or ''}\n{exc.stderr or ''}", encoding="utf-8")
        return -1

    combined = (result.stdout or "") + (result.stderr or "")
    output_file.write_text(combined, encoding="utf-8")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LinkedIn apply-all queue workers.")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-workers", type=int, default=0)
    parser.add_argument("--worker", choices=("codex", "claude"), help="Override worker in state")
    parser.add_argument("--codex-model")
    parser.add_argument("--claude-model")
    parser.add_argument("--claude-permission", default="acceptEdits")
    parser.add_argument("--timeout", type=int, default=2700)
    parser.add_argument("--child-sandbox", default="danger-full-access", choices=("read-only", "workspace-write", "danger-full-access"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch_no = 0
    while True:
        state = load_state()
        worker = args.worker or state.get("runPolicy", {}).get("worker") or "codex"
        max_jobs = int(state.get("runPolicy", {}).get("maxJobs") or 0)
        before_done = done_count(state)
        if stop_requested(state):
            print("Search saturation/stop requested; no more workers.")
            return 0
        if max_jobs and before_done >= max_jobs:
            print(f"Reached max jobs: {before_done}/{max_jobs}")
            return 0
        if hit_manual_circuit_breaker(state):
            print("Manual blocker circuit breaker reached.")
            return 3
        if has_systemic_blocker(state):
            print("Systemic browser/LinkedIn blocker detected; stopping.")
            return 2
        if args.max_workers and batch_no >= args.max_workers:
            print("Stopped because --max-workers was reached.")
            return 0

        batch_no += 1
        rc = run_worker(batch_no, worker, args.batch_size, args)
        after = load_state()
        after_done = done_count(after)
        print(
            f"Progress: done {before_done} -> {after_done}; "
            f"submitted={submitted_count(after)}; manual={manual_count(after)}; worker={worker}"
        )
        if args.dry_run:
            return 0
        if stop_requested(after) or (max_jobs and after_done >= max_jobs):
            return rc
        if hit_manual_circuit_breaker(after):
            return rc or 3
        if has_systemic_blocker(after):
            return rc or 2
        if after_done <= before_done:
            return rc or 4


if __name__ == "__main__":
    raise SystemExit(main())
