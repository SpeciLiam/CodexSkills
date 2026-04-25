---
name: company-prospecting
description: Build and maintain a separate company-to-people outreach prospect tracker for job applications. Use when you want the top 3 recruiter, alumni, engineer, or employee contacts per company in markdown, plus Apollo email lookup status that stays separate from application-trackers/applications.md.
---

# Company Prospecting

Use this skill when you want a separate tracker of who to contact at each company before email outreach.

## Goal

Turn each company into a small prospect list:

- start from active rows in `application-trackers/applications.md`
- create a separate queue in `application-trackers/outreach-prospects.md`
- find up to 3 strong people per company
- look up their Apollo emails
- keep company-level and person-level progress out of the application tracker

## Default ranking

For each company, prioritize prospects in this order:

1. recruiter for the role or hiring team
2. University of Georgia alumni at the company
3. engineer on the likely team
4. another relevant employee with a visible path to reply

If recruiter confidence is low, include both a recruiter and an engineer in the top 3.

## Seed the separate tracker

Create or refresh the company queue from `applications.md`:

```bash
python3 skills/company-prospecting/scripts/sync_company_prospect_tracker.py
```

Useful filters:

```bash
python3 skills/company-prospecting/scripts/sync_company_prospect_tracker.py --limit 20
python3 skills/company-prospecting/scripts/sync_company_prospect_tracker.py --company "Navan"
```

This keeps `application-trackers/outreach-prospects.md` as the source of truth for prospecting.

## Find the next companies that still need names

```bash
python3 skills/company-prospecting/scripts/build_company_prospect_targets.py
```

This highlights companies that still have fewer than 3 prospects or are missing Apollo emails.

## Record prospects

After identifying a person on LinkedIn, record them immediately:

```bash
python3 skills/company-prospecting/scripts/record_company_prospect.py \
  --company "Navan" \
  --posting-key "4401351489" \
  --priority 1 \
  --target-type recruiter \
  --name "Jane Smith" \
  --title "Technical Recruiter" \
  --linkedin-url "https://www.linkedin.com/in/jane-smith/" \
  --email-status "Needs Apollo"
```

After Apollo finds an email, update the same row:

```bash
python3 skills/company-prospecting/scripts/record_company_prospect.py \
  --company "Navan" \
  --posting-key "4401351489" \
  --priority 1 \
  --name "Jane Smith" \
  --apollo-email "jane@navan.com" \
  --email-status "Ready"
```

Use `target-type` values like `recruiter`, `alumni`, `engineer`, or `general`.

## Expected workflow

1. run `resume-tailor`
2. update `applications.md`
3. run this skill to seed the separate company prospect tracker
4. for each queued company, find the top 3 names on LinkedIn
5. use Apollo to look for email addresses
6. record names, titles, LinkedIn URLs, Apollo emails, and status in `outreach-prospects.md`
7. use that tracker for outreach batching later

## Guardrails

- Keep this tracker separate from `applications.md`.
- Prefer real people over generic company inboxes.
- Do not invent email addresses.
- Mark uncertain or partial Apollo matches in `Notes`.
- Keep the top 3 focused; do not spray extra names into the tracker unless the user asks.
