---
name: gmail-application-refresh
description: Review Gmail for application-related emails, infer status changes such as applied, online assessment, interview, rejection, or offer, and update the markdown and Notion application trackers without creating duplicate or low-confidence changes.
---

# Gmail Application Refresh

Use this skill when the user wants to refresh application statuses from Gmail.

For full recruiting sessions, start with `recruiting-pipeline`; it runs Gmail/status refresh before outbound work so stale rows do not waste outreach time.

This skill is designed for safe updates:

- read recent application-related emails
- match those emails to existing tracker rows
- update only high-confidence status changes
- leave ambiguous emails alone and report them instead of guessing

## Best Use

This skill works best as a run-on-demand refresh.

That is the recommended default:

1. scan recent Gmail messages
2. infer meaningful application changes
3. update the markdown tracker
4. update the matching Notion row
5. summarize what changed and what still needs review

If the user later wants this on a schedule, this skill can be used inside an automation.

## Inputs

Gather these first:

1. the markdown tracker in `application-trackers/applications.md`
   or the generated tracker cache in `application-visualizer/src/data/tracker-data.json`
2. the Notion config in `application-trackers/notion-config.md`
3. recent Gmail messages likely related to jobs

Start from the tracker, not from the inbox.

For target building, prefer the generated cache when available because it has normalized application rows. Refresh it with:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

If the cache is missing, use the markdown tracker directly.

The preferred refresh flow is:

1. read `application-trackers/applications.md`
2. build the active target list from rows whose status is not `Rejected` or `Archived`
3. search Gmail only for those tracked companies and roles first
4. classify status changes only for those active rows
5. skip broad inbox scanning unless the targeted search misses something obvious

Prefer Gmail searches like:

- `from:(jobs-listings@linkedin.com OR jobs-noreply@linkedin.com OR linkedin-noreply@linkedin.com) newer_than:30d`
- `subject:(application OR interview OR assessment OR recruiter OR update OR next steps) newer_than:30d`
- `from:(greenhouse.io OR ashbyhq.com OR lever.co OR workday.com) newer_than:30d`
- `label:inbox newer_than:30d ("application" OR "interview" OR "assessment" OR "next steps")`

For the best precision, build company-specific searches from the active tracker rows, such as:

- `newer_than:30d ("Robinhood" OR "Software Engineer, Backend")`
- `newer_than:30d ("LinkedIn" OR "Software Engineer - Applications")`
- `newer_than:30d ("Automat" OR "Software Engineer (Junior/Intermediate)")`

Tune the query if you notice a company-specific sender pattern.

## Matching Rules

Prefer to match an email to a tracker row using, in order:

1. posting ID or ATS ID present in the email URL
2. exact company name plus role title
3. company name plus a uniquely matching ATS/source domain
4. company name only, if there is exactly one open matching row

Do not update the tracker if multiple rows are plausible and you cannot disambiguate confidently.

## Status Rules

Map emails conservatively:

- `Applied`
  Use when the email clearly confirms submission, such as `application received`, `thanks for applying`, or a Workday/Ashby/Greenhouse confirmation.
- `Online Assessment`
  Use when the email includes a coding test, take-home, OA portal, HackerRank, CodeSignal, or similar assessment invite.
- `Interviewing`
  Use when the email schedules or requests a recruiter screen, phone screen, hiring manager chat, or technical interview.
- `Rejected`
  Use when the email clearly says the company is not moving forward.
- `Offer`
  Use only for explicit offer or offer-call emails.

Do not automatically use `Archived` from email evidence alone.

## Applied Column Rules

- Set `Applied` to `Yes` when a submission confirmation email exists.
- Leave it unchanged if the email is only a marketing reminder or a recruiter outreach that does not confirm submission.

## Notes Rules

Append short factual notes, not long summaries.

Good notes:

- `Application confirmation email received 2026-04-07`
- `CodeSignal assessment received 2026-04-08`
- `Recruiter screen requested 2026-04-09`
- `Rejection email received 2026-04-10`

Avoid copying full email text into the tracker.

## Files

- Markdown tracker: `application-trackers/applications.md`
- Notion config: `application-trackers/notion-config.md`
- Target builder: `skills/gmail-application-refresh/scripts/build_refresh_targets.py`
- Status helper: `skills/gmail-application-refresh/scripts/update_application_status.py`

## Start Command

Use this command first:

```bash
python3 skills/gmail-application-refresh/scripts/build_refresh_targets.py
```

That command:

- reads the markdown tracker
- filters out rows with status `Rejected` or `Archived`
- prints the active applications that still need monitoring
- prints suggested Gmail queries for each one

If you want machine-readable output instead:

```bash
python3 skills/gmail-application-refresh/scripts/build_refresh_targets.py --format json
```

## Markdown Update Flow

Use the helper script to update only the status fields that changed:

```bash
python3 skills/gmail-application-refresh/scripts/update_application_status.py \
  --company "Company Name" \
  --role "Role Title" \
  --job-link "https://example.com/job" \
  --status "Interviewing" \
  --applied "Yes" \
  --notes "Recruiter screen requested 2026-04-07"
```

This script:

- finds the existing row
- updates only the requested fields
- preserves the rest of the row
- refreshes the markdown header count

## Notion Update Flow

If `application-trackers/notion-config.md` exists, mirror the same change in Notion.

Recommended property mapping:

- `Status`
- `Applied`
- `Referral` if relevant
- `Notes`

Search Notion by company first, then confirm the row using:

- `Posting Key`
- `Role`
- `Job Link`

If multiple rows exist for the same company, do not guess. Match by posting key or leave it for review.

## Confidence Rules

Update automatically only when confidence is high.

High confidence examples:

- email includes the exact company name and exact role title
- email includes the ATS link with the posting identifier
- email comes from the company ATS and explicitly confirms a status change

Low confidence examples:

- generic recruiter outreach with no role
- job recommendations
- marketing newsletters
- emails about a company when multiple roles are tracked and no posting clue is present

For low-confidence cases:

- do not update trackers
- report the candidate match and why it was skipped

## Suggested Workflow

1. Read `application-trackers/applications.md`
2. Build the active row set by excluding rows with status `Rejected` or `Archived`
3. Search Gmail for recent application-related emails that mention those companies or roles
4. Batch-read the strongest candidates
5. Build a small change list with:
   - company
   - role
   - matched row
   - proposed new status
   - whether `Applied` should become `Yes`
   - short note to append
   - confidence level
6. Apply only high-confidence updates to markdown
7. Mirror the same changes into Notion
8. Summarize:
   - updated rows
   - skipped ambiguous emails
   - any sender patterns worth using next time

## Output Expectations

The final response should include:

1. what changed
2. which tracker rows were updated
3. any ambiguous emails that were skipped
4. whether markdown and Notion stayed in sync

## Notes

- This skill is better as a manual refresh than a perpetual listener by default.
- If the user wants it on a schedule later, use this skill inside an automation instead of trying to build a permanent listener.
