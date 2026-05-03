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
        "company": "Udio",
        "role": "Software Engineer (New Grad)",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-new-grad-at-udio-4377876604",
        "source": "LinkedIn",
        "kind": "ai",
        "fit": "10",
        "posting_key": "software-engineer-new-grad-at-udio-4377876604",
        "focus": "NYC new-grad AI product engineering, full-stack development, scalable application code, testing, and creative technology domain alignment",
    },
    {
        "company": "StubHub",
        "role": "Software Engineer II – Consumer Experience (Full-Stack)",
        "location": "New York, New York, United States",
        "url": "https://job-boards.eu.greenhouse.io/stubhubinc/jobs/4792613101",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "posting_key": "4792613101",
        "focus": "NYC full-stack consumer product engineering, high-traffic web and mobile surfaces, APIs, experimentation, reliability, and cross-functional delivery",
    },
    {
        "company": "StubHub",
        "role": "Software Engineer II - (Fullstack / Product Engineering)",
        "location": "New York, New York, United States",
        "url": "https://job-boards.eu.greenhouse.io/stubhubinc/jobs/4790893101",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "posting_key": "4790893101",
        "focus": "NYC full-stack product engineering, user-facing features, backend APIs, AI-assisted delivery, testing, and production reliability",
    },
    {
        "company": "Superblocks",
        "role": "Forward Deployed Engineer",
        "location": "New York, NY / Remote",
        "url": "https://job-boards.greenhouse.io/superblocks/jobs/4534781005",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "7",
        "posting_key": "4534781005",
        "focus": "forward-deployed AI builder workflows, Python and TypeScript integrations, API-driven internal tools, enterprise product feedback, and customer-facing engineering",
    },
    {
        "company": "Nira Energy",
        "role": "Forward Deployed Engineer",
        "location": "Remote or Hybrid - New York City, NY",
        "url": "https://job-boards.greenhouse.io/niraenergy/jobs/4964468008",
        "source": "Greenhouse",
        "kind": "ai",
        "fit": "7",
        "posting_key": "4964468008",
        "focus": "climate software, forward-deployed user workflows, production shipping, Python/TypeScript product systems, ambiguity, and fast customer validation",
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

    update_intake_status(
        "Giga",
        "Software Engineer (New Grads) - New York",
        "Skipped",
        "",
        "Skipped 2026-05-02: exact LinkedIn page appears duplicative of existing applied Giga New York / new-grad application rows",
    )
    update_intake_status(
        "Loop",
        "2026 New Grad | Software Engineer, Full-Stack (New York)",
        "Skipped",
        "",
        "Skipped 2026-05-02: exact Greenhouse page appears duplicative of already-applied Loop New York new-grad/full-stack rows",
    )


if __name__ == "__main__":
    main()
