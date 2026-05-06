#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "skills" / "resume-tailor" / "config"
JOBS_PATH = CONFIG_DIR / "tailor_jobs.json"
PROFILES_PATH = CONFIG_DIR / "skill_profiles.json"


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_note(batch: dict[str, Any], job: dict[str, Any]) -> str:
    focus = job.get("focus") or job.get("kind", "role-relevant experience")
    return (
        f"{batch['note_prefix']}; tailored SWE resume rendered and verified one page; "
        f"emphasized {focus}. {batch['note_suffix']}"
    )


def update_intake_status(company: str, role: str, status: str, posting_key: str, note: str) -> None:
    path = ROOT / "application-trackers" / "job-intake.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
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
    subprocess.run(["python3", "scripts/mirror_to_sqlite.py"], cwd=ROOT, check=False)


def tailor_tex(path: Path, kind: str, profiles: dict[str, Any]) -> None:
    if kind not in profiles:
        known = ", ".join(sorted(profiles))
        raise KeyError(f"Unknown skill profile '{kind}'. Known profiles: {known}")

    profile = profiles[kind]
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r"     \\textbf\{Languages\}\{:[\s\S]*?     \\textbf\{(?:Frontend / Product|Product / Tooling|Tooling / Product|Testing / Operations|Backend / Product|Cloud / Product|Frontend / Mobile)\}\{:[^\n]+\} \\\\\n",
        lambda _: profile["skills"] + "\n",
        text,
    )

    bullets = profile["role_bullets"]
    text = re.sub(
        r"    \\resumeItem\{Drove GA readiness[\s\S]*?    \\resumeItem\{Built reusable GCloud[\s\S]*?\n    \\resumeItem\{(?:Implemented and merged dry-run support|Implemented Exascale Storage Vault dry-run support)[\s\S]*?\n",
        lambda _: "".join(f"    \\resumeItem{{{bullet}}}\n" for bullet in bullets),
        text,
    )

    if kind in {"backend", "platform", "ai"}:
        text = text.replace(
            "Implemented the search interface in React and NestJS from Figma designs and stakeholder feedback, using PHP and SQL to retrieve metadata for product features and model inputs",
            "Implemented React and NestJS product surfaces from Figma designs, using PHP and SQL metadata pipelines to support search, recommendations, and model inputs",
        )

    path.write_text(text, encoding="utf-8")


def find_batch(data: dict[str, Any], batch_id: str) -> dict[str, Any]:
    for batch in data["batches"]:
        if batch["id"] == batch_id:
            return batch
    known = ", ".join(batch["id"] for batch in data["batches"])
    raise SystemExit(f"Unknown batch '{batch_id}'. Known batches: {known}")


def render_job(batch: dict[str, Any], job: dict[str, Any], profiles: dict[str, Any]) -> Path:
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
    tailor_tex(tex, job["kind"], profiles)

    run("python3", "skills/resume-tailor/scripts/render_resume_pdf.py", "--dir", str(folder))
    pdfs = sorted(folder.glob("Liam_Van_*.pdf"), key=lambda candidate: candidate.stat().st_mtime)
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
        job["source"],
        "--referral",
        "No",
        "--date-added",
        batch["date_added"],
        "--resume-folder",
        str(folder),
        "--resume-pdf",
        str(pdf),
        "--status",
        "Resume Tailored",
        "--fit-score",
        job["fit"],
        "--notes",
        build_note(batch, job),
    )

    if batch.get("update_intake_status"):
        update_intake_status(
            job["company"],
            job["role"],
            "Tailored",
            job.get("posting_key", ""),
            (
                f"Tailored {batch['intake_tailored_date']}; resume rendered and verified one page; "
                f"emphasized {job['focus']}"
            ),
        )

    job["generated"] = True
    job["date_tailored"] = date.today().isoformat()
    job["resume_folder"] = str(folder)
    job["resume_pdf"] = str(pdf)
    return pdf


def validate_manifest(data: dict[str, Any]) -> int:
    problems = 0
    for batch in data["batches"]:
        for job in batch["jobs"]:
            if not job.get("generated"):
                continue
            for field in ("resume_folder", "resume_pdf"):
                value = job.get(field)
                if not value or not Path(value).exists():
                    print(f"missing {field}: {batch['id']} | {job['company']} | {job['role']} | {value}")
                    problems += 1
    if problems == 0:
        print("manifest ok")
    return problems


def list_batches(data: dict[str, Any]) -> None:
    for batch in data["batches"]:
        print(f"{batch['id']}: {len(batch['jobs'])} jobs, date_added={batch['date_added']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tailor resumes from the canonical job manifest.")
    parser.add_argument("--batch", help="Batch id from skills/resume-tailor/config/tailor_jobs.json")
    parser.add_argument("--list-batches", action="store_true", help="Print available batch ids and exit")
    parser.add_argument("--validate-manifest", action="store_true", help="Check generated resume paths in the manifest")
    parser.add_argument("--no-write-manifest", action="store_true", help="Do not persist generated resume paths")
    args = parser.parse_args()

    data = load_json(JOBS_PATH)
    profiles = load_json(PROFILES_PATH)["profiles"]

    if args.list_batches:
        list_batches(data)
        return

    if args.validate_manifest:
        raise SystemExit(validate_manifest(data))

    if not args.batch:
        parser.error("--batch is required unless --list-batches or --validate-manifest is used")

    batch = find_batch(data, args.batch)
    for status_update in batch.get("status_updates", []):
        update_intake_status(**status_update)

    for job in batch["jobs"]:
        pdf = render_job(batch, job, profiles)
        print(f"{job['company']} | {job['role']} | {pdf}")

    if not args.no_write_manifest:
        write_json(JOBS_PATH, data)


if __name__ == "__main__":
    main()
