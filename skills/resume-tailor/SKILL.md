---
name: resume-tailor
description: Tailor a one-page resume from a generic Overleaf LaTeX resume using a job description URL or pasted posting. Use when the user wants to reorder skills, trim irrelevant content, strengthen bullets, remove weaker roles, and create a company-specific resume folder while keeping the output truthful and concise.
---

# Resume Tailor

Use this skill when a user wants to adapt the generic resume to a specific job posting.

For full recruiting sessions that include status refreshes, applications, recruiter/engineer outreach, prospecting, and dashboard refreshes, start with `recruiting-pipeline` and let it route into this skill for new role tailoring.

When the user wants to focus only on resume tailoring but still keep the surrounding recruiting flow organized, run:

```bash
python3 skills/recruiting-pipeline/scripts/build_daily_recruiting_plan.py --mode resume
```

Then tailor the requested role, update the tracker, and only continue into apply/outreach steps when the plan or user request calls for it.

## Inputs

Gather these before editing:

1. A job description URL, or the pasted job description text
2. The target company name
3. The generic resume source in `generic-resume/`
4. The candidate metadata in `generic-resume/README.md`

If a link is provided, open it and extract:

- Title
- Company
- Seniority
- Must-have skills
- Nice-to-have skills
- Repeated keywords
- Domain signals such as startup, AI, frontend, backend, infra, product, leadership, or customer-facing work

## Files and folders

- Generic source resume lives in `generic-resume/`
- The primary resume source file should usually be `generic-resume/resume.tex`
- Candidate metadata lives in `generic-resume/README.md`
- Set `candidate_name: Your Name` in that README so the scripts can name output folders and PDFs
- Treat `generic-resume/README.md` as the richer candidate profile and evidence source, not just naming metadata
- Treat the generic resume and README as the context bank; they can be richer than one page because the tailored output is what must be compressed to one page
- Company outputs should live in `companies/<Company Name>/<Role_Slug>/<Candidate_Name>_Resume/` when a role title is known
- If the same role is tailored again, create `companies/<Company Name>/<Role_Slug>/<Candidate_Name>_Resume_2`, then `_3`, and so on
- Fall back to `companies/<Company Name>/<Candidate_Name>_Resume/` only when the role is unknown
- Application tracking lives in `application-trackers/applications.md`
- Optional Notion tracking should mirror the markdown tracker in a database named `Application Tracker`
- If `application-trackers/notion-config.md` exists, use it as the source of truth for the Notion parent page and data source to update

Before editing, prepare the output directory with:

```bash
python3 skills/resume-tailor/scripts/prepare_resume_folder.py \
  --company "Company Name" \
  --role "Role Title"
```

This copies the generic resume files into the correct company and role specific folder and prints the destination path.

After editing, render a final PDF in the same folder with:

```bash
python3 skills/resume-tailor/scripts/render_resume_pdf.py \
  --dir "companies/Company Name/Role_Slug/Candidate_Name_Resume"
```

This attempts to compile `resume.tex` and writes a final PDF named `<Candidate_Name>_<Company_Name>.pdf` in that same company-specific folder.

If the user wants a basic cover letter in the same folder, create it with:

```bash
python3 skills/resume-tailor/scripts/create_cover_letter.py \
  --dir "companies/Company Name/Role_Slug/Candidate_Name_Resume" \
  --company "Company Name" \
  --role "Role Title" \
  --why-interest "Two to three sentences on why the role is a fit"
```

Then render the cover letter PDF with:

```bash
python3 skills/resume-tailor/scripts/render_cover_letter_pdf.py \
  --dir "companies/Company Name/Role_Slug/Candidate_Name_Resume"
```

This writes `cover_letter.tex` and a final PDF named `<Candidate_Name>_<Company_Name>_Cover_Letter.pdf` right next to the tailored resume PDF.

After the folder and PDF exist, update the markdown tracker with:

```bash
python3 skills/resume-tailor/scripts/update_application_tracker.py \
  --company "Company Name" \
  --role "Role Title" \
  --job-link "https://example.com/job" \
  --location "City, State" \
  --source "Ashby" \
  --referral "No" \
  --date-added "YYYY-MM-DD" \
  --resume-folder "/absolute/path/to/companies/Company Name/Candidate_Name_Resume" \
  --resume-pdf "/absolute/path/to/companies/Company Name/Candidate_Name_Resume/Candidate_Name_Company_Name.pdf" \
  --status "Resume Tailored"
```

If a Notion integration token is available, you can sync the matching Notion row in the same step:

```bash
python3 skills/resume-tailor/scripts/update_application_tracker.py \
  --company "Company Name" \
  --role "Role Title" \
  --job-link "https://example.com/job" \
  --location "City, State" \
  --source "Ashby" \
  --referral "No" \
  --date-added "YYYY-MM-DD" \
  --resume-folder "/absolute/path/to/companies/Company Name/Candidate_Name_Resume" \
  --resume-pdf "/absolute/path/to/companies/Company Name/Candidate_Name_Resume/Candidate_Name_Company_Name.pdf" \
  --status "Resume Tailored" \
  --sync-notion \
  --update-notion-title
```

