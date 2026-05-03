#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATE_ADDED = "2026-05-03"

spec = importlib.util.spec_from_file_location("tailor_greenhouse_batch6", ROOT / "scripts" / "tailor_greenhouse_batch6.py")
batch = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(batch)

JOBS = [
    {
        "company": "StubHub",
        "role": "Software Engineer I - Marketplace Operations (New Grad)",
        "location": "New York, New York, United States",
        "url": "https://job-boards.greenhouse.io/stubhubinc/jobs/4763976101",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "posting_key": "4763976101",
        "focus": "new-grad marketplace operations, customer-facing ticketing workflows, full-stack systems, AI-assisted development, production reliability, and testing",
    },
    {
        "company": "Pallet",
        "role": "Forward Deployed Software Engineer (AI Agents)",
        "location": "New York City",
        "url": "https://job-boards.greenhouse.io/pallet/jobs/5072543007",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "10",
        "posting_key": "5072543007",
        "focus": "forward-deployed AI agents, logistics workflows, customer-facing engineering, backend APIs, full-stack delivery, and production validation",
    },
    {
        "company": "Clear Street",
        "role": "Backend Software Engineer - Reference Data Services",
        "location": "New York, NY",
        "url": "https://job-boards.greenhouse.io/clearstreet/jobs/6675504",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "6675504",
        "focus": "backend financial data services, authoritative datasets, API reliability, data modeling, cloud validation, and production operations",
    },
    {
        "company": "Addepar",
        "role": "Backend Software Engineer - Investor Solutions",
        "location": "New York, NY",
        "url": "https://job-boards.greenhouse.io/addepar1/jobs/8387694002",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "8387694002",
        "focus": "backend investor-solutions systems, financial data workflows, API services, platform reliability, data validation, and cross-functional delivery",
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
    update_intake_status(
        "Loop",
        "2026 New Grad | Software Engineer, Full-Stack (New York)",
        "Skipped",
        "",
        "Skipped 2026-05-03: exact Greenhouse page appears duplicative of already-applied Loop New York new-grad/full-stack rows",
    )
    update_intake_status(
        "Rokt",
        "Junior Software Engineer",
        "Manual",
        "",
        "Manual review needed 2026-05-03: degraded LinkedIn capture exposed only the public entry-level search page, not the exact posting URL",
    )

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
                "Hourly intake 2026-05-03 degraded public-search pass; tailored SWE resume rendered and verified one page; "
                f"emphasized {job['focus']}. Browser-based submission was blocked because Computer Use access "
                "to Chrome and Firefox was denied during this automation run."
            ),
        )
        update_intake_status(
            job["company"],
            job["role"],
            "Tailored",
            job["posting_key"],
            f"Tailored 2026-05-03; resume rendered and verified one page; emphasized {job['focus']}",
        )
        print(f"{job['company']} | {job['role']} | {pdf}")


if __name__ == "__main__":
    main()
