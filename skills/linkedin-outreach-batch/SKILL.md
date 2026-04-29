---
name: linkedin-outreach-batch
description: Build LinkedIn recruiter outreach batches for Liam Van's application tracker. Use when the user wants to batch-get recruiter contacts, label recruiter prospects before outreach, prepare a sending-ready morning LinkedIn run, schedule a later prep pass, or update the recruiting dashboard with recruiter found but not yet reached out states.
---

# LinkedIn Outreach Batch

## Overview

Create a separate recruiter batch tracker so "recruiter found" and "outreach sent" stay distinct. Use this skill before a scheduled LinkedIn outreach run, especially when the user wants to prepare exact recipients and notes in advance, then give one batch-level confirmation while present at send time.

## Core Rule

LinkedIn messages and connection requests are third-party communications from the user's account. Do not send to any recipient that is not explicitly listed and approved in the batch tracker with an exact note, and do not click final Send unless the user gives action-time confirmation for the current batch. The confirmation may cover multiple approved rows at once; it does not need to be per recruiter. Do not spend InMail credits; check Message first only to see whether it is free, then use Connect with note if the UI shows an InMail credit or paid path.

## Batch-Get Workflow

1. Refresh the dashboard cache:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

2. Build or refresh the batch tracker:

```bash
python3 skills/linkedin-outreach-batch/scripts/build_recruiter_batch.py --min-fit 8
```

This writes `application-trackers/linkedin-recruiter-batches.md`. It preserves existing recruiter labels, approval fields, outcomes, and notes while adding newly eligible tracker rows.

3. Fill recruiter labels in the batch tracker. Prefer current company recruiters, talent acquisition, university recruiters, technical recruiters, or hiring contacts. Use founders/people leads only when there is no recruiter path.

4. Regenerate the dashboard cache after batch edits:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

The Outreach section will show batch rows as research needed, labeled, approved, sent, skipped, or blocked without marking the application's recruiter lane done.

## Approval Workflow

Before a sending-ready run, make sure each row to be sent has:

- `Recruiter Name`
- `Recruiter Profile`
- `Route` set to `try-free-inmail-then-connect-note`
- exact `Connection Note`
- `Approval` set to `Approved`
- `Outcome` set to `Not reached out`

Use the updater for small changes:

```bash
python3 skills/linkedin-outreach-batch/scripts/mark_batch_decision.py \
  --posting-key "7859317" \
  --recruiter-name "Dinaaz Tawileh" \
  --recruiter-profile "https://www.linkedin.com/in/dinaazaga/" \
  --approval Approved
```

## Batch-Run Workflow

0. Present the exact `Approved` and `Not reached out` rows and ask for one action-time confirmation to send that batch. If the user is not present, stop before final sends and leave the dashboard prepared.
1. Open each approved recruiter profile from `application-trackers/linkedin-recruiter-batches.md`.
2. Click `Message` first only to inspect whether it is free. If LinkedIn shows `Use 1 of ... InMail credit`, close the composer.
3. Use `Connect` or `More -> Connect`, add the exact connection note, and send.
4. After a successful send, record the application tracker:

```bash
python3 skills/linkedin-outreach/scripts/update_outreach_tracker.py \
  --company "Company" \
  --posting-key "Posting Key" \
  --contact-name "Recruiter Name" \
  --profile-url "https://www.linkedin.com/in/example/" \
  --contact-type recruiter \
  --date YYYY-MM-DD
```

5. Mark the batch row outcome:

```bash
python3 skills/linkedin-outreach-batch/scripts/mark_batch_decision.py \
  --posting-key "Posting Key" \
  --outcome Sent \
  --notes "Invitation sent through Connect with note"
```

6. Refresh the dashboard cache.

## Scheduling Pattern

For a 7 AM run, prepare the batch the night before. Create a thread heartbeat for 7 AM local time that says to use this skill, refresh the batch, show only `Approved` and `Not reached out` rows, ask for one action-time batch confirmation, skip paid InMail, and refresh the dashboard after recording outcomes. If no confirmation arrives, leave the queue ready and do not send.