This requires a Notion internal integration token in `NOTION_TOKEN` and access to the configured tracker database.

The tracker also supports a configurable fit score and recruiter outreach flag:

- preferences live in `application-trackers/scoring-profile.json`
- `Fit Score` is a 1 to 10 heuristic based on role, location, company, source, and current status
- `Reach Out` should default to `Yes` when the score is at or above the configured threshold
- use `--fit-score` or `--reach-out` only when you need to override the defaults for a specific role

To backfill or recompute those values across the full tracker, run:

```bash
python3 skills/resume-tailor/scripts/score_application_tracker.py
```

If you also want to sync those recomputed values into Notion, run:

```bash
python3 skills/resume-tailor/scripts/score_application_tracker.py \
  --sync-notion \
  --update-notion-title
```

Or, if markdown is already correct and you only want to push scores to Notion:

```bash
python3 skills/resume-tailor/scripts/sync_notion_scores.py \
  --update-title
```

Use the tracker every time the user provides a new role link so the repository keeps a single running application log.
If the user mentions a referral, record it in the `Referral` column. If they do not mention one, leave it blank or mark `No` based on the user's preference.
Treat the posting itself as the unique identity of the application. Multiple roles at the same company should create separate folder paths and separate tracker rows, even when the titles are similar.
Use status values such as `Resume Tailored`, `Applied`, `Online Assessment`, `Interviewing`, `Offer`, `Rejected`, and `Archived` when they fit the user's application stage.
Keep the markdown tracker header count in sync so `application-trackers/applications.md` shows `Total applications tracked: N` above the table.
If the resulting row has `Reach Out` enabled and the user wants outbound networking, hand off to the `linkedin-outreach` skill next so recruiter and engineer outreach gets tracked in the same markdown row.

If the user wants Notion tracking too, create or update a Notion database with a clean table-oriented schema:

- `Company` as the title property
- `Role` as rich text
- `Posting Key` as rich text
- `Date Added` as date
- `Status` as a status property
- `Applied` as checkbox
- `Referral` as checkbox
- `Referral Name` as rich text
- `Location` as rich text
- `Source` as a select property
- `Job Link` as URL
- `Resume PDF` as URL
- `Notes` as rich text

Prefer a simple polished table view with:

- rows sorted by `Date Added` descending
- the running total visible in the database title or primary table view name, such as `Applications (12)`
- `Applied` shown as a checkbox for quick green-check scanning
- `Referral` shown as a checkbox for quick scanning
- `Status`, `Company`, `Role`, `Location`, `Source`, `Applied`, `Referral`, `Job Link`, and `Resume PDF` visible

When the repo already contains `application-trackers/notion-config.md`, prefer updating that configured database instead of creating a new one.

## Tailoring rules

Keep the resume truthful. Optimize framing, ordering, emphasis, and brevity. Do not invent tools, impact, titles, or employers.

Primary edits:

1. Reorder the skills section so the most relevant skills appear first
2. Remove weak or irrelevant skills that dilute the match
3. Add already-true skills that exist elsewhere in the resume or user-provided context if they improve alignment
4. Rewrite bullets to foreground matching technologies, outcomes, scope, and ownership
5. Drop or compress older or less relevant roles if needed to stay within one page
6. Preserve measurable impact whenever possible
7. Keep the final tailored result to one page after LaTeX render
8. Use the full page effectively when strong truthful content fits; avoid leaving obvious empty space in the final one-page layout
9. Keep the bullet-based layout; do not replace experience bullets with paragraph blocks
10. Allow two-line bullets when they improve clarity, but do not force bullets to fill space unnecessarily
11. Keep the skills section visually substantial so it never looks sparse or underfilled
12. Preserve a compact header with the personal website `liamvan.dev` and no blank-looking contact rows
13. Default tailored role labels to `Software Engineer` unless the user explicitly wants the original internship wording
14. Avoid bullets that wrap with only one or two low-information trailing words on the second line; rewrite those bullets so wrapped lines carry meaningful content

## Skill alignment workflow

Before editing the skills section, build a quick alignment map with four buckets:

1. Required or highly repeated skills from the job posting
2. Skills already listed in the resume
3. Missing-but-true skills implied by bullets, projects, or technologies named elsewhere in the resume
4. Low-value or irrelevant skills that should be removed or demoted

Use that map to drive edits instead of only reordering the existing list.

## Rules for adding or removing skills

