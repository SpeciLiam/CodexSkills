---
name: linkedin-unattended-drain-codex
description: Codex-driven leave-the-PC LinkedIn early-career drain — an interactive Codex (GPT 5.5) session is the conductor AND the browser actor (Codex Chrome plugin first, Computer Use fallback), with best-effort upload-origin warming at a supervised kickoff, park-don't-pause on every manual blocker, isolated /tmp state, and the shared path-parameterized watchdog for caffeinate/RAM/stall/reconcile/notifications. Use when Liam says `$linkedin-unattended-drain-codex`, wants the unattended drain run by Codex instead of Claude, or wants to compare the Codex upload path (absolute local paths, per-origin approvals) against the Claude variant's one-grant model.
---

# LinkedIn Unattended Drain — Codex Variant

Same leave-the-PC contract as `linkedin-unattended-drain` (one supervised
kickoff → autonomous discover → tailor → apply, park-don't-pause, watchdog,
caps) but the conductor/executor is an **interactive Codex session** and the
browser stack is the **Codex Chrome plugin**.

## Why this variant exists (the upload tradeoff, stated honestly)

- **Claude variant:** uploads need one `request_directory` grant at kickoff;
  after that, *every* upload on *any* origin works for the session. Ceiling:
  the grant only exists in a supervised session.
- **Codex variant (this):** `chooser.setFiles(...)` uploads absolute local
  paths with no share registry, but Codex asks **per-origin**: "Allow upload to
  `<origin>`?". Kickoff warms the origins this run will hit most; any origin
  that wasn't warmed parks as `manual` when its prompt appears with nobody
  home.

Net: Claude's ceiling is one grant covering everything; Codex's ceiling is
per-origin approvals that cover the *common* ATS hosts (Greenhouse / Ashby /
Lever / LinkedIn Easy Apply) and park the long tail. Neither submits from a
fully headless run. Pick this variant when most of the queue lives on shared
ATS origins, or to A/B against the Claude variant.

### Upload-approval semantics — knowns and unknowns

| Surface | Behavior | Status |
|---|---|---|
| Interactive conductor tab, warmed origin | upload proceeds | expected |
| Interactive conductor tab, new origin | "Allow upload to `<origin>`?" prompt | verified (base card 9e note) |
| Approval persistence across tabs, same origin, same session | assumed yes | **UNVERIFIED** |
| Approval persistence across Codex sessions / extension restart | unknown | **UNVERIFIED** |
| Spawned `codex exec` worker hitting an upload prompt | cannot be approved headless | treat as park |

Treat every UNVERIFIED row pessimistically: if an upload prompt appears mid-run
and is not answered within the bounded wait, the item parks (operating card
C1). The first real run upgrades these rows from assumption to fact — record
what you observe in the run summary.

## Operating Card

Read `skills/linkedin-unattended-drain-codex/OPERATING_CARD.md` before every
stage. It layers on the Codex base card
(`skills/linkedin-early-career-weekly/OPERATING_CARD.md`) and the Claude
variant's park-don't-pause rules.

## Isolated Durable State

```text
/tmp/linkedin_unattended_drain_codex_state.json          # run state / cursor / items
/tmp/linkedin_unattended_drain_codex_worker.lock         # single-actor lock
/tmp/linkedin_unattended_drain_codex_outputs/            # worker result notes
/tmp/linkedin_unattended_drain_codex_descriptions/       # captured job descriptions
/tmp/linkedin_unattended_drain_codex_ram_warning         # flag file from watchdog
/tmp/linkedin_unattended_drain_codex_watchdog.log        # watchdog log + digest
```

Do **not** use `run_stages.py` in this variant — its output/description paths
are hardcoded to the base weekly's `/tmp` locations and would collide. The
conductor drives stages itself; only `build_run_state.py` (fully
path-parameterized) is reused.

## Persistence Goal (shared with the `linkedin-early-career-weekly` variants)

State this goal at kickoff and keep it active for the whole drain. The
blockquote below is the shared completion condition — keep it byte-identical
across variants:

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

## Kickoff — the supervised minutes

Run in order while Liam is at the keyboard. A failed preflight is fixed now or
the run does not start.

1. **Single-drain preflight.** Verify none of these belong to a live process
   (check any recorded pid with `kill -0`):
   `/tmp/linkedin_unattended_drain_codex_worker.lock`,
   `/tmp/linkedin_unattended_drain_worker.lock` (Claude variant),
   `/tmp/linkedin_early_career_weekly_worker.lock`,
   `/tmp/linkedin_early_career_weekly_claude_worker.lock`,
   `/tmp/fa_script_run_state.json`. One drain per machine — a live lock from
   any variant stops this kickoff. Kill orphan automation Chrome
   (`~/.codex/nodriver-chrome-ben`).
