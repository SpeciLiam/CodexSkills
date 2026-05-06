---
name: finish-app-script
description: Drain Liam's tailored-resume application queue from a phone-friendly command. Build `/tmp/fa_script_run_state.json`, then run the rotating batch orchestrator that launches fresh Codex CLI parent processes for small Chrome/Computer Use batches, closes submitted tabs, leaves low-confidence handoff tabs open, updates tracker/cache, and commits confirmed submissions. Use when the user says `$finish-app-script`, "run finish app script", "drain my application queue", or wants applications completed without context overflow.
---

# Finish-App-Script

A reliability-focused parallel of `finish-applications`. Same goal — submit ready tracker rows — but uses an outer orchestrator to rotate fresh Codex CLI parent processes through small batches.

## Default Invocation

When the user invokes `$finish-app-script` or asks to run this skill from chat,
do this without asking for extra confirmation:

```bash
python3 skills/finish-app-script/scripts/run_monitored_batches.py
```

Use `run_monitored_batches.py` by default for live browser work. It refreshes
the tracker cache, builds `/tmp/fa_script_run_state.json`, runs `run_batches.py`,
and restarts the batch runner if it stops while queued rows remain. Monitor its
terminal output while it runs. If the assistant turn is interrupted or the shell
session disappears, inspect `/tmp/fa_script_run_state.json`; when queued rows
remain and no `run_batches.py`/`codex exec` process is active, resume with:

```bash
python3 skills/finish-app-script/scripts/run_monitored_batches.py --resume
```

Do not pass `--no-commit` or `--no-push` unless the user explicitly asks.
`run_batches.py` owns commits and pushes, including final commits for confirmed
submissions. Use the legacy `run_queue.py` only if the user explicitly asks for
per-row mode.

## Tab Confidence Grouping

During live browser runs, keep open application tabs organized by perceived
handoff confidence:

- **High Confidence / Ready Submit**: fully completed tabs where every required
  answer is covered by standing answers, critical rendered answers are verified,
  and only final submission/confirmation remains.
- **Needs Review**: tabs with one or more medium-confidence answers, free
  response drafts, eligibility/location/salary uncertainty, or required choices
  that Liam should inspect.
- **Hard Blocker**: Workday, login/account creation, SMS/authenticator 2FA,
  CAPTCHA, legal signature/attestation, AI-deterrent verification, or other true
  blockers.
- **Submitted / Archived**: confirmation tabs, already-submitted portals, closed
  postings, mismatched redirects, and not-found pages.

If Chrome tab groups are available through UI automation, place tabs into those
groups. If tab groups are not scriptable from the current environment, use the
closest non-destructive fallback: reorder tabs into the same sequence and keep a
short written map in the run notes or final response.

## How To Run

```bash
# Refresh the tracker cache
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

# Build the queue (writes /tmp/fa_script_run_state.json)
python3 skills/finish-app-script/scripts/build_queue.py

# Preferred for live browser application work: rotate a fresh parent Codex CLI
# process through two applications at a time, restarting if the runner stops.
python3 skills/finish-app-script/scripts/run_monitored_batches.py

# Resume an existing run state without rebuilding the queue.
python3 skills/finish-app-script/scripts/run_monitored_batches.py --resume

# Lower-level batch runner used by the monitor.
python3 skills/finish-app-script/scripts/run_batches.py

# Legacy per-row mode: one child codex exec per application row.
python3 skills/finish-app-script/scripts/run_queue.py
```

`run_batches.py` flags:

- `--batch-size N` — rows per fresh Codex process (default `2`)
- `--max-batches N` — stop after N fresh Codex processes (testing)
- `--model MODEL` — override default `gpt-5.5`
- `--timeout SECONDS` — per-batch timeout (default 1800s = 30 min)
- `--child-sandbox MODE` — sandbox for each fresh Codex process (default `danger-full-access`)
- `--no-commit` — skip auto-commit every 5 confirmed submissions
- `--no-push` — commit but don't push
- `--dry-run` — print what would be spawned without invoking `codex exec`

`run_monitored_batches.py` flags:

- `--resume` — skip refresh/build and continue `/tmp/fa_script_run_state.json`
- `--max-restarts N` — retry stopped runs with queued rows remaining (default `3`)
- `--restart-sleep SECONDS` — wait before retrying (default `10`)
- all normal `run_batches.py` flags above are forwarded

`run_queue.py` flags:

- `--max-rows N` — stop after N rows (testing)
- `--model MODEL` — override default `gpt-5.5`
- `--timeout SECONDS` — per-row timeout (default 360s = 6 min)
- `--no-commit` — skip auto-commit every 5 confirmed submissions
- `--no-push` — commit but don't push
- `--dry-run` — print what would be spawned without invoking `codex exec`

## Architecture

### Rotating Parent Mode (`run_batches.py`)

```
run_batches.py (outer orchestrator)
  ├── reads /tmp/fa_script_run_state.json
  └── while queued rows remain:
        ├── previews the next N queued rows (default 2)
        ├── spawns a fresh parent Codex CLI process:
        │     codex exec --ephemeral --cd $REPO --sandbox danger-full-access
        │       -m gpt-5.5 -o /tmp/fa_script_batch_outputs/batch_NNN.txt "<prompt>"
        ├── that fresh parent owns Chrome/Computer Use directly
        ├── parent processes up to N rows, writes outcomes to state, exits
        ├── outer orchestrator re-reads state and summarizes progress
        └── commits + pushes every 5 confirmed submissions
```

This is the preferred live-browser mode. It keeps the context-reset benefit,
but avoids making every individual application a tiny GUI worker. Each fresh
Codex process behaves like a short `$finish-applications` run: it owns the
browser, processes one row at a time, and stops after a small batch.

### Legacy Per-Row Mode (`run_queue.py`)

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
| Context overflow | Rotating parent mode sees only a small batch before the CLI process exits |
| Computer Use flakiness | The browser is owned by a fresh parent process for a short batch, instead of a separate GUI worker per row |
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

Email 2FA / verification codes / magic links to liamvanpj@gmail.com are NOT
blockers. Use gmail@openai-curated MCP to read the code or click the link in
Chrome (already signed in), then continue. Only escalate if the email never
arrives, expires, or the verification switches to SMS / authenticator-app 2FA.

Confidence decision after final review:
- HIGH (every required field covered, no blocker): click submit, retrieve any
  emailed verification code via Gmail MCP, capture confirmation,
  run update_application_status.py, set state="submitted".
- MEDIUM (FRQ/one uncertain field): fill all safe fields, generate best-effort
  answer from profile, leave tab open, set state="manual" with
  blocker like "FRQ review: <question>".
- HARD blocker (account creation, fresh login when unauthenticated, SMS/
  authenticator-app 2FA, interactive CAPTCHA, Workday, legal signature):
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
