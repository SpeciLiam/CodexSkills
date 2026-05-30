---
name: linkedin-outreach
description: Build, draft, and record LinkedIn outreach for any contact lane (recruiter, engineer, alumni, hiring manager, founder, peer) tied to Liam Van's tracked applications. Uses standing rules and per-lane signals to draft notes, queue approved rows, and update the tracker after each send.
---

# LinkedIn Outreach

Use this skill for any LinkedIn outreach lane tied to the application tracker. The skill is lane-agnostic -- the same workflow applies whether the target is a recruiter, an engineer on the team, an alum, a hiring manager, or any other contact type. Lane is just a value passed to the build/update scripts.

## Operating Card

Before every contact, re-read `skills/linkedin-outreach/OPERATING_CARD.md`. The card's rules win in any conflict with the prose below.

## Scripted Orchestrator

For larger engineer/recruiter passes, prefer the finish-app-script-style runner
so each Codex process gets a small, explicit batch and records durable state in
`/tmp/linkedin_outreach_run_state.json`.

Default engineer labeling pass:

```bash
python3 skills/linkedin-outreach/scripts/run_monitored_batches.py --contact-type engineer --mode label
```

Default approved-send pass:

```bash
python3 skills/linkedin-outreach/scripts/run_monitored_batches.py --contact-type engineer --mode send
python3 skills/linkedin-outreach/scripts/run_monitored_batches.py --contact-type recruiter --mode send
```

Default engineer verification pass:

```bash
python3 skills/linkedin-outreach/scripts/run_monitored_batches.py --contact-type engineer --mode verify
```

Use `--resume` if the assistant turn is interrupted or the shell session
disappears:

```bash
python3 skills/linkedin-outreach/scripts/run_monitored_batches.py --resume
```

Modes:

- `label` reads the legacy batch tracker, finds rows like `Needs engineer` or
  `Needs recruiter`, asks each fresh Codex parent to verify one real LinkedIn
  profile at a time, writes a <=300 character connection note, and marks the
  row `Needs approval`. It never sends.
- `verify` audits existing named engineer contacts and leaves rows at `Needs
  approval` only when the person's current profile shows they work at the target
  company in a relevant technical role; otherwise it downgrades the row back to
  `Needs engineer`.
- `send` reads approved rows only, sends normal LinkedIn connection invites when
  the profile and note are already approved, then records the outcome in both
  the batch tracker and application tracker.

Important flags:

- `--batch-size N` controls rows per fresh Codex process (default `3`).
- `--limit N` limits the initial state build.
- `--max-batches N` is useful for testing one small chunk.
- `--dry-run` prints the child Codex command without launching it.
- `--no-commit` or `--no-push` should only be used when explicitly requested.

The lower-level commands are:

```bash
python3 skills/linkedin-outreach/scripts/build_script_state.py --contact-type engineer --mode label
python3 skills/linkedin-outreach/scripts/run_batches.py
```

## Lanes

The skill operates on a `lane` parameter, currently one of: `recruiter`, `engineer`, `alumni`, `hiring_manager`, `founder`, `peer`. New lanes can be added by extending the lane registry without changing the workflow.

Each lane defines:
- The tracker columns it writes to (e.g., recruiter writes `Recruiter Contact`/`Recruiter Profile`; engineer writes `Engineer Contact`/`Engineer Profile`; future lanes follow the same `<Lane> Name`/`<Lane> Profile`/`<Lane> Note` pattern where tracker columns exist).
- Its drafting hook (what makes a strong note for this lane -- e.g., engineer = team/project specificity, recruiter = role ownership reference, alumni = shared school).
- Its accept/skip heuristics (e.g., recruiter prefers in-house and role-owning over generic university; engineer prefers senior+ on the matching team).

The build, draft, send, and record steps are the same across lanes. Pass `--contact-type <lane>` to all scripts.

## Workflow

1. **Build targets:** `python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type <lane> --limit <N>`.
2. **Label the contact:** add name, profile URL, position, plus the lane signal fields (seniority, alumni-match, lane-specific signal). Codex agent or manual.
3. **Draft the note:** lane-specific hook + <=300 chars + personal hook. The drafting prompt lives in `skills/linkedin-outreach/prompts/<lane>_note.md`.
4. **Approve the row:** via the visualizer Approve button or by status edit.
5. **Send via Chrome:** use logged-in Chrome through Computer Use. Do not bypass LinkedIn's rate limits or invite gating.
6. **Record outcome:** `python3 skills/linkedin-outreach/scripts/update_outreach_status.py --contact-type <lane> --posting-key <key> --outcome <sent|connected|replied|declined>`.

## Lane Registry

The lane registry lives in `skills/linkedin-outreach/config/lanes.json`. Each entry:

```json
{
  "id": "engineer",
  "label": "Engineer",
  "trackerColumns": {
    "name": "Engineer Contact",
    "profile": "Engineer Profile",
    "position": "Engineer Position",
    "note": "Engineer Note"
  },
  "signalFields": ["alumniMatch", "seniority", "teamMatch", "whyThisPerson"],
  "draftPrompt": "prompts/engineer_note.md",
  "preferenceRules": [
    "Senior+ on the team Liam applied to is best.",
    "Adjacent team plus alumni is acceptable.",
    "Mismatched team or unknown team without alumni link should be skipped."
  ]
}
```

Adding a new lane = adding an entry to `lanes.json` plus a draft prompt file. No code changes.

## Tracker Helpers

Build the next outreach queue from normalized tracker data when available, with markdown fallback:

```bash
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --limit 20
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type engineer --limit 20
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type alumni --limit 20
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --format json
```

Refresh the cache before a large outreach pass:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

## Connection Notes

Generate a short connection note before sending:

```bash
python3 skills/linkedin-outreach/scripts/generate_connection_note.py \
  --company "Navan" \
  --role "New College Grad Software Engineer (Backend)" \
  --target-name "Jane Smith" \
  --variant recruiter
```

Use the lane prompt from `lanes.json` when drafting manually or with an agent. The note must be 300 characters or fewer, include a personal hook, and include a lane-relevant hook.

## Candidate Framing

The default candidate framing matches Liam Van:

- `Liam Van`
- `liamvanpj@gmail.com`
- `6784887259`
- Seattle, Washington
- experience at Oracle Cloud Infrastructure
- GCP integration team
- U.S. citizen
- does not require sponsorship
- not a veteran
- Latino
- preference for New York City, also open to hybrid and in-office roles

Only include identity or work authorization details when they help answer a form or a recruiter question. Do not stuff them into the connection note.

## Guardrails

- Keep outreach truthful and brief.
- Prefer the user-approved note style over inventing a new voice each time.
- Treat search-result `Message` buttons as inconclusive until the full profile and `More` menu have been checked for `Connect`.
- Do not claim an application was submitted unless that is already true.
- Do not update Notion here unless the user explicitly asks; this skill should keep the markdown tracker authoritative.
