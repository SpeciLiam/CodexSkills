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
    "security": r"""     \textbf{Languages}{: Java, Python, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{Backend / APIs}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, distributed systems, data modeling} \\
     \textbf{Reliability / Operations}{: CI/CD, Grafana, T2, canary validation, release support, on-call response, Selenium} \\
     \textbf{Cloud / Product}{: AWS, GCP, OCI, React, NestJS, Angular, Node.js, technical documentation} \\""",
    "ai": r"""     \textbf{Languages}{: Python, Java, TypeScript, JavaScript, SQL, C++, C\#, PHP, C} \\
     \textbf{AI / Product}{: LLM applications, AI-assisted tooling, REST APIs, React, NestJS, OpenSearch, data workflows} \\
     \textbf{Backend / Cloud}{: Spring Boot, MySQL, Docker, AWS, GCP, OCI, distributed systems, production validation} \\
     \textbf{Testing / Operations}{: CI/CD, Robot Framework, Selenium, Grafana, Azure DevOps, release support, on-call response} \\""",
    "mobile_fullstack": r"""     \textbf{Languages}{: Java, TypeScript, JavaScript, Python, SQL, C\#, C++, PHP, C} \\
     \textbf{Backend / Cloud}{: REST APIs, Spring Boot, MySQL, OpenSearch, Docker, AWS, GCP, OCI, microservices} \\
     \textbf{Frontend / Mobile}{: React, NestJS, Angular, Node.js, Android Studio, product integrations} \\
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
    "security": [
        "Drove GA readiness for OCI database services on GCP by validating security-sensitive API, CLI, console, backup, restore, and Data Guard workflows across product surfaces",
        "Served as primary on-call for Oasis releases, leading Sev2 investigations and resolving Sev3 and Sev4 issues through log analysis, Grafana, T2 metrics, and alarm tuning",
        "Implemented Exascale Storage Vault dry-run support, improving preflight validation and reaching over 90\\% unit test coverage across BaseDB and Exadata Infrastructure components",
    ],
    "ai": [
        "Built an LLM-powered recommendation experience for Oracle University and OCI learning content, helping customers discover tailored OCI information and course paths",
        "Drove GA readiness for OCI database services on GCP by validating API, CLI, console, backup, restore, and Data Guard workflows across product surfaces",
        "Built reusable GCloud and OCI scripting workflows plus regression utilities, improving local validation and scaling end-to-end coverage for BaseDB and ADBS releases",
    ],
    "mobile_fullstack": [
        "Drove GA readiness for OCI database services on GCP by validating API, CLI, console, backup, restore, and Data Guard workflows across partner-owned product surfaces",
        "Built reusable GCloud and OCI scripting workflows plus regression utilities, improving local validation and scaling end-to-end coverage for BaseDB and ADBS releases",
        "Implemented React and NestJS product surfaces from Figma designs, using PHP and SQL metadata pipelines to support search, recommendations, and model inputs",
    ],
}

JOBS = [
    {
        "company": "Pinterest",
        "role": "Security Software Engineer II, Detection and Response",
        "location": "San Francisco, CA, US; Remote, US",
        "url": "https://www.pinterestcareers.com/jobs/?gh_jid=7770914",
        "kind": "security",
        "fit": "10",
        "focus": "security-adjacent backend systems, incident response habits, observability, CI/CD, APIs, and production operations",
    },
    {
        "company": "Pinterest",
        "role": "Security Software Engineer II, Internal Identity & Access Management",
        "location": "Seattle, WA, US; Remote, US",
        "url": "https://www.pinterestcareers.com/jobs/?gh_jid=7770900",
        "kind": "security",
        "fit": "10",
        "focus": "identity-adjacent backend workflows, reliable APIs, cloud validation, operational ownership, and cross-team execution",
    },
    {
        "company": "Pinterest",
        "role": "Software Engineer II, Backend",
        "location": "San Francisco, CA, US; Seattle, WA, US",
        "url": "https://www.pinterestcareers.com/jobs/?gh_jid=4813946",
        "kind": "backend",
        "fit": "10",
        "focus": "backend APIs, distributed service validation, data workflows, reliability, and production readiness",
    },
    {
        "company": "Pinterest",
        "role": "Software Engineer II, Backend, tvScientific",
        "location": "San Francisco, CA, US; Remote, US",
        "url": "https://www.pinterestcareers.com/jobs/?gh_jid=7782552",
        "kind": "backend",
        "fit": "10",
        "focus": "backend product systems, APIs, data modeling, high-throughput validation, and operational reliability",
    },
    {
        "company": "Pinterest",
        "role": "Software Engineer II, ML Platform, tvScientific",
        "location": "San Francisco, CA, US; Remote, US",
        "url": "https://www.pinterestcareers.com/jobs/?gh_jid=7782571",
        "kind": "ai",
        "fit": "10",
        "focus": "ML platform-adjacent backend systems, AI product workflows, APIs, data pipelines, and production validation",
    },
    {
        "company": "Pinterest",
        "role": "Software Engineer II, Simulation, tvScientific",
        "location": "San Francisco, CA, US; Remote, US",
        "url": "https://www.pinterestcareers.com/jobs/?gh_jid=7642265",
        "kind": "platform",
        "fit": "10",
        "focus": "simulation-adjacent platform workflows, validation tooling, distributed systems, observability, and release safety",
    },
    {
        "company": "Flexport",
        "role": "Software Engineer II, Autonomous Freight Systems",
        "location": "San Francisco, California, United States",
        "url": "https://boards.greenhouse.io/flexport/jobs/7839346?gh_jid=7839346",
        "kind": "backend",
        "fit": "10",
        "focus": "backend logistics workflows, distributed APIs, data modeling, reliability, and operational debugging",
    },
    {
        "company": "Fanatics Betting & Gaming",
        "role": "Software Engineer II, iCasino - US",
        "location": "New York, NY, United States",
        "url": "https://job-boards.greenhouse.io/fanaticsfbg/jobs/4209984009",
        "kind": "backend",
        "fit": "10",
        "focus": "backend product engineering, high-reliability APIs, cloud operations, testing, and cross-functional delivery",
    },
    {
        "company": "Attentive",
        "role": "Software Engineer II, BI Tooling and Platform",
        "location": "United States",
        "url": "https://job-boards.greenhouse.io/attentive/jobs/4224514009",
        "kind": "platform",
        "fit": "10",
        "focus": "BI tooling, platform reliability, backend data workflows, CI/CD, observability, and developer productivity",
    },
    {
        "company": "Affirm",
        "role": "Software Engineer I, Backend (Purchasing Power Experience)",
        "location": "Remote US",
        "url": "https://job-boards.greenhouse.io/affirm/jobs/7673126003",
        "kind": "backend",
        "fit": "10",
        "focus": "backend product APIs, financial-product reliability, data workflows, validation, and cross-team execution",
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
    if kind in {"backend", "platform", "security", "ai"}:
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
