---
name: resume-tailor
description: Tailor a one-page resume from a generic Overleaf LaTeX resume using a job description URL or pasted posting. Use when the user wants to reorder skills, trim irrelevant content, strengthen bullets, remove weaker roles, and create a company-specific resume folder while keeping the output truthful and concise.
---

# Resume Tailor

Use this skill when a user wants to adapt the generic resume to a specific job posting.

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
- Company outputs live in `companies/<Company Name>/<Candidate_Name>_Resume/`
- If that folder already exists, create `companies/<Company Name>/<Candidate_Name>_Resume_2`, then `_3`, and so on

Before editing, prepare the output directory with:

```bash
python3 skills/resume-tailor/scripts/prepare_resume_folder.py \
  --company "Company Name"
```

This copies the generic resume files into the correct company-specific folder and prints the destination path.

After editing, render a final PDF in the same folder with:

```bash
python3 skills/resume-tailor/scripts/render_resume_pdf.py \
  --dir "companies/Company Name/Candidate_Name_Resume"
```

This attempts to compile `resume.tex` and writes a final PDF named `<Candidate_Name>_<Company_Name>.pdf` in that same company-specific folder.

## Tailoring rules

Keep the resume truthful. Optimize framing, ordering, emphasis, and brevity. Do not invent tools, impact, titles, or employers.

Primary edits:

1. Reorder the skills section so the most relevant skills appear first
2. Remove weak or irrelevant skills that dilute the match
3. Add already-true skills that exist elsewhere in the resume or user-provided context if they improve alignment
4. Rewrite bullets to foreground matching technologies, outcomes, scope, and ownership
5. Drop or compress older or less relevant roles if needed to stay within one page
6. Preserve measurable impact whenever possible
7. Keep the final result to one page after LaTeX render

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
3. Read `generic-resume/README.md` and use `candidate_name` for output naming.
4. Create the company-specific copy with `prepare_resume_folder.py`.
5. Edit the copied LaTeX files in the company-specific folder, not the generic source.
6. Build a skill alignment map:
   - top skills from the posting
   - skills already listed
   - missing-but-true skills found in bullets and projects
   - skills to remove or demote
7. Make targeted changes:
   - skills ordering
   - adding missing-but-true skills
   - removing weak or irrelevant skills
   - summary wording if the template has one
   - bullet emphasis
   - removal of lower-value lines or roles
8. Check for one-page risk. If the resume is too long:
   - remove least relevant bullets first
   - shorten wording second
   - remove an older role only if necessary
9. Render the final PDF with `render_resume_pdf.py`.
10. Summarize what changed and why, including which skills were added, removed, or promoted.

## Prioritization heuristics

Bias toward:

- Keywords repeated in required qualifications
- Tools that appear in both requirements and responsibilities
- Skills tied to business outcomes, ownership, and cross-functional execution
- Recent experience over older experience
- Matching domain language such as AI, SaaS, data, platform, security, fintech, healthcare, or consumer
- Skills that are clearly evidenced in bullets even if they are missing from the current skills section

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
3. A brief summary of changes made
4. Any notes about missing evidence for requested skills

If local LaTeX tooling is missing, leave the LaTeX ready for Overleaf upload and note the intended PDF filename.

## Overleaf note

Direct Overleaf upload is not built into this skill. If the user has connected the project to Git, you can push the tailored LaTeX to that Git remote. Otherwise, prepare the company-specific LaTeX folder so it can be uploaded to Overleaf manually.
