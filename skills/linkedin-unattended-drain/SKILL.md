---
name: linkedin-unattended-drain
description: Leave-the-PC LinkedIn early-career drain — one supervised 60-second kickoff (Chrome check + one request_directory approval + watchdog start), then Claude (Fable 5 / Opus-class) drains discover → tailor → apply fully hands-off until saturation or caps. Never pauses for human gates — every manual blocker is parked to the handoff file and the run continues. A background watchdog keeps the Mac awake, guards RAM, reconciles the tracker/SQLite/visualizer deterministically, and sends macOS notifications on completion or systemic failure. Use when Liam says `$linkedin-unattended-drain`, "apply while I'm gone", "run it and I'll leave my PC", or wants the weekly drain to survive manual blockers without stopping.
---

# LinkedIn Unattended Drain

Same pipeline as `linkedin-early-career-weekly-claude-only` (discover → tailor →
apply, one stage at a time, durable state, tracker reconcile) but engineered for
**zero humans after kickoff**:

- **Park, never pause.** Anything that would normally wait for Liam — blocking
  form question, required cover letter, FRQ, lost upload grant on one item —
  becomes a `manual` item + a handoff entry, and the loop moves to the next job.
- **One supervised minute, then autonomy.** Liam approves exactly one
  `request_directory` grant at kickoff; that covers every resume upload for the
  whole session. This is the autonomy ceiling — a fully headless session can
  never upload (the grant lives outside the permission system), so do not
  pretend otherwise.
- **A watchdog owns the machine.** `scripts/watchdog.sh` runs in the background:
  caffeinate, RAM guard, staleness detection, deterministic tracker/SQLite/
  visualizer reconcile, completion digest, macOS notifications. Checkpointing is
  not left to model memory.

## Stack Decision (fixed)

Claude Code only. The conductor is this session (Fable 5 / Opus-class); browser
stages run **inline on the main thread** (the upload grant and browser bridge do
not reliably reach subagents); `tailor` runs as a fresh Claude subagent. No
Codex anywhere: `codex exec` workers cannot reach the Codex Chrome extension,
and interactive Codex prompts per-origin for uploads — both need a human, which
defeats this skill's purpose.

## Canonical Repo & Absolute Paths

Everything this skill touches on disk lives under
`/Users/liamvan/Documents/Repos/CodexSkills` (the `~/.claude/skills` copy is a
mirror that only exists so the skill triggers from any session). Every repo
path in this skill and its operating card is **absolute** on purpose: the
skill is routinely invoked from sessions rooted in other projects, where
relative `skills/...` paths resolve nowhere and out-of-root file access is
gated by directory grants that bypass-permissions does NOT cover. Do not
"normalize" these paths back to relative, and do not go looking for these
directories inside the current project.

## Operating Card

Read
`/Users/liamvan/Documents/Repos/CodexSkills/skills/linkedin-unattended-drain/OPERATING_CARD.md`
before every stage. It inherits the claude-only card by reference and lists
only the overrides (isolated paths, park-don't-pause, failure streaks, RAM
budget).

## Isolated Durable State

```text
/tmp/linkedin_unattended_drain_state.json          # run state / cursor / items
/tmp/linkedin_unattended_drain_worker.lock         # single-actor lock
/tmp/linkedin_unattended_drain_outputs/            # worker result notes
/tmp/linkedin_unattended_drain_descriptions/       # captured job descriptions
/tmp/linkedin_unattended_drain_ram_warning         # flag file written by watchdog
/tmp/linkedin_unattended_drain_watchdog.log        # watchdog log + digest
```

Never read or write the state/lock files of the other `linkedin-early-career-*`
variants or `/tmp/fa_script_run_state.json`. If another variant's lock is held
by a live process, stop at kickoff and report — one drain per machine.

## Persistence Goal (shared with the `linkedin-early-career-weekly` variants)

State this goal at kickoff and keep it active for the whole drain. Keep the
completion-condition text byte-identical across variants:

> Every fresh last-week LinkedIn Entry-level software-engineer posting from the
> configured search is discovered, deduped against the tracker, and driven to a
> terminal state — submitted with confirmation evidence, recorded as a precise
> manual blocker, marked already-applied/duplicate, or archived with a reason —
> until search saturation (`search.stopRequested` with a `saturationReason`) or
> `runPolicy.maxJobs`, with the markdown tracker and visualizer cache
> reconciled. Submit high-confidence applications when the tailored resume is
> verified, all required answers are truthful/standing-answer covered, and no
> true blocker remains. Stop early only on a systemic browser/auth/rate-limit
> blocker or an explicit user stop. Honor the one-worker / one-browser-actor
> rule; never spawn extra workers just to satisfy the goal.

For hard session persistence Liam runs
`/goal Drain LinkedIn unattended per the linkedin-unattended-drain Persistence Goal`
once at kickoff.

## Kickoff — the one supervised minute

Run these in order while Liam is still at the keyboard. If any step fails,
fix it now; do not start an unattended run on a broken preflight.

1. **Single-drain check.** Verify no other variant's lock/state is live
   (`/tmp/linkedin_early_career_weekly*_worker.lock`,
   `/tmp/fa_script_run_state.json`). Kill orphan automation Chrome
   (`~/.codex/nodriver-chrome-ben`) — it wastes RAM and competes for the
   browser.
