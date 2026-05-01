---
name: greenhouse-sourcing
description: Source high-volume SWE I, SWE II, early-career, new-grad, founding engineer, generalist, backend, full-stack, and forward-deployed roles from MyGreenhouse or Greenhouse job boards, dedupe them against Liam Van's CodexSkills application tracker, rank fit, queue resume tailoring, and apply through Greenhouse autofill where possible.
---

# Greenhouse Sourcing

Use this skill when Liam wants to mine Greenhouse for fresh software engineering roles, add strong matches to the CodexSkills dataset, tailor batches of resumes, and submit applications efficiently.

This skill is a sourcing and batching layer. Route actual resume edits through `resume-tailor`, actual submissions through `finish-applications`, and dashboard updates through `application-visualizer-refresh`.

## Sources Of Truth

- Tracker: `application-trackers/applications.md`
- Candidate profile and generic resume: `generic-resume/README.md` and `generic-resume/resume.tex`
- Queue builder: `skills/greenhouse-sourcing/scripts/build_greenhouse_queue.py`
- Resume workflow: `skills/resume-tailor/SKILL.md`
- Apply workflow: `skills/finish-applications/SKILL.md`

Markdown is authoritative. Never let scraped search results overwrite tracker truth.

## Default Search

Start from Liam's MyGreenhouse search unless he gives a different one:

```text
https://my.greenhouse.io/jobs?query=Software%20engineer&location=United%20States&lat=39.71614&lon=-96.999246&location_type=country&country_short_name=US&date_posted=past_day&employment_type[]=full_time
```

MyGreenhouse requires Liam's logged-in browser session, so use Chrome or the in-app browser when authentication is needed. Do not try to bypass login, CAPTCHA, bot checks, or anti-automation controls.

## Fit Target

Maximize volume, but only queue roles that plausibly fit Liam's profile:

- Strong yes: SWE I, SWE II, Software Engineer, Backend, Full Stack, Platform, Product Engineer, Generalist, Founding Engineer, Forward Deployed Engineer, Member of Technical Staff, Applied AI Engineer, early-career, university grad, new grad, associate engineer.
- Maybe yes: all-levels engineering roles when the posting does not require senior-only ownership, startup founding/generalist roles that value 1-3 years, customer-facing/deployed engineering roles.
- Usually skip: senior/staff/principal/manager, internships, unpaid roles, contractor-only roles, cleared-only roles, embedded-only roles when the resume has no strong match, roles requiring 4+ years unless the rest is unusually flexible.
- Hard skip: jobs already tracked, closed/unavailable postings, roles outside the United States unless remote-US is explicit, non-engineering sales/recruiting/support roles unless Liam explicitly asks.

Default allowed locations are Washington DC, Bay Area, Seattle, remote, and NYC. The queue builder enforces those by default; use repeated `--allowed-location` flags to override for a specific run, or `--no-location-filter` only when Liam explicitly widens the search.

If a role is a stretch but plausible, keep it in the queue with a note rather than silently discarding it.

## Browser Capture

For MyGreenhouse, prefer browser capture over manual clicking through every card.

1. Open the search URL in Liam's logged-in Chrome session.
2. Apply filters: United States, full-time, past day or the requested freshness window.
3. Scroll until the result list stops loading.
4. Capture results by the fastest available route:
   - Browser/network JSON if visible in devtools or the in-app browser inspector.
   - Page DOM extraction if result cards are rendered in the document.
   - Manual copy/paste only as fallback.
5. Save captured jobs as JSON, JSONL, CSV, or TSV, usually in `/tmp/greenhouse_jobs.json`.

Useful console snippet for DOM extraction when result cards are visible:

```js
copy(JSON.stringify([...document.querySelectorAll("a[href*='greenhouse'], a[href*='gh_jid'], a[href*='jobs']")].map((a) => ({
  title: a.innerText.trim(),
  url: a.href,
  company: a.closest("[data-testid], li, article, div")?.innerText?.split("\n")?.find(Boolean) || "",
  location: a.closest("[data-testid], li, article, div")?.innerText || ""
})).filter((job) => job.title && job.url), null, 2))
```

The snippet is intentionally broad. Clean ranking happens locally in the queue builder.

## Build The Queue

