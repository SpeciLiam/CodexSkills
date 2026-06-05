---
name: linkedin-early-career-weekly
description: Durable LinkedIn early-career weekly application drain with fresh workers for discovery, resume tailoring, and one application at a time.
---

# LinkedIn Early-Career Weekly

Run the new LinkedIn early-career weekly workflow. This command intentionally
does not use `skills/linkedin-apply-all`.

Before starting from chat, create a persistent pursuing goal for the drain if
the environment exposes goal tools. Keep it active while workers are running or
the state is resumable, and close it only on search saturation, systemic
blocker, or explicit user stop. The one-worker/browser-actor rule still wins.

Default live run:

```bash
python3 skills/linkedin-early-career-weekly/scripts/run_monitored.py
```

Resume after interruption:

```bash
python3 skills/linkedin-early-career-weekly/scripts/run_monitored.py --resume
```

Short dry run:

```bash
python3 skills/linkedin-early-career-weekly/scripts/run_monitored.py --dry-run --max-stages 1 --no-refresh
```

The monitor writes state to `/tmp/linkedin_early_career_weekly_state.json` and
worker transcripts to `/tmp/linkedin_early_career_weekly_outputs/`.

This workflow uses Liam's Chrome profile for both discovery and applications,
and only the Codex Chrome plugin or Codex Computer Use for browser work.
