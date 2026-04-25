---
name: linkedin-outreach
description: Find the best LinkedIn person to reach out to for a tracked job application, usually after resume-tailor. Use when a role in application-trackers/applications.md has Reach Out enabled and you want recruiter-first outreach, University of Georgia alumni priority, connection-note drafting, and tracker updates after a LinkedIn invite is sent.
---

# LinkedIn Outreach

Use this skill after `resume-tailor` has created or updated a tracker row, especially when `Reach Out` is `Yes`.

## Default strategy

1. Start from the markdown tracker, not memory.
2. Prioritize rows that:
   - have `Reach Out` marked
   - are not `Rejected` or `Archived`
   - do not already show completed outreach in `Notes`
3. Search LinkedIn for the best contact in this order:
   - recruiter for the role or company
   - University of Georgia alumni at the company
   - engineer on the likely hiring team
   - another relevant employee if the cleaner options are unavailable
4. Prefer a LinkedIn `Connect` request with a note.
5. Avoid `InMail` unless the user explicitly wants to spend it.
6. If recruiter confidence is low, send one recruiter and one engineer.

## Tracker helpers

Build the next outreach queue from the markdown tracker:

```bash
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py
```

Useful filters:

```bash
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --limit 10
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --company "Navan"
python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --format json
```

The script filters for rows that still need outreach and sorts the highest-fit targets first.

## Connection note helper

Generate a short connection note before sending:

```bash
python3 skills/linkedin-outreach/scripts/generate_connection_note.py \
  --company "Navan" \
  --role "New College Grad Software Engineer (Backend)" \
  --target-name "Jane Smith" \
  --variant recruiter
```

Use `--variant engineer` when the note should be aimed at an engineer instead of a recruiter.

The default candidate framing matches Liam Van:

- `Liam Van`
- `liamvanpj@gmail.com`
- `6784887259`
- Seattle, Washington
- SWE at Oracle
- OCI Google Cloud Integration team
- U.S. citizen
- does not require sponsorship
- not a veteran
- Latino
- preference for New York City, also open to hybrid and in-office roles

Only include identity or work authorization details when they help answer a form or a recruiter question. Do not stuff them into the connection note.

## LinkedIn search workflow

For each target row:

1. Open the job posting or company page on LinkedIn.
2. Go to `People` or search LinkedIn people for the company.
3. Check for a recruiter first using titles like:
   - recruiter
   - talent acquisition
   - technical recruiter
   - university recruiter
   - hiring
4. If several people fit, prioritize in this order:
   - University of Georgia alumni
   - role-aligned recruiter
   - recruiter in the same city or office
   - engineer close to the role team or stack
5. If there is no clean recruiter connect path, fall back to:
   - UGA alum engineer
   - engineer on the relevant team
   - another employee with a visible `Connect` button
6. Use a note with the connection request whenever LinkedIn allows it.
7. If only a follow button or message-only flow is available, skip and move on unless the user asks for a manual fallback.

## After a send

Record the contact immediately in the markdown tracker:

```bash
python3 skills/linkedin-outreach/scripts/update_outreach_tracker.py \
  --company "Navan" \
  --posting-key "4401351489" \
  --contact-name "Jane Smith" \
  --profile-url "https://www.linkedin.com/in/jane-smith/" \
  --contact-type recruiter \
  --date 2026-04-25
```

Use `--contact-type engineer` for engineer outreach. Recruiter sends also populate `Recruiter Contact` and `Recruiter Profile` when those fields are empty.

## Coordination with resume-tailor

This skill pairs naturally with `resume-tailor`:

1. tailor the resume
2. update the tracker
3. if `Reach Out` is `Yes`, run this skill
4. record every successful invite in the tracker so later Gmail and Notion refreshes do not need to guess

## Guardrails

- Keep outreach truthful and brief.
- Prefer the user-approved note style over inventing a new voice each time.
- Do not claim an application was submitted unless that is already true.
- Do not update Notion here unless the user explicitly asks; this skill should keep the markdown tracker authoritative.