After saving captured jobs, build a ranked, deduped queue:

```bash
python3 skills/greenhouse-sourcing/scripts/build_greenhouse_queue.py \
  --input /tmp/greenhouse_jobs.json \
  --limit 60 \
  --format markdown
```

For machine-readable output:

```bash
python3 skills/greenhouse-sourcing/scripts/build_greenhouse_queue.py \
  --input /tmp/greenhouse_jobs.json \
  --limit 120 \
  --format json > /tmp/greenhouse_queue.json
```

Use `--include-stretch` when Liam wants maximum volume and is comfortable with plausible 3-4 year or all-levels roles.

## Batch Workflow

1. Refresh context:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode resume
```

2. Capture Greenhouse jobs from the logged-in browser and save them to `/tmp/greenhouse_jobs.json`.
3. Run the queue builder and take the top 10 strong matches:

```bash
python3 skills/greenhouse-sourcing/scripts/build_greenhouse_queue.py \
  --input /tmp/greenhouse_jobs.json \
  --limit 10 \
  --format json > /tmp/greenhouse_queue_batch_10.json
```

4. For each of the 10 queue items, use `resume-tailor`:
   - Extract company, title, location, posting URL, responsibilities, qualifications, and repeated keywords.
   - Prepare the resume folder, tailor `resume.tex`, render the PDF, verify one page, and update `applications.md` with `Source` set to `Greenhouse`.
   - Use the direct Greenhouse board URL when available, not only the MyGreenhouse search URL.
5. After the 10 resumes are tailored, use `finish-applications` to submit those 10 ready rows:
   - Prefer Greenhouse's own `Autofill with resume` or MyGreenhouse autofill button.
   - Upload the tailored PDF from the tracker row, not the generic resume.
   - Use Liam's standing answers from `finish-applications`.
   - Stop for CAPTCHA, login, 2FA, account creation, legal signature, custom essay, or any non-routine consent.
   - Present one batch review before final submission that lists all 10 companies, roles, destinations, resume PDFs, and any non-default answers. Use one grouped approval for the final submit buttons; do not interrupt for every routine field.
6. After the batch, refresh the visualizer cache, stage only the batch's tracker/cache/resume changes, commit, and push:

```bash
python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py
git status --short
git add application-trackers/applications.md application-visualizer/src/data/tracker-data.json companies/<batch-company-dirs> skills/greenhouse-sourcing
git commit -m "Add Greenhouse application batch"
git push
```

## Volume Defaults

For a mass pass:

- Work in strict batches of 10: source 10, tailor 10, apply 10, update tracker/cache, commit, and push.
- Keep the queue file for resume-tailor follow-through; do not lose skipped roles.
- If fewer than 10 strong Greenhouse roles are available in the current search, widen the search window or add compatible queries such as `backend engineer`, `full stack engineer`, `new grad software engineer`, `founding engineer`, `platform engineer`, and `forward deployed engineer` until the batch has 10 or the available pool is exhausted.
- If time is short, prioritize direct Greenhouse apply forms with autofill over roles that redirect to Workday or require account creation.
- Minimize approvals by batching them. The agent may source, tailor, fill routine fields, update local tracker files, commit, and push within the batch flow; final submission to employers still needs the grouped batch review when required by Codex action policy.

## Tracker Rules

- Use posting IDs from `gh_jid`, Greenhouse board paths, or direct job URLs as `Posting Key`.
- Record `Source` as `Greenhouse` for Greenhouse board or MyGreenhouse-sourced roles.
- If a role is found via MyGreenhouse but the application form lives on an employer site, record the final direct posting URL.
- Dedupe by posting key, job URL, and company plus normalized title.
- Record blockers with dated, factual notes such as `Manual apply needed: Greenhouse reCAPTCHA 2026-04-30`.
- Do not mark `Applied` until a confirmation page, confirmation email, or portal status confirms submission.

## Guardrails

- Keep every resume truthful. Do not invent skills, titles, years of experience, or domain expertise to chase volume.
- Do not submit custom essays without reviewing the exact answer or getting Liam's approval.
- Do not bypass anti-bot controls or terms-sensitive gates.
- Prefer high-throughput routine forms; pause or mark manual when the form becomes legally or personally sensitive.
