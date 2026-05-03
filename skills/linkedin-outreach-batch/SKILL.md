---
name: linkedin-outreach-batch
description: Thin compatibility entrypoint for preparing approved LinkedIn outreach batches through the generalized linkedin-outreach lane workflow.
---

# LinkedIn Outreach Batch

This skill is deprecated as a standalone workflow. Use `linkedin-outreach` for the lane-agnostic process; this wrapper remains because existing visualizer commands, automations, and batch markdown files still reference the batch entrypoint.

For any lane, build the outreach queue with:

```bash
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type <lane> --limit <N>
```

For the legacy batch markdown manifests, the compatibility script still works:

```bash
python3 skills/linkedin-outreach-batch/scripts/build_recruiter_batch.py --contact-type recruiter
python3 skills/linkedin-outreach-batch/scripts/build_recruiter_batch.py --contact-type engineer
```

Before sending, re-read `skills/linkedin-outreach/OPERATING_CARD.md`. It is the source of truth for approval gates, send behavior, and outcome recording.
