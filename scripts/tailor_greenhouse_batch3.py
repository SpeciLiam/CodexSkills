#!/usr/bin/env python3

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATE_ADDED = "2026-05-01"

BASE_SKILLS = {
    "fullstack": r"""     \textbf{Languages}{: Java, TypeScript, JavaScript, Python, SQL, C\#, C++, PHP, C} \\
     \textbf{Backend / Cloud}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, AWS, GCP, OCI, microservices} \\
     \textbf{Frontend / Product}{: React, NestJS, Angular, Node.js, product integrations, technical documentation} \\
     \textbf{Testing / Operations}{: CI/CD, Robot Framework, Selenium, Grafana, Azure DevOps, release support, on-call response} \\""",
    "backend": r"""     \textbf{Languages}{: Java, Python, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{Backend / APIs}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, distributed caching, data modeling} \\
     \textbf{Cloud / Reliability}{: AWS, GCP, OCI, CI/CD, Grafana, T2, canary validation, release support, on-call response} \\
     \textbf{Frontend / Product}{: React, NestJS, Angular, Node.js, technical documentation, cross-team product delivery} \\""",
    "platform": r"""     \textbf{Languages}{: Java, Python, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{Platform / APIs}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, distributed systems, data modeling} \\
     \textbf{Cloud / Reliability}{: AWS, GCP, OCI, CI/CD, Grafana, T2, canary validation, release support, on-call response} \\
     \textbf{Product / Tooling}{: React, NestJS, Angular, Node.js, technical documentation, developer workflows} \\""",
    "dotnet": r"""     \textbf{Languages}{: C\#, Java, TypeScript, JavaScript, Python, SQL, C++, PHP, C} \\
     \textbf{Backend / APIs}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, distributed caching, data modeling} \\
     \textbf{Cloud / Reliability}{: AWS, GCP, OCI, CI/CD, Grafana, T2, canary validation, release support, on-call response} \\
     \textbf{Frontend / Product}{: React, NestJS, Angular, Node.js, technical documentation, cross-team delivery} \\""",
}

ROLE_BULLETS = {
    "fullstack": [
        "Drove GA readiness for OCI database services on GCP by validating API, CLI, console, backup, restore, and Data Guard workflows across partner-owned product surfaces",
        "Built reusable GCloud and OCI scripting workflows plus regression utilities, improving local validation and scaling end-to-end coverage for BaseDB and ADBS releases",
        "Implemented Exascale Storage Vault dry-run support, improving preflight validation and reaching over 90\\% unit test coverage across BaseDB and Exadata Infrastructure components",
    ],
    "backend": [
        "Drove GA readiness for BaseDB and Exadata DB workflows on GCP, validating API-driven create, restore, backup, and Data Guard scenarios across distributed service boundaries",
        "Built reusable GCloud and OCI scripting workflows plus performance and regression utilities, improving local testing efficiency for backend release validation",
        "Implemented Exascale Storage Vault dry-run support, improving preflight validation and reaching over 90\\% unit test coverage across BaseDB and Exadata Infrastructure components",
    ],
    "platform": [
        "Drove GA readiness for OCI database services on GCP, validating cloud workflows across API, CLI, console, backup, restore, and Data Guard paths",
        "Served as primary on-call for Oasis releases, leading Sev2 investigations and resolving Sev3 and Sev4 issues through log analysis, Grafana, T2 metrics, and alarm tuning",
        "Built reusable GCloud and OCI automation plus regression utilities, improving release validation for BaseDB, ADBS, and Exadata workflows",
    ],
    "dotnet": [
        "Built production-facing Oracle University search and recommendation features across React and NestJS surfaces, integrating OpenSearch retrieval with PHP and SQL metadata pipelines",
        "Drove GA readiness for BaseDB and Exadata DB workflows by validating API-driven create, restore, backup, and Data Guard scenarios across distributed service boundaries",
        "Implemented Exascale Storage Vault dry-run support, improving preflight validation and reaching over 90\\% unit test coverage across BaseDB and Exadata Infrastructure components",
    ],
}

