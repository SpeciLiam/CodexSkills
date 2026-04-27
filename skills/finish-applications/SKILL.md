---
name: finish-applications
description: Complete Liam Van's tracked job applications that have tailored resumes but are not yet applied. Use when the user wants an agent to work through `application-trackers/applications.md` rows with `Applied` blank/false and `Status` like `Resume Tailored`, submit the applications where possible, ask the user only for blocking form answers or consent-sensitive choices, update the markdown tracker, and refresh the recruiting dashboard cache.
---

# Finish Applications

## Overview

Use this skill to turn ready tracker rows into submitted applications with minimal user interruption.
The agent should prioritize high-fit, tailored, unapplied rows; open each posting; submit using the tailored resume already recorded in the tracker; and update the source-of-truth markdown after each confirmed submission.

## Sources Of Truth

Use these files and scripts:

- Markdown tracker: `application-trackers/applications.md`
- Generated cache: `application-visualizer/src/data/tracker-data.json`
- Queue builder: `skills/finish-applications/scripts/build_application_queue.py`
- Status updater: `skills/gmail-application-refresh/scripts/update_application_status.py`
- Dashboard refresh: `skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py`

Markdown is authoritative. Use the cache only as a normalized read model and refresh it after tracker edits.

## Start Command

Refresh the cache first when it may be stale:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

Then build the application queue:

```bash
python3 skills/finish-applications/scripts/build_application_queue.py --limit 10
```

For JSON output:

```bash
python3 skills/finish-applications/scripts/build_application_queue.py --limit 10 --format json
```

## Workflow

1. Refresh status first when emails may have changed.
   - For a full run, start with `recruiting-pipeline --mode apply` or run the Gmail refresh skill before submitting.
   - Do not apply to rows that are already `Applied`, `Rejected`, `Archived`, `Online Assessment`, `Interviewing`, or `Offer`.

2. Build and inspect the queue.
   - Prioritize `Status: Resume Tailored`, `Applied` false, existing resume PDF, fit score >= 8.
   - Lower-fit rows can be processed only when the user asks for all unapplied applications or the high-fit queue is empty.
   - Skip rows whose posting link is missing, expired, or clearly no longer accepts applications. Report them as blocked.

3. Open one application at a time.
   - Use the row's `Job Link`, `Resume PDF`, company, role, location, and source.
   - Prefer the tailored resume path in `Resume PDF`; do not upload the generic resume unless the tracker row explicitly points to it.
   - Use existing factual profile information from `generic-resume/README.md` and the tailored resume when answering routine application fields.

4. Ask the user only for blockers.
   Ask before submitting when the form requests information that is not safely inferable, including:
   - demographic self-identification choices
   - disability/veteran status when no known saved answer exists
   - work authorization, sponsorship, relocation, salary, start date, or location commitments if the form requires a specific answer and the answer is not already in the candidate profile
   - custom essays, free-response questions, or company-specific motivations
   - account creation, login, 2FA, CAPTCHA, payment, or anything requiring user credentials
   - legal attestations, background check consent, signature fields, or declarations of accuracy if the agent cannot show the user the exact final state first

5. Submit only when ready.
   - Before final submission, verify company, role, resume upload, contact info, and required answers.
   - Do not submit if the posting redirects to a different role or company unless the user approves.
   - Do not guess at questions that could materially affect eligibility or legal consent.

6. Record the result immediately after a confirmed submission.
   Use:

```bash
python3 skills/gmail-application-refresh/scripts/update_application_status.py \
  --company "Company Name" \
  --role "Role Title" \
  --posting-key "posting-key" \
  --status "Applied" \
  --applied "Yes" \
  --notes "Application submitted YYYY-MM-DD"
```

   If the application cannot be completed, do not mark it applied. Append a short note only when it is useful and factual, such as `Posting closed 2026-04-27` or `Blocked on sponsorship question 2026-04-27`.

7. Continue through the queue.
   - Batch user questions when possible instead of interrupting for every small field.
   - After tracker edits, refresh the visualizer cache:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

## Answering Form Questions

Use the candidate profile and resume as evidence. Keep answers concise and truthful.

Safe to answer without asking when the answer is clearly available:

- name, email, phone, website, GitHub, LinkedIn, school, degree, graduation date
- resume upload and portfolio links
- employment history already represented in the resume/profile
- standard "how did you hear about us" from the tracker `Source`
- referral as `No` or blank when the tracker has no referral value

Ask instead of guessing for anything not evidenced. If a form has optional demographic questions, prefer the user's known preference if documented; otherwise leave optional fields blank or choose the neutral "decline to self-identify" style option when available.

## Tracker Rules

- Never mark a row applied based only on opening the form or clicking LinkedIn Easy Apply before the confirmation step.
- Treat a visible confirmation page, confirmation email, or application portal status as sufficient evidence.
- Keep notes short: `Application submitted YYYY-MM-DD`, `LinkedIn Easy Apply submitted YYYY-MM-DD`, `Posting closed YYYY-MM-DD`, or `Blocked on custom question YYYY-MM-DD`.
- Preserve recruiter and engineer contact fields.
- If multiple tracker rows match the same company, pass `--posting-key` to the update script.
- Refresh the dashboard cache after any tracker update.

## Final Response

Summarize:

- submitted applications
- blocked applications and the exact question or obstacle
- skipped applications and why
- tracker/cache updates made
- suggested next lane, usually recruiter or engineer outreach for newly applied high-fit rows
