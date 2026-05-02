---
name: application-visualizer-refresh
description: Refresh the Vercel-ready application tracker visualization website by parsing application-trackers/applications.md and outreach-prospects.md into application-visualizer/src/data/tracker-data.json.
---

# Application Visualizer Refresh

Use this skill when the user wants to refresh, rebuild, or update the application tracker visualization website data.

For full recruiting sessions, start with `recruiting-pipeline`; it uses this skill at the beginning for read-model freshness and at the end after tracker changes.

## Source Files

- Application tracker: `application-trackers/applications.md`
- Outreach tracker: `application-trackers/outreach-prospects.md`
- Job intake tracker: `application-trackers/job-intake.md`
- Website data output: `application-visualizer/src/data/tracker-data.json`

## Default Command

Run this from the CodexSkills repo root:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

That command parses both markdown trackers, normalizes markdown links, computes statistics, and writes the JSON consumed by the React site.

## Website Commands

From `application-visualizer`:

```bash
npm run refresh
npm run build
```

`npm run build` already runs the refresh script before compiling, so Vercel builds pick up the latest committed markdown data.

## Guardrails

- Treat the markdown trackers as the source of truth.
- Do not edit application rows while refreshing visualizer data.
- If parsing fails, fix the parser or malformed markdown instead of hand-editing generated JSON.
- Keep generated JSON committed when deploying the static Vercel site.
