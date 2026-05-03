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
        "company": "S&P Global",
        "role": "Software Engineer II",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-ii-at-s-p-global-4402306070",
        "source": "LinkedIn",
        "kind": "ai",
        "fit": "10",
        "posting_key": "software-engineer-ii-at-s-p-global-4402306070",
        "focus": "Kensho AI product engineering, generative AI agents, data retrieval APIs, NLP workflows, production reliability, and backend validation",
    },
    {
        "company": "Brex",
        "role": "Software Engineer II, Product",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-ii-product-at-brex-4341255828",
        "source": "LinkedIn",
        "kind": "fullstack",
        "fit": "10",
        "posting_key": "software-engineer-ii-product-at-brex-4341255828",
        "focus": "NYC product engineering for financial workflows, full-stack delivery, backend APIs, React surfaces, reliability, and cross-functional execution",
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