2. **Chrome + extension.** Open Chrome on Liam's profile (`Default`,
   `liamvanpj@gmail.com`). Confirm the Codex Chrome extension is connected and
   **"Allow access to file URLs" is enabled** in `chrome://extensions` (base
   card 10d — without it every upload fails as `Not allowed`). Create an
   agent-owned Codex tab group; load `https://www.linkedin.com/feed/` to prove
   login. Logged out / 2FA / CAPTCHA = fix before leaving.
3. **Build state** (before warming — the warming event needs somewhere durable
   to go):

   ```bash
   python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py

   python3 skills/linkedin-early-career-weekly/scripts/build_run_state.py \
     --state /tmp/linkedin_unattended_drain_codex_state.json \
     --lock-file /tmp/linkedin_unattended_drain_codex_worker.lock \
     --output-dir /tmp/linkedin_unattended_drain_codex_outputs \
     --description-dir /tmp/linkedin_unattended_drain_codex_descriptions \
     --child-sandbox workspace-write \
     --max-jobs 20
   ```

   Add `--resume` to continue an interrupted run; `--search-url URL` for a
   specific search. (`--child-sandbox workspace-write` matches the tailor
   worker policy in the operating card — do not leave the default
   `danger-full-access` in state.)
4. **Origin warming (best-effort, not a contract).** With Liam present, for
   each shared ATS origin expected in this run — `boards.greenhouse.io`,
   `jobs.ashbyhq.com`, `jobs.lever.co`, `www.linkedin.com` — open one real
   application form and attach (do **not** submit) a resume via
   `chooser.setFiles`, letting Liam answer each "Allow upload to `<origin>`?"
   prompt once. Form sources, in order: items already in state when resuming,
   then pending rows in `application-trackers/job-intake.md`; if neither has a
   form on a given origin, skip it and note the reduced hands-off share. Record
   warmed origins in a state event (`warmedOrigins: [...]`) — the state file
   exists now. This is opportunistic: it raises the share of hands-off applies;
   it does not guarantee any later upload (see unknowns table).
5. **Start the shared watchdog** (path-parameterized; no copy):

   ```bash
   DRAIN_STATE_PREFIX=/tmp/linkedin_unattended_drain_codex \
     bash skills/linkedin-unattended-drain/scripts/watchdog.sh &
   ```

   Confirm a startup line in
   `/tmp/linkedin_unattended_drain_codex_watchdog.log`. Note: watchdog
   notifications are titled generically ("Drain …"); variant identity comes
   from the prefixed log/state paths, not the notification text.
6. **Tell Liam to leave.** Summarize: warmed origins, file-URL setting, max
   jobs, search URL, watchdog PID. Everything after this is autonomous.

## The Loop

One stage per iteration, exactly one browser actor, lock held for the life of
each stage.

1. **Select** from state: `apply_needed` → `tailor_needed` → discover next.
   Stop selecting on `search.stopRequested`, cap reached, or systemic blocker.
2. **Execute.**
   - `discover` / `apply`: **inline in this interactive conductor** with the
     Codex Chrome plugin (Computer Use fallback only). Fresh agent-owned tab,
     do the stage, write the outcome atomically to the isolated state, close
     the work tab.
   - `tailor`: may run as a spawned `codex exec` worker (no browser
     dependency, `--cd` this repo, workspace-write sandbox) or inline —
     whichever keeps the conductor responsive. Worker prompt must name the
     isolated state path and require atomic writeback.
   - `codex exec` **browser** workers are off by default. Only enable after a
     passing child-Chrome preflight (the `browser-client.mjs` bootstrap shape
     from `run_stages.py`), and never for stages that may hit an upload or
     permission prompt — a headless worker cannot answer one (card C1).
3. **Checkpoint (every stage).** Re-read the changed item + cursor. Park
   anything human-shaped (card C1/O1). Check the RAM flag
   (`/tmp/linkedin_unattended_drain_codex_ram_warning`). Every 5 terminal
   items: full dedupe + evidence audit.
4. **Continue.** `manual` is never a stop signal.

## End Of Run

Write `search.stopRequested` + `saturationReason` (or note the cap). The
watchdog runs the final reconcile (repo-root `scripts/mirror_to_sqlite.py` +
visualizer refresh), appends a digest, and notifies. Final summary must
include: submissions with evidence, manual rows with exact blockers
(including every unapproved-upload-origin park with the origin named), warmed
origins that worked vs didn't (upgrade the unknowns table), duplicates,
archived, integrity flags, and the exact resume command. **No commits, no
pushes, no Notion** unless Liam explicitly asked at kickoff.

## Degraded Headless Mode (optional, prep-only)

A fully headless `codex exec` run cannot answer any upload or permission
prompt, so it can only prep: discover + tailor, park every apply as `manual`
with an upload blocker. Be explicit in the digest that such a run produced
zero submissions by design.
