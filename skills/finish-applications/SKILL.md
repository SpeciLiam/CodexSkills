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

Then build the application queue. The queue intentionally includes both `Resume Tailored` rows and `Manual Apply Needed` rows; only rows with concrete blockers should remain manual, while stale/generic manual rows should be retried:

```bash
python3 skills/finish-applications/scripts/build_application_queue.py --limit 10
```

To mark Workday rows in the tracker for Liam:

```bash
python3 skills/finish-applications/scripts/build_application_queue.py --mark-workday-manual
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
   - Prioritize `Applied` false, existing resume PDF, fit score >= 8, and `Status` of either `Resume Tailored` or `Manual Apply Needed`.
   - Keep `Manual Apply Needed` rows in the same queue as still-needed applications. If the recorded reason is not a true manual blocker, retry the application path and replace the stale note with the real outcome.
   - Lower-fit rows can be processed only when the user asks for all unapplied applications or the high-fit queue is empty.
   - Skip rows whose posting link is missing, expired, or clearly no longer accepts applications. Report them as blocked.
   - Do not submit Workday applications. Treat any posting whose source, URL, or notes mention Workday as manual-only.
   - Run `build_application_queue.py --mark-workday-manual` so Liam can find those rows later by searching for `Manual apply needed`.
   - Do not treat `LinkedIn login` as a final manual blocker when Liam's authenticated Chrome profile is available. Open the LinkedIn job in Chrome, click `Apply` or `Apply on company website`, capture the real ATS URL, and continue there. Update the tracker source/link/posting key when a direct ATS posting is discovered.

3. Open one application at a time.
   - Use the row's `Job Link`, `Resume PDF`, company, role, location, and source.
   - Prefer the tailored resume path in `Resume PDF`; do not upload the generic resume unless the tracker row explicitly points to it.
   - Use existing factual profile information from `generic-resume/README.md` and the tailored resume when answering routine application fields.
   - If the form has a required cover letter field or upload, generate a tailored cover letter first using the `resume-tailor` skill's cover-letter workflow in the same company-specific resume folder, then upload or paste it as requested. Base the letter on the tailored resume, the job posting, and Liam's saved profile context; keep it truthful, concise, and role-specific.
   - If the cover letter field is optional and the form can be submitted without it, skip it unless the job posting explicitly asks for one or Liam has provided company-specific cover letter instructions.
   - For LinkedIn-sourced rows marked `Manual apply needed: LinkedIn login`, first retry through the authenticated Chrome session:
     1. Open the LinkedIn job URL in Chrome.
     2. Verify Liam is signed in and the job is the same company/role.
     3. Click `Apply`, `Apply on company website`, or the equivalent LinkedIn apply control.
     4. If it opens an external ATS such as Lever, Ashby, Greenhouse, Rippling, SmartRecruiters, or a company careers page, use that URL as the active application link and continue the normal form workflow.
     5. If LinkedIn shows Easy Apply, continue only for routine fields and stop before final submission for confirmation. Always verify and reset the contact email to `liamvanpj@gmail.com`; LinkedIn may prefill `liampjvan@gmail.com`, which should not be used.
     6. If LinkedIn or the ATS shows login, 2FA, CAPTCHA, account creation, or bot/AI-deterrent verification, keep it manual and record that specific blocker instead of the generic LinkedIn login note.

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
   If the blocker is something Liam must complete later, such as CAPTCHA, forced login after the authenticated LinkedIn retry, account creation, bot/AI-deterrent verification, legal address, signature, consent that is not covered by Liam's standing answers, or custom motivation text, set `Status` to `Manual Apply Needed` and append a specific `Manual apply needed: ... YYYY-MM-DD` note. Avoid generic `LinkedIn login` notes unless the authenticated Chrome retry is unavailable or LinkedIn itself has actually logged Liam out.
   If the posting is unavailable or closed, set `Status` to `Archived` and append a short factual note.
   For Workday rows, do not open the application flow. Leave `Status` as `Resume Tailored`, leave `Applied` blank, and append `Manual apply needed: Workday posting YYYY-MM-DD` if that note is not already present.

7. Continue through the queue.
   - Batch user questions when possible instead of interrupting for every small field.
   - After tracker edits, refresh the visualizer cache:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
```

## Answering Form Questions

Use the candidate profile and resume as evidence. Keep answers concise and truthful.

### Liam's Standing Answers

Use these saved answers without interrupting Liam unless a form asks for a materially different or more specific commitment:

- Full name: Liam Van.
- Email: liamvanpj@gmail.com.
- Phone: 678-488-7259.
- Current location: Seattle, WA.
- Legal address: 1421 Harvard Avenue, Seattle, WA 98122.
- Current company: Oracle.
- LinkedIn: https://www.linkedin.com/in/liam-van.
- GitHub: https://github.com/SpeciLiam.
- Portfolio / website: https://liamvan.dev.
- School: University of Georgia, School of Computing.
- Degree: Bachelor of Science in Computer Science.
- School start date: August 2021.
- Graduation date: Dec 2024; graduation year: 2024.
- Work authorization: Liam is a U.S. citizen.
- Sponsorship: Liam does not require employer sponsorship now or in the future.
- Location/relocation: Liam is open to the locations where he is applying, with a preference for NYC and SF.
- Race/ethnicity: Hispanic / Latino and Two or More Races. For "select all that apply" demographic questions, select the reasonable matching options from those labels.
- Disability status: not disabled.
- Veteran status: not a veteran / not a protected veteran.
- Routine applicant privacy notices and data-processing acknowledgements: acknowledge when required to submit.

