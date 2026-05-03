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
        "company": "Yext",
        "role": "Software Engineer",
        "location": "New York, NY",
        "url": "https://job-boards.greenhouse.io/yext/jobs/7085149",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "7085149",
        "focus": "NYC product engineering, AI-search platform services, backend APIs, data workflows, and production reliability",
    },
    {
        "company": "TEGNA Inc.",
        "role": "Software Engineer",
        "location": "New York, New York",
        "url": "https://job-boards.greenhouse.io/tegnainc/jobs/4744576007?gh_jid=4744576007",
        "source": "Greenhouse",
        "kind": "backend",
        "fit": "10",
        "posting_key": "4744576007",
        "focus": "real-time software systems, microservices, Java/Python/Go-adjacent backend delivery, event-driven workflows, and reliability",
    },
    {
        "company": "NinjaTrader",
        "role": "Software Engineer III (Fullstack)",
        "location": "Chicago; remote flexibility includes New York, California, Washington, DC, and other US states",
        "url": "https://job-boards.greenhouse.io/ninjatrader/jobs/4535655006",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "8",
        "posting_key": "4535655006",
        "focus": "full-stack fintech product systems, APIs, testing, operational reliability, and cross-functional delivery",
    },
    {
        "company": "Fortune",
        "role": "Full Stack Software Engineer Next.js",
        "location": "New York, NY 10038",
        "url": "https://job-boards.greenhouse.io/fortune/jobs/5424161004",
        "source": "Greenhouse",
        "kind": "fullstack",
        "fit": "10",
        "posting_key": "5424161004",
        "focus": "NYC full-stack media products, TypeScript/React surfaces, REST APIs, CMS-adjacent systems, and production web reliability",
    },
    {
        "company": "Meltwater",
        "role": "Software Engineer - Machine Learning",
        "location": "New York, NY",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-machine-learning-at-meltwater-4377382456",
        "source": "LinkedIn",
        "kind": "ai",
        "fit": "9",
        "posting_key": "software-engineer-machine-learning-at-meltwater-4377382456",
        "focus": "NYC machine-learning software, AI product workflows, Python services, data-backed search/recommendation systems, and validation",
    },
    {
        "company": "Sift",
        "role": "Software Engineer, Full Stack",
        "location": "San Francisco, CA",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-full-stack-at-sift-4253102305",
        "source": "LinkedIn",
        "kind": "fullstack",
        "fit": "8",
        "posting_key": "software-engineer-full-stack-at-sift-4253102305",
        "focus": "full-stack observability systems, telemetry products, startup ownership, backend APIs, React product surfaces, and reliability",
    },
    {
        "company": "Salient",
        "role": "Forward Deployed Software Engineer",
        "location": "San Francisco, CA",
        "url": "https://www.linkedin.com/jobs/view/forward-deployed-software-engineer-at-salient-4337004844",
        "source": "LinkedIn",
        "kind": "ai",
        "fit": "8",
        "posting_key": "forward-deployed-software-engineer-at-salient-4337004844",
        "focus": "forward-deployed AI fintech systems, customer-facing engineering, APIs, production validation, and fast product iteration",
    },
    {
        "company": "HDR",
        "role": "Software Engineer",
        "location": "San Francisco, CA",
        "url": "https://www.linkedin.com/jobs/view/software-engineer-at-hdr-4389318555",
        "source": "LinkedIn",
        "kind": "fullstack",
        "fit": "8",
        "posting_key": "software-engineer-at-hdr-4389318555",
        "focus": "general software engineering, full-stack implementation, backend services, testing, and production support",
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
                f"emphasized {job['focus']}. Browser-based submission was not attempted because Computer Use access "
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
        "Apple",
        "Software Engineer - Early Career (Backend/Data)",
        "Manual",
        "",
        "Manual review needed 2026-05-02: degraded LinkedIn capture exposed only the public search page, not the exact posting URL",
    )


if __name__ == "__main__":
    main()
