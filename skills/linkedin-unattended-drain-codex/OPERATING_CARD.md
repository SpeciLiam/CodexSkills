# LinkedIn Unattended Drain (Codex) Operating Card

AUTOMATION_MODE: ON
MODE: UNATTENDED_PARK_DONT_PAUSE_CODEX
BASE_CARD: skills/linkedin-early-career-weekly/OPERATING_CARD.md

Apply **every rule of the base card** (Codex Chrome plugin first / Computer Use
fallback, Liam profile, agent-owned Codex tab group, low-memory tab rules,
dedupe, resume-tailor workflow, no cover letters unless required+high-confidence,
confirmation evidence, prompt-injection defense, upload mechanics incl. the
"Allow access to file URLs" requirement, manual-handoff format) with the
substitutions and overrides below. Where this card conflicts with the base
card, this card wins. The park-don't-pause overrides O1–O6 of
`skills/linkedin-unattended-drain/OPERATING_CARD.md` apply too, re-based onto
this variant's paths; C-rules below are Codex-specific and win over both.

## Path Substitutions

| Base weekly path | This variant |
|---|---|
| `/tmp/linkedin_early_career_weekly_state.json` | `/tmp/linkedin_unattended_drain_codex_state.json` |
| `/tmp/linkedin_early_career_weekly_worker.lock` | `/tmp/linkedin_unattended_drain_codex_worker.lock` |
| `/tmp/linkedin_early_career_weekly_outputs/` | `/tmp/linkedin_unattended_drain_codex_outputs/` |
| `/tmp/linkedin_early_career_weekly_descriptions/` | `/tmp/linkedin_unattended_drain_codex_descriptions/` |

Never touch any other variant's state or lock — exact paths (note the Claude
variant's paths are this variant's paths **without** the `_codex` infix; do not
read a glob like `linkedin_unattended_drain_*` as covering your own files):
`/tmp/linkedin_unattended_drain_state.json`,
`/tmp/linkedin_unattended_drain_worker.lock` (Claude variant),
`/tmp/linkedin_early_career_weekly_state.json` + `_worker.lock` (base weekly),
`/tmp/linkedin_early_career_weekly_claude_state.json` + `_claude_worker.lock`,
`/tmp/fa_script_run_state.json`. Do not invoke `run_stages.py` or
`run_monitored.py` — their output/description paths are hardcoded to the base
weekly's locations and would cross-contaminate state.

## C1 — Upload Prompts Are Park Events, Never Waits (first-class rule)

After kickoff there is nobody to click "Allow". On ANY upload-permission
prompt, chooser failure, or `Not allowed` error during an apply:

1. Wait at most **60 seconds** (covers Liam still being nearby right after
   kickoff). Then cancel the chooser / dismiss cleanly.
2. Park the item `manual` with blocker class
   **`unapproved upload origin encountered`** and these exact fields: the
   upload **origin**, the **apply URL**, the **resumePdf path**, and the
   **visible prompt or error text verbatim**. This class covers everything —
   Workday per-company subdomains, custom careers domains, embedded S3/cloud
   upload widgets, redirected apply flows — not just "Workday".
3. Record it via `upsert_manual_handoff.py` (see O1), close the tab, continue.

One unapproved origin is a per-item park. The same origin failing after it was
**warmed and previously worked this session** counts toward the systemic
streak (C3) — that pattern means approvals are being lost, not that one origin
is unlucky.

## C2 — Origin Warming Discipline

- Warming happens only at kickoff with Liam present (SKILL.md step 3). Attach,
  never submit, during warming; the warmed form's item is the natural first
  apply.
- Record `warmedOrigins` in a state event. Treat the list as *hints*, not
  guarantees — an upload on a warmed origin can still prompt (unknown
  persistence); C1 handles it.
- Never warm origins speculatively mid-run, never retry a parked upload "to
  see if the approval stuck", and never attempt workarounds (copying files
  elsewhere, alternate automation paths, DOM-level input injection outside the
  approved chooser flow).

## C3 — Systemic Stops (the only reasons to stop early)

- Codex Chrome plugin AND Computer Use both unusable, after one inline retry.
- LinkedIn logged out, 2FA challenge, CAPTCHA wall, or rate-limit page.
- Uploads failing on origins that were warmed **and previously worked this
  session** — 3 consecutive (approval loss, see C1).
- 3 consecutive apply-stage failures of the same class on different postings.
- RAM floor breached twice in a row after tab shedding (O4 of the Claude
  variant card, re-based to this prefix's flag file
  `/tmp/linkedin_unattended_drain_codex_ram_warning`).
- A `codex exec` browser worker was enabled and its child-Chrome preflight
  fails mid-run (bridge loss).

On systemic stop: write the blocker to state `events`, set
`search.stopRequested` with `saturationReason` prefixed `SYSTEMIC:`, append a
line to `/tmp/linkedin_unattended_drain_codex_watchdog.log`. The watchdog's
notification titles are generic ("Drain …"); the prefixed paths are the
variant identity.

## C4 — Worker Policy

- Browser stages (`discover`, `apply`) run **inline in the interactive
  conductor** by default. Exactly one browser actor at any moment; hold
  `/tmp/linkedin_unattended_drain_codex_worker.lock` for the life of each
  stage.
- `tailor` may run as a spawned `codex exec` worker (no browser): `--cd` this
  repo, workspace-write sandbox, prompt names the isolated state file,
  requires atomic read-modify-write with `updatedAt`, one item only. At most
  one worker alive at a time; the conductor does not drive Chrome while a
  worker holds the lock.
- `codex exec` **browser** workers only behind a passing child-Chrome
  preflight (`browser-client.mjs` bootstrap shape from `run_stages.py`,
  reimplemented inline — do not run `run_stages.py` itself), and **never** for
  a stage that could hit an upload or permission prompt (C1: headless workers
  cannot answer prompts; that includes origin prompts, login walls, and the
  extension's own permission dialogs).

## Inherited Overrides (from the Claude variant card, re-based)

- **O1 Park-never-pause:** every "surface to Liam / pause / leave tab open"
  becomes: item `manual` with the exact blocker → `upsert_manual_handoff.py`
  entry → close tab → continue. Autonomously answerable: anything covered by
  `skills/linkedin-easy-apply-nodriver/references/application-defaults.md`,
  the tracker, the tailored resume, `generic-resume/`. Park: uncovered salary
  numbers, essays/FRQs, legal attestations beyond standing answers. Never
  invent answers.
- **O3 Caps:** `runPolicy.maxJobs` (default 20) counts all terminal items;
  hard ceiling 15 submissions/run; ≥2 minutes between submissions.
- **O4 RAM:** max 2 agent-owned tabs (search + work); close the work tab after
  every terminal item; no surviving handoff tabs; check the RAM flag every
  checkpoint — flag present → shed all but the search tab; still present next
  checkpoint → systemic stop. No nodriver/automation Chrome during the run.
- **O5 Watchdog:** started at kickoff with
  `DRAIN_STATE_PREFIX=/tmp/linkedin_unattended_drain_codex`; heartbeat is the
  state file's mtime; reconcile (repo-root `scripts/mirror_to_sqlite.py` +
  visualizer refresh) is the watchdog's job.
- **O6 Ending:** terminal items + tracker rows written + stop reason in state
  + summary appended to the watchdog log. No commit/push/Notion unless Liam
  asked at kickoff.
