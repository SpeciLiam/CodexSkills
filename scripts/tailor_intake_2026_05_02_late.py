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
        "company": "Opto Investments",
        "role": "Software Engineer, Backend",
        "location": "New York, New York, United States; San Francisco, California, United States",
        "url": "https://job-boards.greenhouse.io/optoinvest/jobs/7646858003",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "focus": "backend financial technology systems, API delivery, data modeling, cloud validation, and production reliability",
    },
    {
        "company": "Checkr",
        "role": "Backend Software Engineer II",
        "location": "Denver, Colorado, United States; San Francisco, California, United States",
        "url": "https://job-boards.greenhouse.io/checkr/jobs/7438937",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "focus": "backend services, Ruby/JavaScript-adjacent API delivery, SQL and NoSQL data workflows, async systems, and reliability",
    },
    {
        "company": "Tebra",
        "role": "Software Engineer III",
        "location": "United States - Remote",
        "url": "https://job-boards.greenhouse.io/tebra/jobs/4679086005",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "9",
        "focus": "remote healthcare software engineering, subsystem ownership, backend APIs, operational quality, and production support",
    },
    {
        "company": "Runpod",
        "role": "Software Engineer (Full-Stack)",
        "location": "Remote, USA",
        "url": "https://job-boards.greenhouse.io/runpod/jobs/4785681008",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "9",
        "focus": "AI infrastructure, Python and TypeScript product systems, APIs, cloud validation, and full-stack delivery",
    },
    {
        "company": "Canopy Connect",
        "role": "Backend Engineer - Carrier Integrations Team (Remote)",
        "location": "Remote (USA & Canada)",
        "url": "https://job-boards.greenhouse.io/canopyconnect/jobs/4076674004",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "9",
        "focus": "backend integration systems, third-party APIs, data aggregation, Node-adjacent service design, AWS reliability, and startup delivery",
    },
    {
        "company": "Verkada",
        "role": "Software Engineer - Computer Vision",
        "location": "San Mateo, CA United States",
        "url": "https://job-boards.greenhouse.io/verkada/jobs/4128624007",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "9",
        "focus": "applied computer vision, AI-adjacent product systems, scalable backend validation, cloud operations, and production reliability",
    },
    {
        "company": "Neuralink",
        "role": "Software Engineer, Implant Manufacturing",
        "location": "Austin, Texas, United States",
        "url": "https://job-boards.greenhouse.io/neuralink/jobs/6353417003",
        "source": "Greenhouse",
        "kind": "platform",
        "fit": "9",
        "focus": "manufacturing software, validation infrastructure, backend services, operational debugging, and hardware-adjacent product delivery",
    },
    {
        "company": "Agentio",
        "role": "Software Engineer",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-at-agentio-4400957231",
        "source": "LinkedIn",
        "kind": "fullstack",
        "fit": "9",
        "focus": "NYC startup product engineering, full-stack delivery, backend APIs, data workflows, customer-facing iteration, and ownership",
    },
    {
        "company": "Sesame",
        "role": "Software Engineer",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-at-sesame-4403118222",
        "source": "LinkedIn",
        "kind": "ai",
        "fit": "9",
        "focus": "voice-agent backend systems, low-latency product infrastructure, AI workflows, API reliability, and production validation",
    },
    {
        "company": "Meta",
        "role": "Software Engineer, AI Native",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-ai-native-at-meta-4376617463",
        "source": "LinkedIn",
        "kind": "ai",
        "fit": "9",
        "focus": "AI-native product engineering, LLM applications, experimentation, backend APIs, quality validation, and cross-platform delivery",
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
                "Hourly intake 2026-05-02 late pass; tailored SWE resume rendered and verified one page; "
                f"emphasized {job['focus']}. Browser-based submission was not attempted because Computer Use access "
                "to Chrome and Firefox was denied during this automation run."
            ),
        )
        print(f"{job['company']} | {job['role']} | {pdf}")


if __name__ == "__main__":
    main()
