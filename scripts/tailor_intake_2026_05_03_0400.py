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
        "company": "PhysicsX",
        "role": "Forward Deployed Software Engineer",
        "location": "New York, United States",
        "url": "https://job-boards.greenhouse.io/physicsx/jobs/4644850101",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "10",
        "posting_key": "4644850101",
        "focus": "forward-deployed AI applications, simulation software, customer-facing engineering, Python and TypeScript product systems, backend APIs, and production validation",
    },
    {
        "company": "Invisible Technologies",
        "role": "Software Engineer - Forward Deployed",
        "location": "New York - Hybrid; San Francisco Bay Area - Hybrid; Washington DC-Baltimore - Hybrid",
        "url": "https://job-boards.greenhouse.io/invisibletech/jobs/4697599101",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "10",
        "posting_key": "4697599101",
        "focus": "forward-deployed AI workflows, backend systems, customer-facing delivery, cloud operations, LLM tooling, and production reliability",
    },
    {
        "company": "Forge Global",
        "role": "Software Engineer II, Marketplace Middleware Engineering",
        "location": "New York, New York, United States",
        "url": "https://job-boards.greenhouse.io/forgeglobal/jobs/5971240004",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "5971240004",
        "focus": "fintech marketplace middleware, backend APIs, SQL data workflows, server-side delivery, CI/CD, reliability, and financial-services product execution",
    },
    {
        "company": "Flex",
        "role": "Software Engineer II, Frontend, Mobile and Web",
        "location": "New York, New York, United States; Remote (U.S.); San Francisco, California, United States",
        "url": "https://job-boards.greenhouse.io/flex/jobs/4642708005?gh_jid=4642708005",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "posting_key": "4642708005",
        "focus": "frontend and mobile-web fintech product engineering, React/NestJS surfaces, backend integrations, customer-facing reliability, and cross-functional delivery",
    },
    {
        "company": "Fanatics Betting & Gaming",
        "role": "Software Engineer II",
        "location": "New York, NY, United States",
        "url": "https://job-boards.greenhouse.io/fanaticsfbg/jobs/4209810009",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "4209810009",
        "focus": "backend sports-platform services, data handling, real-time operational tooling, API reliability, testing, and production support",
    },
    {
        "company": "Fanatics Betting & Gaming",
        "role": "Software Engineer II, iCasino - US",
        "location": "New York, NY, United States",
        "url": "https://job-boards.greenhouse.io/fanaticsfbg/jobs/4209984009",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "4209984009",
        "focus": "fault-tolerant gaming platform services, backend integrations, high-volume transaction workflows, API validation, and production reliability",
    },
    {
        "company": "Civis Analytics",
        "role": "Applied Software Engineer II",
        "location": "Chicago, IL (Remote); eligible states include New York, DC, Texas, Virginia, Washington",
        "url": "https://job-boards.greenhouse.io/civisanalytics/jobs/7392088",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "10",
        "posting_key": "7392088",
        "focus": "applied data software, mission-driven product workflows, Python/Java backend systems, analytics tooling, APIs, and cross-functional delivery",
    },
    {
        "company": "OpenAI",
        "role": "Forward Deployed Software Engineer - NYC",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/forward-deployed-software-engineer-nyc-at-openai-4349516535",
        "source": "LinkedIn",
        "kind": "ai",
        "fit": "9",
        "posting_key": "forward-deployed-software-engineer-nyc-at-openai-4349516535",
        "focus": "forward-deployed OpenAI API solutions, full-stack prototypes, customer-facing technical delivery, LLM product systems, and production-quality abstractions",
    },
]


def update_intake_status(company: str, role: str, status: str, posting_key: str, note: str) -> None:
    path = ROOT / "application-trackers" / "job-intake.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = []
    for line in lines:
        if not line.startswith("| "):
            updated.append(line)
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 12 and cells[1] == company and cells[2] == role:
            cells[9] = status
            cells[10] = note
            cells[11] = posting_key
            line = "| " + " | ".join(cell.replace("|", "\\|") for cell in cells[:12]) + " |"
        updated.append(line)
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


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
                "Hourly intake 2026-05-02/03 pass; tailored SWE resume rendered and verified one page; "
                f"emphasized {job['focus']}. Browser-based submission was blocked because Computer Use access "
                "to Chrome and Firefox was denied during this automation run."
            ),
        )
        update_intake_status(
            job["company"],
            job["role"],
            "Tailored",
            job["posting_key"],
            f"Tailored 2026-05-02; resume rendered and verified one page; emphasized {job['focus']}",
        )
        print(f"{job['company']} | {job['role']} | {pdf}")


if __name__ == "__main__":
    main()
