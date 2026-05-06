---
name: finish-app-script
description: Per-row orchestrator for completing tracked job applications. Spawns one fresh `codex exec` per ready row so each agent gets a clean context, no accumulated browser history, and the submission rule embedded directly in its prompt. Use when the user wants to drain the application queue without context overflow, single-agent drift, or one-row-at-a-time stalls.
---

# Finish-App-Script

A reliability-focused parallel of `finish-applications`. Same goal — submit ready tracker rows — but uses an orchestrator that spawns one fresh `codex exec` per row instead of a single long-running agent.

## How To Run

```bash
# Build the queue (writes /tmp/fa_script_run_state.json)
python3 skills/finish-app-script/scripts/build_queue.py

# Drain it
python3 skills/finish-app-script/scripts/run_queue.py
```

`run_queue.py` flags:

- `--max-rows N` — stop after N rows (testing)
- `--model MODEL` — override default `gpt-5.5`
- `--timeout SECONDS` — per-row timeout (default 360s = 6 min)
- `--no-commit` — skip auto-commit every 5 confirmed submissions
- `--no-push` — commit but don't push
- `--dry-run` — print what would be spawned without invoking `codex exec`

## Architecture

```
run_queue.py (orchestrator)
  ├── reads /tmp/fa_script_run_state.json
  └── for each queued row:
        ├── builds tight per-row prompt (~250 tokens)
        ├── spawns: codex exec --cd $REPO --sandbox workspace-write
        │           -m gpt-5.5 -o /tmp/fa_script_outputs/<key>.txt "<prompt>"
        ├── waits up to 6 min
        ├── re-reads state file → checks outcome (submitted|manual|archived)
        ├── increments counters, runs circuit breaker
        └── commits + pushes every 5 confirmed
```

Each spawned agent is a fresh process with no context history. It reads `OPERATING_CARD.md`, applies to one job, writes outcome to the state file, exits.

## Why This Architecture

| Pain point | Why this fixes it |
|---|---|
| Context overflow | Each agent only sees one application; context can never fill |
| Computer Use flakiness | Fresh browser state per agent; one failure doesn't cascade |
| FRQ blocking the queue | Fill-and-leave-open enforced per row; orchestrator continues |
| Single-agent drift | The submission rule lives in the prompt itself, can't degrade |

## Bug Fixes vs `finish-applications`

`build_queue.py` corrects three behaviors in the original `build_application_queue.py`:

1. **`"not automation-accessible"` is retryable**, not a true blocker. Past notes from environment failures (denied Chrome automation permission) used to permanently lock those rows; they re-enter the queue now.
2. **Manual-Apply-Needed rows with no specific note are retryable.** Original `true_manual_reason()` returned a generic non-empty fallback that forced `action=manual`. Returns `""` here so they get `action=retry/apply`.
3. **FRQ terms reduce confidence, not block the row.** `"free response"`, `"free-response"`, `"custom"` moved out of `TRUE_MANUAL_BLOCKERS` into a new `CONFIDENCE_REDUCERS` list (`-20` score impact, pushes to medium band so the agent attempts with fill-and-leave-open).

## Per-Row Prompt Template

The orchestrator builds this for each spawned agent. Keep it tight; do not bloat with full SKILL contents — the agent reads `OPERATING_CARD.md` for rules.

```
Read skills/finish-app-script/OPERATING_CARD.md before starting. Follow it strictly.

You are completing ONE job application.

Company: {company}
Role: {role}
URL: {jobLink}
Resume PDF: {resumePdf}
Posting key: {postingKey}
Source: {source}
State item key: {key}
Notes carried from tracker: {notes}

Use Codex Computer Use for the browser. Dropdowns/typeaheads: open menu →
click option → verify chip rendered. Never just type and move on.

Confidence decision after final review:
- HIGH (every required field covered, no blocker): click submit, capture
  confirmation, run update_application_status.py, set state="submitted".
- MEDIUM (FRQ/one uncertain field): fill all safe fields, generate best-effort
  answer from profile, leave tab open, set state="manual" with
  blocker like "FRQ review: <question>".
- HARD blocker (login/2FA/CAPTCHA/Workday/account creation/legal signature):
  set state="manual" with exact blocker.
- Posting closed/404/redirected: set state="archived".

Update /tmp/fa_script_run_state.json item with key "{key}":
  state, result, blocker (if manual), confirmationEvidence (if submitted), updatedAt.

Exit when done.
```

## Run State File

`/tmp/fa_script_run_state.json` (separate namespace from the legacy skill's `/tmp/fa_run_state.json`). Schema mirrors the legacy file but `items[i].state` transitions are the only thing the orchestrator reads back.

## Liam's Standing Answers

Detailed in `OPERATING_CARD.md` rule 4. The condensed list is in the per-row prompt only as a reference — the agent re-reads the operating card on every run.

## Cover Letters

Generate only when required (not optional). From the spawned agent:

```bash
python3 skills/resume-tailor/scripts/create_cover_letter.py \
  --dir "<company resume folder>" --company "<Company>" --role "<Role>" \
  --why-interest "<2-3 sentences grounded in posting + Liam's projects>"

python3 skills/resume-tailor/scripts/render_cover_letter_pdf.py \
  --dir "<company resume folder>"
```

Upload `Liam_Van_<Company>_Cover_Letter.pdf`. Record in tracker note that a cover letter was submitted.

## Workday

Workday rows are flagged at queue-build time and never spawned — Liam submits manually. To mark them in the tracker:

```bash
python3 skills/finish-app-script/scripts/build_queue.py --mark-workday-manual
```

## Circuit Breaker

`run_queue.py` stops the run if 3 consecutive rows return `state=manual`. This catches Chrome auth loss, network problems, or systemic blocker patterns before burning more spawns. Resume by clearing the consecutive-manual streak (run with `--max-rows` to test) or fixing the underlying issue.

## Final Response

Orchestrator prints a summary: confirmed submissions, manual rows with blockers, archived rows, commits made. Tracker and visualizer cache reflect all confirmed submissions.