JOBS = [
    {
        "company": "Clarity Innovations",
        "role": "Software Engineer",
        "location": "Herndon, VA",
        "url": "https://job-boards.greenhouse.io/clarityinnovates/jobs/5125081007?gh_src=my.greenhouse.search",
        "kind": "backend",
        "fit": "8",
    },
    {
        "company": "Apptronik",
        "role": "Software Engineer - Platform",
        "location": "Austin, TX",
        "url": "https://boards.greenhouse.io/apptronik/jobs/5985625004?gh_jid=5985625004&gh_src=my.greenhouse.search",
        "kind": "platform",
        "fit": "8",
    },
    {
        "company": "Apptronik",
        "role": "Software Engineer - Controls Infrastructure",
        "location": "Austin, TX",
        "url": "https://boards.greenhouse.io/apptronik/jobs/5985982004?gh_jid=5985982004&gh_src=my.greenhouse.search",
        "kind": "platform",
        "fit": "7",
    },
    {
        "company": "Next Insurance",
        "role": "Backend Engineer - DevEx Team",
        "location": "Waltham, MA",
        "url": "https://job-boards.greenhouse.io/nextinsurance66/jobs/7719281003?gh_src=my.greenhouse.search",
        "kind": "backend",
        "fit": "8",
    },
    {
        "company": "xAI",
        "role": "Backend Engineer - API",
        "location": "Palo Alto, CA",
        "url": "https://job-boards.greenhouse.io/xai/jobs/5119111007?gh_src=my.greenhouse.search",
        "kind": "backend",
        "fit": "7",
    },
    {
        "company": "Divergent",
        "role": "Full Stack Software Engineer",
        "location": "Los Angeles, CA",
        "url": "https://job-boards.greenhouse.io/divergent/jobs/5207177008?gh_src=my.greenhouse.search",
        "kind": "fullstack",
        "fit": "8",
    },
    {
        "company": "Whop",
        "role": "Full Stack Engineer, Ad Networks",
        "location": "Palo Alto, CA",
        "url": "https://careers.whop.com/?gh_jid=5124207007&gh_src=my.greenhouse.search",
        "kind": "fullstack",
        "fit": "8",
    },
    {
        "company": "Formic",
        "role": "Full Stack Software Engineer - Robotics",
        "location": "San Francisco, CA; Oakland, CA",
        "url": "https://job-boards.greenhouse.io/formic/jobs/4677397006?gh_src=my.greenhouse.search",
        "kind": "fullstack",
        "fit": "8",
    },
    {
        "company": "Empower Pharmacy",
        "role": "Full Stack Developer",
        "location": "Remote - Houston, TX",
        "url": "https://job-boards.greenhouse.io/empowerpharmacy/jobs/4234731009?gh_src=my.greenhouse.search",
        "kind": "fullstack",
        "fit": "8",
    },
    {
        "company": "Revolutional, LLC",
        "role": "Full Stack .NET Developer",
        "location": "Arlington, VA; Baltimore, MD",
        "url": "https://revolutional.com/job-openings/?gh_jid=7720736003&gh_src=my.greenhouse.search",
        "kind": "dotnet",
        "fit": "7",
    },
]


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def tailor_tex(path: Path, kind: str) -> None:
    text = path.read_text()
    text = re.sub(
        r"     \\textbf\{Languages\}\{:[\s\S]*?     \\textbf\{Frontend / Product\}\{:[^\n]+\} \\\\\n",
        BASE_SKILLS[kind] + "\n",
        text,
    )

    bullets = ROLE_BULLETS[kind]
    text = re.sub(
        r"    \\resumeItem\{Drove GA readiness[\s\S]*?    \\resumeItem\{Built reusable GCloud[\s\S]*?\n    \\resumeItem\{Implemented and merged dry-run support[\s\S]*?\n",
        "".join(f"    \\resumeItem{{{bullet}}}\n" for bullet in bullets),
        text,
    )
    if kind in {"backend", "platform"}:
        text = text.replace(
            "Implemented the search interface in React and NestJS from Figma designs and stakeholder feedback, using PHP and SQL to retrieve metadata for product features and model inputs",
            "Implemented React and NestJS product surfaces from Figma designs, using PHP and SQL metadata pipelines to support search, recommendations, and model inputs",
        )
    elif kind == "dotnet":
        text = text.replace(
            "Built an LLM-powered recommendation experience for Oracle University and OCI learning content, helping customers discover tailored OCI information and course paths",
            "Built production-facing Oracle University search and recommendation features, integrating OpenSearch retrieval with React and NestJS product surfaces",
        )

    path.write_text(text)


def main() -> None:
    for job in JOBS:
        destination = run(
            "python3",
            "skills/resume-tailor/scripts/prepare_resume_folder.py",
            "--company",
            job["company"],
            "--role",
            job["role"],
        )
        folder = Path(destination.splitlines()[-1]).resolve()
        tex = folder / "resume.tex"
        tailor_tex(tex, job["kind"])

        run("python3", "skills/resume-tailor/scripts/render_resume_pdf.py", "--dir", str(folder))
        pdfs = sorted(folder.glob("Liam_Van_*.pdf"), key=lambda path: path.stat().st_mtime)
        pdf = pdfs[-1]
        run("python3", "skills/resume-tailor/scripts/verify_resume_pdf.py", "--pdf", str(pdf))

        run(
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
            "Greenhouse",
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
            "Sourced from MyGreenhouse 2026-05-01",
        )
        print(f"{job['company']} | {job['role']} | {pdf}")


if __name__ == "__main__":
    main()
