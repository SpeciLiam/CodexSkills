---
name: notion-application-sync
description: Optionally mirror Liam Van's application tracker data into Notion from the generated visualizer JSON cache. Use only when the user explicitly asks to sync, audit, configure, or schedule Notion matching; normal recruiting skills should not call this by default.
---

# Notion Application Sync

Use this skill only for the optional Notion mirror. The recruiting source of truth remains:

1. `application-trackers/applications.md`
2. `application-visualizer/src/data/tracker-data.json`
3. Notion, as a slower external mirror

Do not run this inside normal resume tailoring, Gmail refresh, LinkedIn outreach, or company prospecting unless the user explicitly asks for Notion.

## Commands

Preview matches without changing Notion:

```bash
python3 skills/notion-application-sync/scripts/sync_applications_to_notion.py --dry-run
```

Sync from the generated website data cache:

```bash
NOTION_TOKEN=secret_... python3 skills/notion-application-sync/scripts/sync_applications_to_notion.py --update-title
```

Sync one row:

```bash
NOTION_TOKEN=secret_... python3 skills/notion-application-sync/scripts/sync_applications_to_notion.py \
  --posting-key "posting-id-or-ats-id"
```

Refresh the website cache before a sync when tracker files changed:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

## Scheduled Automation

The repo includes `.github/workflows/notion-application-sync.yml`, which can run every 12 hours.

Required GitHub secret:

- `NOTION_TOKEN`: Notion internal integration token shared with the configured tracker database

Optional repository variables:

- `NOTION_SYNC_ENABLED=true`: required before the scheduled job will push to Notion

The job uses `application-trackers/notion-config.md` for the Notion database/data source and reads `application-visualizer/src/data/tracker-data.json` as the normalized tracker cache.

## Matching Rules

Match Notion rows in this order:

1. exact `Posting Key`
2. exact normalized `Company` plus `Role`

If there is no unique match, skip the row and report it. Do not create duplicates automatically.

## Guardrails

- Markdown and visualizer JSON are authoritative; Notion is not.
- Do not sync without an explicit user request or the scheduled workflow being enabled.
- Do not guess Notion matches when multiple pages are plausible.
- Use `--dry-run` before a large manual sync.
- Keep this optional so the fast recruiting loop is not blocked by Notion API latency.
