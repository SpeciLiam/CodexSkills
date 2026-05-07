#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

IGNORED_NAMES = {
    ".gitkeep",
    "resume.pdf",
}

IGNORED_SUFFIXES = {
    ".pdf",
    ".aux",
    ".log",
    ".out",
    ".xdv",
    ".fls",
    ".fdb_latexmk",
}


def load_candidate_name(generic_resume_dir: Path) -> str:
    readme_path = generic_resume_dir / "README.md"
    if not readme_path.exists():
        return "Liam Van"

    for line in readme_path.read_text().splitlines():
        if line.lower().startswith("candidate_name:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value
    return "Liam Van"


def safe_path_component(value: str, fallback: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return fallback
    return trimmed.replace("/", "-").replace("\\", "-")


def candidate_token(value: str) -> str:
    return "_".join(value.split())


def role_token(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value.strip())
    compact = "_".join(part for part in cleaned.split("_") if part)
    return compact or "General_Role"


def unique_destination(base_dir: Path, folder_name: str) -> Path:
    destination = base_dir / folder_name
    if not destination.exists():
        return destination

    suffix = 2
    while True:
        candidate = base_dir / f"{folder_name}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a company-specific resume folder from the generic resume source."
    )
    parser.add_argument("--company", required=True, help="Target company name")
    parser.add_argument(
        "--role",
        default="",
        help="Optional target role title. When provided, creates a role-specific subfolder under the company.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Optional repo root override. Defaults to the repo containing this script.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing destination folder if it already exists.",
    )
    args = parser.parse_args()

    repo_root = (
        Path(args.root).expanduser().resolve()
        if args.root
        else Path(__file__).resolve().parents[3]
    )
    template_dir = repo_root / "generic-resume"
    if not template_dir.exists():
        raise SystemExit(f"Generic resume directory not found: {template_dir}")

    company_display = safe_path_component(args.company, "Unknown Company")
    candidate_name = load_candidate_name(template_dir)
    folder_name = f"{candidate_token(candidate_name)}_Resume"
    company_base = repo_root / "companies" / company_display
    if args.role.strip():
        company_base = company_base / role_token(args.role)
    destination = unique_destination(company_base, folder_name)

    if destination.exists():
        if not args.force:
            raise SystemExit(
                f"Destination already exists: {destination}\n"
                "Re-run with --force to replace it."
            )
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        template_dir,
        destination,
        ignore=shutil.ignore_patterns(
            *IGNORED_NAMES,
            *[f"*{suffix}" for suffix in IGNORED_SUFFIXES],
        ),
    )

    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