- Add a skill if the resume wording clearly supports it, even if the current skills section does not list it
- Infer missing-but-true skills from tools, frameworks, cloud platforms, testing systems, languages, and product areas mentioned in bullets or project lines
- If a bullet says the candidate built APIs with Spring Boot, it is valid to surface `REST APIs` and `Spring Boot` in the skills section
- If a bullet says the candidate used Robot Framework, OpenSearch, OCI, GCP, React, NestJS, Android, Selenium, or Azure DevOps, those can be promoted into skills when relevant
- Do not add a skill unless the resume already provides evidence for it
- Remove or de-emphasize generic skills that do not improve match quality for the target job
- Remove older, weaker, or redundant items when they crowd out better evidence
- Prefer fewer, stronger, more targeted skills over long catch-all lists
- When a role strongly implies a skill but the wording is weak, tighten the bullet language so the evidence is clearer before adding that skill

## Editing workflow

1. Read the job description and extract the top priorities.
2. Inspect the generic LaTeX resume in `generic-resume/`, usually `generic-resume/resume.tex`.
3. Read `generic-resume/README.md` in full and use it as the richer profile, evidence bank, and wording guide.
4. Use `candidate_name` from `generic-resume/README.md` for output naming.
5. Create the company-specific copy with `prepare_resume_folder.py`.
6. Edit the copied LaTeX files in the company-specific folder, not the generic source.
7. Build a skill alignment map:
   - top skills from the posting
   - skills already listed
   - missing-but-true skills found in bullets and projects
   - stronger evidence and wording available in `generic-resume/README.md`
   - skills to remove or demote
8. Make targeted changes:
   - skills ordering
   - adding missing-but-true skills
   - removing weak or irrelevant skills
   - pulling stronger evidence from `generic-resume/README.md`
   - rephrasing bullets with more specific truthful wording from `generic-resume/README.md`
   - summary wording if the template has one
   - bullet emphasis
   - removal of lower-value lines or roles
   - preserve readability over over-compression, even if that means a few bullets wrap to a second line
   - inspect wrapped bullets and rewrite any that leave an orphaned trailing word or tiny fragment on the next line
9. Check for one-page risk. If the resume is too long:
   - remove least relevant bullets first
   - shorten wording second
   - remove an older role only if necessary
   - before cutting information, try rewriting awkwardly wrapping bullets so the line break is cleaner
10. If the resume fits comfortably under one page with visible unused space:
   - add stronger truthful detail from the generic context before considering layout-only expansion
   - prefer strengthening bullets, skills, or a relevant project line over leaving the page underfilled
   - keep the final rendered PDF to exactly one page
11. Render the final PDF with `render_resume_pdf.py`.
12. Update `application-trackers/applications.md` with the new role, posting key, link, resume folder, PDF path, source, referral status, and current status.
    - Include a company-and-role labeled PDF link so the tracker can open the tailored resume directly from the table.
    - Keep the markdown tracker ordered for fast scanning: `Company`, `Role`, `Applied`, `Status`, `Company Resume`, `Referral`, then supporting details.
    - Refresh the header count so the markdown tracker shows the current total number of tracked applications.
13. If the user has requested Notion tracking and has provided or already has a parent page for it, create or update the matching Notion tracker row as well.
    - Refresh the Notion database title or primary table view name so the visible count stays current there too.
14. Summarize what changed and why, including which skills were added, removed, promoted, or rewritten using stronger profile evidence.

## Prioritization heuristics

Bias toward:

- Keywords repeated in required qualifications
- Tools that appear in both requirements and responsibilities
- Skills tied to business outcomes, ownership, and cross-functional execution
- Recent experience over older experience
- Matching domain language such as AI, SaaS, data, platform, security, fintech, healthcare, or consumer
- Skills that are clearly evidenced in bullets even if they are missing from the current skills section
- Stronger supporting detail from `generic-resume/README.md` when the one-page resume is too compressed to show the best phrasing

De-prioritize:

- Generic skills that take space without improving relevance
- Older technologies unless the job explicitly asks for them
- Bullets that describe tasks without outcomes
- Experience that competes with the target narrative
- Skills with no clear evidence in the resume

## Output expectations

The final deliverable should usually include:

1. Updated LaTeX resume files in the company-specific directory
2. A final PDF named `<Candidate_Name>_<Company_Name>.pdf` in that same directory when local LaTeX tooling exists
3. When requested, a basic `cover_letter.tex` and `<Candidate_Name>_<Company_Name>_Cover_Letter.pdf` in that same directory
4. An updated row in `application-trackers/applications.md`
5. When requested and configured, a matching Notion tracker entry
6. A brief summary of changes made
7. Any notes about missing evidence for requested skills

If local LaTeX tooling is missing, leave the LaTeX ready for Overleaf upload and note the intended PDF filename.

## Overleaf note

Direct Overleaf upload is not built into this skill. If the user has connected the project to Git, you can push the tailored LaTeX to that Git remote. Otherwise, prepare the company-specific LaTeX folder so it can be uploaded to Overleaf manually.
