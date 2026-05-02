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
    "ai": r"""     \textbf{Languages}{: Python, Java, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{AI / Product}{: LLM applications, AI-assisted tooling, REST APIs, React, NestJS, OpenSearch, data workflows} \\
     \textbf{Backend / Cloud}{: Spring Boot, MySQL, Docker, AWS, GCP, OCI, distributed systems, production validation} \\
     \textbf{Testing / Operations}{: CI/CD, Robot Framework, Selenium, Grafana, Azure DevOps, release support, on-call response} \\""",
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
    "ai": [
        "Built an LLM-powered recommendation experience for Oracle University and OCI learning content, helping customers discover tailored OCI information and course paths",
        "Drove GA readiness for OCI database services on GCP by validating API, CLI, console, backup, restore, and Data Guard workflows across product surfaces",
        "Built reusable GCloud and OCI scripting workflows plus regression utilities, improving local validation and scaling end-to-end coverage for BaseDB and ADBS releases",
    ],
}

JOBS = [
    {
        "company": "Twitch",
        "role": "Software Engineer I, Commerce Engineering",
        "location": "Seattle, WA",
        "url": "https://job-boards.greenhouse.io/twitch/jobs/8459320002",
        "kind": "fullstack",
        "fit": "10",
        "focus": "consumer-facing commerce, scalable applications, React/TypeScript, AWS-adjacent backend systems, schema design, and product reliability",
    },
    {
        "company": "Twitch",
        "role": "Software Engineer II, Safety",
        "location": "San Francisco, CA",
        "url": "https://job-boards.greenhouse.io/twitch/jobs/8499608002",
        "kind": "backend",
        "fit": "10",
        "focus": "backend safety systems, service reliability, API workflows, debugging, observability, and cross-team execution",
    },
    {
        "company": "Twitch",
        "role": "Software Engineer I, Streamer Monetization Experience",
        "location": "Seattle, WA",
        "url": "https://job-boards.greenhouse.io/twitch/jobs/8470752002",
        "kind": "fullstack",
        "fit": "10",
        "focus": "full-stack product engineering, streamer monetization workflows, React/TypeScript, REST APIs, testing, and production readiness",
    },
    {
        "company": "StubHub",
        "role": "Software Engineer II - Open Distribution (Backend)",
        "location": "Los Angeles, California, United States",
        "url": "https://job-boards.eu.greenhouse.io/stubhubinc/jobs/4825352101",
        "kind": "backend",
        "fit": "10",
        "focus": "backend distribution systems, REST APIs, data modeling, reliability, distributed workflows, and operational debugging",
    },
    {
        "company": "Scale AI",
        "role": "Software Engineer, ARC Team",
        "location": "San Francisco, CA; St. Louis, MO; New York, NY; Washington, DC",
        "url": "https://job-boards.greenhouse.io/scaleai/jobs/4673771005",
        "kind": "ai",
        "fit": "10",
        "focus": "AI product infrastructure, Python/TypeScript systems, LLM applications, data workflows, production validation, and fast execution",
    },
    {
        "company": "Scale AI",
        "role": "Software Engineer, Frontier AI Infrastructure",
        "location": "San Francisco, CA; St. Louis, MO; New York, NY; Washington, DC",
        "url": "https://job-boards.greenhouse.io/scaleai/jobs/4363623005",
        "kind": "platform",
        "fit": "10",
        "focus": "AI infrastructure, backend/platform systems, distributed workflows, observability, reliability, and production readiness",
    },
    {
        "company": "Scale AI",
        "role": "Software Engineer, Gen AI",
        "location": "San Francisco, CA; New York, NY",
        "url": "https://job-boards.greenhouse.io/scaleai/jobs/4591300005",
        "kind": "ai",
        "fit": "10",
        "focus": "generative AI product engineering, LLM applications, Python/TypeScript, REST APIs, data workflows, and cross-functional delivery",
    },
    {
        "company": "Mixpanel",
        "role": "Software Engineer, DevInfra",
        "location": "San Francisco, US (Hybrid)",
        "url": "https://job-boards.greenhouse.io/mixpanel/jobs/7850913",
        "kind": "platform",
        "fit": "9",
        "focus": "developer infrastructure, CI/CD, backend tooling, observability, release validation, and reliable engineering workflows",
    },
    {
        "company": "Grow Therapy",
        "role": "Software Engineer - Full Stack",
        "location": "New York, NY, San Francisco, CA, Seattle, WA",
        "url": "https://job-boards.greenhouse.io/growtherapy/jobs/4678587005",
        "kind": "fullstack",
        "fit": "9",
        "focus": "full-stack product engineering, React/TypeScript, backend APIs, product workflows, testing, reliability, and customer-facing execution",
    },
    {
        "company": "Glean",
        "role": "Software Engineer, Backend",
        "location": "San Francisco Bay Area",
        "url": "https://job-boards.greenhouse.io/gleanwork/jobs/4581643005",
        "kind": "backend",
        "fit": "9",
        "focus": "backend search and AI product systems, REST APIs, data workflows, distributed services, observability, and production validation",
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
