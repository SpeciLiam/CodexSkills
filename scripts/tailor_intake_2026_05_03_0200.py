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
        "company": "StubHub",
        "role": "Software Engineer II - Fulfillment",
        "location": "New York, New York, United States or Santa Monica, CA",
        "url": "https://job-boards.greenhouse.io/stubhubinc/jobs/4740072101",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "4740072101",
        "focus": "NYC fulfillment systems, post-purchase reliability, partner integrations, observability, backend APIs, and customer-facing product quality",
    },
    {
        "company": "StubHub",
        "role": "Software Engineer II - Platform Runtime & Services",
        "location": "New York, New York, United States",
        "url": "https://job-boards.greenhouse.io/stubhubinc/jobs/4683779101",
        "source": "Greenhouse",
        "kind": "platform",
        "fit": "10",
        "posting_key": "4683779101",
        "focus": "NYC platform runtime services, shared SDKs and tools, distributed systems, reliability, APIs, and developer workflow support",
    },
    {
        "company": "Ounce of Care",
        "role": "Software Engineer",
        "location": "New York, New York, United States",
        "url": "https://job-boards.greenhouse.io/ounceofcare/jobs/5091148007",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "posting_key": "5091148007",
        "focus": "NYC full-stack community-health product engineering, data and platform workflows, customer-facing reporting, automation, and stakeholder collaboration",
    },
    {
        "company": "Flex",
        "role": "Software Engineer II, Backend",
        "location": "Remote (U.S.)",
        "url": "https://job-boards.greenhouse.io/flex/jobs/4652834005?gh_src=Nfeutp",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "4652834005",
        "focus": "backend fintech systems, consumer and partner integrations, core platform services, API reliability, data validation, and product delivery",
    },
    {
        "company": "Aflac",
        "role": "Software Engineer I",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-i-at-aflac-4337203348",
        "source": "LinkedIn",
        "kind": "backend",
        "fit": "10",
        "posting_key": "software-engineer-i-at-aflac-4337203348",
        "focus": "early-career New York software engineering, backend services, API validation, production support, testing, and cross-team delivery",
    },
    {
        "company": "adMarketplace",
        "role": "Software Engineer II, Data",
        "location": "New York, New York, United States",
        "url": "https://job-boards.greenhouse.io/admarketplaceinc/jobs/4596931005?gh_src=9e9e08775us",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "4596931005",
        "focus": "NYC data-intensive backend systems, low-latency APIs, distributed services, search and advertising workflows, validation, and reliability",
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
            line = "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"
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
