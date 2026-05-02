#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATE_ADDED = "2026-05-02"

spec = importlib.util.spec_from_file_location("tailor_greenhouse_batch6", ROOT / "scripts" / "tailor_greenhouse_batch6.py")
batch = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(batch)

JOBS = [
    {
        "company": "WithCoverage",
        "role": "Software Engineer",
        "location": "New York, NY",
        "url": "https://job-boards.greenhouse.io/withcoverage/jobs/4828873008",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "focus": "backend product systems, API delivery, data modeling, cloud validation, production reliability, and fast product iteration",
    },
    {
        "company": "Superblocks",
        "role": "Software Engineer, Cloud Infrastructure",
        "location": "New York, NY",
        "url": "https://job-boards.greenhouse.io/superblocks/jobs/4507226005",
        "source": "Greenhouse",
        "kind": "platform",
        "fit": "10",
        "focus": "cloud infrastructure, developer tooling, API reliability, distributed services, operational debugging, and platform validation",
    },
    {
        "company": "Nira Energy",
        "role": "Founding Software Engineer",
        "location": "New York, NY",
        "url": "https://job-boards.greenhouse.io/niraenergy/jobs/4824126008",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "focus": "founding full-stack product engineering, backend APIs, data workflows, customer-facing delivery, and rapid product iteration",
    },
    {
        "company": "Loop",
        "role": "2026 New Grad - Software Engineer, Full-Stack",
        "location": "San Francisco, CA",
        "url": "https://job-boards.greenhouse.io/loop/jobs/5780582004",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "focus": "new-grad full-stack engineering, AI logistics workflows, backend APIs, React product surfaces, data processing, and production validation",
    },
    {
        "company": "Flex",
        "role": "Software Engineer",
        "location": "New York City, NY",
        "url": "https://job-boards.greenhouse.io/flex/jobs/5633923004",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "focus": "financial technology systems, backend services, API workflows, data validation, reliability, and product collaboration",
    },
    {
        "company": "Vercel",
        "role": "Software Engineer, AI",
        "location": "Remote - United States",
        "url": "https://job-boards.greenhouse.io/vercel/jobs/5633379004",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "9",
        "focus": "AI product engineering, developer experience, LLM applications, TypeScript and Python systems, APIs, and production validation",
    },
    {
        "company": "Warner Bros. Discovery",
        "role": "Software Engineer II",
        "location": "Atlanta, GA",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-ii-at-warner-bros-discovery-4374141586",
        "source": "LinkedIn",
        "kind": "backend",
        "fit": "10",
        "focus": "software engineering II delivery, backend services, API reliability, cloud validation, testing, and cross-functional product execution",
    },
]


def main() -> None:
    for job in JOBS:
        destination = batch.run(
            "python3",
            "skills/resume-tailor/scripts/prepare_resume_folder.py",
            "--company",
            job["company"],
            "--role",
            job["role"],
        )
        folder = Path(destination.splitlines()[-1]).resolve()
        tex = folder / "resume.tex"
        batch.tailor_tex(tex, job["kind"])

        batch.run("python3", "skills/resume-tailor/scripts/render_resume_pdf.py", "--dir", str(folder))
        pdfs = sorted(folder.glob("Liam_Van_*.pdf"), key=lambda path: path.stat().st_mtime)
        pdf = pdfs[-1]
        batch.run("python3", "skills/resume-tailor/scripts/verify_resume_pdf.py", "--pdf", str(pdf))

        batch.run(
            "python3",
            "skills/resume-tailor/scripts/update_application_tracker.py",
            "--company",
            job["company"],
            "--role",
            job["role"],
            "--job-link",
            job["url"],
            "--location",
            job["location"],
            "--source",
            job["source"],
            "--referral",
            "No",
            "--date-added",
            DATE_ADDED,
            "--resume-folder",
            str(folder),
            "--resume-pdf",
            str(pdf),
            "--status",
            "Resume Tailored",
            "--fit-score",
            job["fit"],
            "--notes",
            (
                "Hourly intake 2026-05-02; tailored SWE resume rendered and verified one page; "
                f"emphasized {job['focus']}. Did not claim direct company-specific domain ownership or unlisted framework experience."
            ),
        )
        print(f"{job['company']} | {job['role']} | {pdf}")


if __name__ == "__main__":
    main()
