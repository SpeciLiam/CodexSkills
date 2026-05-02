#!/usr/bin/env python3

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATE_ADDED = "2026-05-01"

BASE_SKILLS = {
    "backend": r"""     \textbf{Languages}{: Java, Python, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{Backend / APIs}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, distributed caching, data modeling} \\
     \textbf{Cloud / Reliability}{: AWS, GCP, OCI, CI/CD, Grafana, T2, canary validation, release support, on-call response} \\
     \textbf{Frontend / Product}{: React, NestJS, Angular, Node.js, technical documentation, cross-team product delivery} \\""",
    "platform": r"""     \textbf{Languages}{: Java, Python, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{Platform / APIs}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, distributed systems, data modeling} \\
     \textbf{Cloud / Reliability}{: AWS, GCP, OCI, CI/CD, Grafana, T2, canary validation, release support, on-call response} \\
     \textbf{Tooling / Product}{: React, NestJS, Angular, Node.js, technical documentation, developer workflows} \\""",
    "ai": r"""     \textbf{Languages}{: Python, Java, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{AI / Product}{: LLM applications, AI-assisted tooling, REST APIs, React, NestJS, OpenSearch, data workflows} \\
     \textbf{Backend / Cloud}{: Spring Boot, MySQL, Docker, AWS, GCP, OCI, distributed systems, production validation} \\
     \textbf{Testing / Operations}{: CI/CD, Robot Framework, Selenium, Grafana, Azure DevOps, release support, on-call response} \\""",
    "fullstack": r"""     \textbf{Languages}{: Java, TypeScript, JavaScript, Python, SQL, C\#, C++, PHP, C} \\
     \textbf{Backend / Cloud}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, AWS, GCP, OCI, microservices} \\
     \textbf{Frontend / Product}{: React, NestJS, Angular, Node.js, Figma-to-product implementation, product integrations} \\
     \textbf{Testing / Operations}{: CI/CD, Robot Framework, Selenium, Grafana, Azure DevOps, release support, on-call response} \\""",
}

ROLE_BULLETS = {
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
    "ai": [
        "Built an LLM-powered recommendation experience for Oracle University and OCI learning content, helping customers discover tailored OCI information and course paths",
        "Drove GA readiness for OCI database services on GCP by validating API, CLI, console, backup, restore, and Data Guard workflows across product surfaces",
        "Built reusable GCloud and OCI scripting workflows plus regression utilities, improving local validation and scaling end-to-end coverage for BaseDB and ADBS releases",
    ],
    "fullstack": [
        "Implemented React and NestJS product surfaces from Figma designs, using PHP and SQL metadata pipelines to support search, recommendations, and model inputs",
        "Drove GA readiness for OCI database services on GCP by validating API, CLI, console, backup, restore, and Data Guard workflows across partner-owned product surfaces",
        "Built reusable GCloud and OCI scripting workflows plus regression utilities, improving local validation and scaling end-to-end coverage for BaseDB and ADBS releases",
    ],
}

JOBS = [
    {
        "company": "AssetWatch",
        "role": "Backend Engineer",
        "location": "United States",
        "url": "https://job-boards.greenhouse.io/assetwatch/jobs/4658890005",
        "kind": "backend",
        "fit": "10",
        "focus": "backend data services, scalable APIs, serverless workflows, database operations, ingestion pipelines, and production reliability",
    },
    {
        "company": "Mattermost",
        "role": "Software Engineer II",
        "location": "United States",
        "url": "https://job-boards.greenhouse.io/mattermost/jobs/4821266008",
        "kind": "fullstack",
        "fit": "10",
        "focus": "secure collaboration products, React and backend delivery, workflow reliability, customer-focused execution, and open-source-style engineering",
    },
    {
        "company": "SupplyHouse.com",
        "role": "Backend Engineer",
        "location": "Remote, Remote, United States",
        "url": "https://job-boards.greenhouse.io/supplyhouse/jobs/5616318004",
        "kind": "backend",
        "fit": "10",
        "focus": "backend ecommerce systems, APIs, internal operations, full-stack collaboration, testing, and scalable service delivery",
    },
    {
        "company": "Genies",
        "role": "Backend Engineer",
        "location": "Los Angeles, California, United States; San Francisco, California, United States",
        "url": "https://job-boards.greenhouse.io/genies/jobs/7029957003",
        "kind": "ai",
        "fit": "9",
        "focus": "AI platform backend systems, scalable services, data workflows, API reliability, and cross-functional product execution",
    },
    {
        "company": "ngrok",
        "role": "Software Engineer II/III/Senior, Gateway",
        "location": "United States",
        "url": "https://job-boards.greenhouse.io/ngrokinc/jobs/5789584004",
        "kind": "platform",
        "fit": "9",
        "focus": "gateway infrastructure, API delivery, backend reliability, distributed systems, operational debugging, and developer-product workflows",
    },
    {
        "company": "Sumo Logic",
        "role": "Software Engineer II - Core Platform",
        "location": "United States",
        "url": "https://job-boards.greenhouse.io/sumologic/jobs/7485892",
        "kind": "platform",
        "fit": "10",
        "focus": "core platform services, scalable cloud microservices, on-call ownership, reliability, APIs, and distributed system validation",
    },
    {
        "company": "Lynx Analytics",
        "role": "Software Engineer (US)",
        "location": "San Francisco, California, United States",
        "url": "https://job-boards.greenhouse.io/lynxanalytics/jobs/8395412002",
        "kind": "ai",
        "fit": "10",
        "focus": "Python software platforms, AI and analytics solutions, cloud deployments, containerization, cross-functional delivery, and production operations",
    },
    {
        "company": "Beacon Software",
        "role": "Software Engineer",
        "location": "New York City, New York, United States",
        "url": "https://job-boards.greenhouse.io/beaconsoftware/jobs/4974798008",
        "kind": "fullstack",
        "fit": "10",
        "focus": "full-stack product engineering, AI-enabled modernization, portfolio software systems, product collaboration, and rapid delivery",
    },
    {
        "company": "Glean",
        "role": "Software Engineer, Fullstack",
        "location": "San Francisco Bay Area",
        "url": "https://job-boards.greenhouse.io/gleanwork/jobs/4006734005",
        "kind": "ai",
        "fit": "10",
        "focus": "AI product workflows, enterprise search, full-stack systems, backend APIs, data workflows, and customer-facing product execution",
    },
    {
        "company": "Anduril Industries",
        "role": "Software Engineer II, Manufacturing Test",
        "location": "Costa Mesa, California, United States",
        "url": "https://job-boards.greenhouse.io/andurilindustries/jobs/5003658007?gh_jid=5003658007",
        "kind": "platform",
        "fit": "9",
        "focus": "manufacturing test software, validation infrastructure, production reliability, automated testing, operational debugging, and hardware-adjacent workflows",
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
    if kind in {"backend", "platform", "ai"}:
        text = text.replace(
            "Implemented the search interface in React and NestJS from Figma designs and stakeholder feedback, using PHP and SQL to retrieve metadata for product features and model inputs",
            "Implemented React and NestJS product surfaces from Figma designs, using PHP and SQL metadata pipelines to support search, recommendations, and model inputs",
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
            f"Greenhouse-sourced batch 2026-05-01; tailored SWE resume rendered and verified one page; emphasized {job['focus']}. Did not claim direct company-specific domain ownership or unlisted framework experience.",
        )
        print(f"{job['company']} | {job['role']} | {pdf}")


if __name__ == "__main__":
    main()