2. **Chrome + auth.** `open -na "Google Chrome" --args
   --profile-directory="Default"` (Liam profile, `liamvanpj@gmail.com`). Create
   one agent-owned tab via Claude-in-Chrome and load
   `https://www.linkedin.com/feed/` to prove both the bridge and the LinkedIn
   login. Logged out / 2FA / CAPTCHA here = fix before leaving, not after.
3. **The one approval.** Call `mcp__ccd_directory__request_directory` for the
   **repo root** `/Users/liamvan/Documents/Repos/CodexSkills` on the **main
   thread**. Liam approves once. This single grant covers everything the run
   touches outside the session root: the helper scripts under `skills/`, the
   trackers, `generic-resume/`, and every `companies/...` resume upload.
   Request the root even when the session is already rooted in CodexSkills —
   the browser upload path needs the explicit grant either way. Never request
   a narrower path (e.g. `companies/` alone) and never request additional
   directories mid-run: a partial grant is exactly what causes repeated
   directory prompts after Liam has left. Record an `uploadGrant: granted`
   event. If it is denied/unavailable, tell Liam plainly: this run can only
   prep the queue (discover + tailor); every apply will park as `manual`.
4. **Build state** (reuses the agent-neutral builder; `runPolicy.workerAgent`
   it writes is informational only):

   ```bash
   python3 /Users/liamvan/Documents/Repos/CodexSkills/skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

   python3 /Users/liamvan/Documents/Repos/CodexSkills/skills/linkedin-early-career-weekly/scripts/build_run_state.py \
     --state /tmp/linkedin_unattended_drain_state.json \
     --lock-file /tmp/linkedin_unattended_drain_worker.lock \
     --output-dir /tmp/linkedin_unattended_drain_outputs \
     --description-dir /tmp/linkedin_unattended_drain_descriptions \
     --max-jobs 20
   ```

   `--max-jobs 20` is the unattended default (a bounded run you can review
   beats an unbounded one you can't). Add `--resume` to continue an
   interrupted run; pass `--search-url URL` for a specific search.
5. **Start the watchdog** (background; it caffeinates the Mac for its own
   lifetime):

   ```bash
   bash /Users/liamvan/Documents/Repos/CodexSkills/skills/linkedin-unattended-drain/scripts/watchdog.sh &
   ```

   Always launch the CodexSkills copy by absolute path — the `~/.claude/skills`
   mirror resolves its repo root to `~/.claude` and the reconcile step breaks.

   Confirm `/tmp/linkedin_unattended_drain_watchdog.log` shows a startup line.
6. **Tell Liam to leave.** Summarize: grant status, max jobs, search URL,
   watchdog PID. Everything after this point is autonomous.

## The Loop

Each iteration: select → execute one stage → checkpoint → continue. Exactly one
browser actor at a time; hold the worker lock for the life of each stage.

1. **Select** from `/tmp/linkedin_unattended_drain_state.json`, same priority
   as the base runner: `apply_needed` → `tailor_needed` → discover next. Stop
   selecting when `search.stopRequested`, `runPolicy.maxJobs` terminal items
   reached, or a systemic blocker is recorded.
2. **Execute.**
   - `discover` / `apply`: **inline on the main thread** with Claude-in-Chrome
     (Computer Use fallback only). Take the lock, create a fresh agent-owned
     tab, do the stage, write the outcome atomically to state, release the
     lock, **close the work tab**.
   - `tailor`: fresh Claude subagent (Agent tool, `general-purpose`) — no
     browser dependency, keeps the main context lean. The prompt names the one
     item, the isolated state path, and requires reading this skill's
     operating card plus
     `/Users/liamvan/Documents/Repos/CodexSkills/skills/linkedin-easy-apply-nodriver/references/application-defaults.md`.
3. **Checkpoint (lightweight, every stage).** Re-read the changed item +
   search cursor. Park anything human-shaped (see operating card O1). Check
   the RAM flag file (O4). Every 5 terminal items, run the full audit:
   dedupe sweep vs `applications.md` / `job-intake.md` / `state.items`,
   confirmation-evidence check on new `submitted` rows, resume-matches-posting
   check.
4. **Continue.** A `manual` item is never a stop signal. Stop only on the
   systemic conditions in O2, on caps, or on saturation.

## End Of Run

Write `search.stopRequested` + `saturationReason` (or note the cap) to state.
The watchdog detects the terminal state, runs the final reconcile
(`scripts/mirror_to_sqlite.py` + visualizer refresh), appends a digest to its
log, and fires a macOS notification. Your final summary (also append it to the
watchdog log so it survives the session): submitted with evidence, manual rows
with exact blockers, duplicates, archived, integrity flags, and the exact
resume-from-here command. **No commits or pushes** in this workflow unless Liam
explicitly asked at kickoff — the repo often carries unrelated dirty files.

## Degraded Headless Mode (optional, prep-only)

A scheduled, fully unsupervised run can never submit (no grant), but it can
keep the queue warm. If Liam wants it, a launchd job can run:

```bash
claude -p 'Run $linkedin-unattended-drain in degraded prep mode: discover and
tailor only, park every apply as manual with an upload-grant blocker, resume
from /tmp/linkedin_unattended_drain_state.json with --resume.' \
  --permission-mode acceptEdits
```

Be honest in the digest that such a run produced zero submissions by design.