### Reusable Custom Answer Seeds

Use these as source material for short custom questions, but do not submit custom essays without reviewing the final text when the question is personal, evaluative, or company-specific.

- Favorite or proud AI project: Liam created an AI skill that reduced stress for the on-call engineer and the broader team during high-severity incidents. When a high-severity issue arose, the skill would trigger in parallel with the manual incident response and begin an organized investigation: gathering context, structuring possible causes, tracking evidence, and helping the human on-call engineer move faster without replacing their judgment. This is a good answer seed for prompts about a project Liam liked working on, AI improving a workflow, operational impact, incident response, developer productivity, or helping a team under pressure.

Preserve Liam's flow: keep applying with these defaults and only ask when there is a hard blocker such as login, 2FA, CAPTCHA, account creation, a legal signature/attestation beyond routine privacy acknowledgement, a salary/start-date/custom essay question, or a question whose answer cannot reasonably be derived from these standing answers.

Fill every required factual field that can be answered from Liam's profile, resume, tracker, or standing answers. Leave optional free-text prompts like `Anything else?`, `Additional information`, or similar blank unless the tracker/profile already provides a precise answer. Treat anti-automation or AI-deterrent gates, including CAPTCHA, bot checks, forced login traps, or verification-only walls, as manual follow-up items for Liam instead of repeatedly attempting them.

### Cover Letters

When an application requires a cover letter upload or cover letter text:

1. Use the existing `Resume Folder` from the tracker row and the cover-letter commands documented in `skills/resume-tailor/SKILL.md`.
2. Create the letter in that folder with:

```bash
python3 skills/resume-tailor/scripts/create_cover_letter.py \
  --dir "<company resume folder>" \
  --company "<Company>" \
  --role "<Role>" \
  --why-interest "<2-3 sentences on why the role is a strong fit based on the job description and Liam's background>"
```

   The `--why-interest` value should be grounded in the posting and Liam's truthful project/work evidence.
3. Render the PDF with:

```bash
python3 skills/resume-tailor/scripts/render_cover_letter_pdf.py \
  --dir "<company resume folder>"
```

4. Upload the resulting PDF named `Liam_Van_<Company>_Cover_Letter.pdf` to the cover letter field when the form requests a file, or paste the generated letter text when the form requests text.
5. Record in the tracker note that a tailored cover letter was submitted.

Do not generate a cover letter for optional fields when the application accepts a resume-only submission, unless Liam has specifically asked for one for that company or role.
If no cover letter field exists, skip this step and continue the application as normal.

### Manual Apply Criteria

Use `Manual Apply Needed` only for real blockers that Liam should handle directly:

- Login/account blockers after retrying LinkedIn through Liam's authenticated Chrome profile
- CAPTCHA, hCaptcha, reCAPTCHA, bot checks, anti-automation, or AI-deterrent gates
- 2FA, email/SMS OTP, password prompts, account creation, or account recovery
- Legal signature, background-check consent, declarations of accuracy, or non-routine legal attestations
- Consent choices not covered by the standing answers, such as AI notetaker consent or partner-sharing consent
- Required salary, start-date, deadline, relocation, or location commitments not already covered by the standing answers
- Required custom essays, motivation prompts, culture-fit prompts, project/accomplishment prompts, or company-specific free responses
- Missing or closed application forms, expired postings, redirects to materially different roles, or sites with no visible apply path

Do not use `Manual Apply Needed` for these by themselves:

- A LinkedIn job URL when authenticated Chrome can reveal a direct ATS link
- A routine external ATS form asking only saved profile fields, resume upload, work authorization, sponsorship, location openness, referral/source, school, degree, graduation dates, veteran/disability, or matching demographic options

Safe to answer without asking when the answer is clearly available:

- name, email, phone, website, GitHub, LinkedIn, school, degree, graduation date
- resume upload and portfolio links
- employment history already represented in the resume/profile
- standard "how did you hear about us" from the tracker `Source`
- referral as `No` or blank when the tracker has no referral value

Ask instead of guessing for anything not evidenced. If a form has optional demographic questions, prefer Liam's standing answers when the form offers matching choices; otherwise leave optional fields blank or choose the neutral "decline to self-identify" style option when available.

## Tracker Rules

- Workday rows are for Liam to submit manually. Never attempt to complete them as the agent.
- Never mark a row applied based only on opening the form or clicking LinkedIn Easy Apply before the confirmation step.
- Treat a visible confirmation page, confirmation email, or application portal status as sufficient evidence.
- Keep notes short: `Application submitted YYYY-MM-DD`, `LinkedIn Easy Apply submitted YYYY-MM-DD`, `Posting closed YYYY-MM-DD`, `Blocked on custom question YYYY-MM-DD`, `Manual apply needed: LinkedIn login YYYY-MM-DD`, or `Manual apply needed: Workday posting YYYY-MM-DD`.
- Preserve recruiter and engineer contact fields.
- If multiple tracker rows match the same company, pass `--posting-key` to the update script.
- Refresh the dashboard cache after any tracker update.

## Final Response

Summarize:

- submitted applications
- Workday applications marked for manual submission
- blocked applications and the exact question or obstacle
- skipped applications and why
- tracker/cache updates made
- suggested next lane, usually recruiter or engineer outreach for newly applied high-fit rows
