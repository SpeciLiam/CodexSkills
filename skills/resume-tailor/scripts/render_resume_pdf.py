#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

INTERMEDIATE_SUFFIXES = {
    ".aux",
    ".log",
    ".out",
    ".xdv",
    ".fls",
    ".fdb_latexmk",
}


def read_candidate_name(readme_path: Path) -> str | None:
    if not readme_path.exists():
        return None

    for line in readme_path.read_text().splitlines():
        if line.lower().startswith("candidate_name:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value
    return None


def load_candidate_name(resume_dir: Path) -> str:
    local_value = read_candidate_name(resume_dir / "README.md")
    if local_value:
        return local_value

    for ancestor in resume_dir.parents:
        repo_value = read_candidate_name(ancestor / "generic-resume" / "README.md")
        if repo_value:
            return repo_value
    return "Candidate Name"


def candidate_token(value: str) -> str:
    return "_".join(value.split())


def infer_company_name(folder: Path) -> str:
    if folder.parent.parent.name == "companies":
        return folder.parent.name or "Company"
    if folder.parent.parent.parent.name == "companies":
        return folder.parent.parent.name or "Company"
    return folder.parent.name or "Company"


def choose_engine() -> list[str] | None:
    latexmk = shutil.which("latexmk")
    if latexmk:
        return [latexmk, "-pdf", "-interaction=nonstopmode", "-halt-on-error"]

    pdflatex = shutil.which("pdflatex")
    if pdflatex:
        return [pdflatex, "-interaction=nonstopmode", "-halt-on-error"]

    tectonic = shutil.which("tectonic")
    if tectonic:
        return [tectonic, "--keep-logs", "--keep-intermediates"]

    return None


def build_pdf(resume_dir: Path, engine: list[str]) -> Path:
    if Path(engine[0]).name == "latexmk":
        subprocess.run(
            [*engine, "resume.tex"],
            cwd=resume_dir,
            check=True,
        )
    elif Path(engine[0]).name == "tectonic":
        subprocess.run([*engine, "resume.tex"], cwd=resume_dir, check=True)
    else:
        subprocess.run([*engine, "resume.tex"], cwd=resume_dir, check=True)
        subprocess.run([*engine, "resume.tex"], cwd=resume_dir, check=True)

    output = resume_dir / "resume.pdf"
    if not output.exists():
        raise SystemExit(f"Expected PDF was not created: {output}")
    return output


def cleanup_generated_files(resume_dir: Path, final_pdf: Path) -> None:
    for path in resume_dir.iterdir():
        if path == final_pdf or path.name == "resume.tex":
            continue

        if path.name == "resume.pdf" or path.name == "README.md":
            path.unlink(missing_ok=True)
            continue

        if path.suffix in INTERMEDIATE_SUFFIXES:
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a tailored resume PDF with a standardized file name."
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Company-specific resume directory containing resume.tex",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the expected output path without compiling.",
    )
    args = parser.parse_args()

    resume_dir = Path(args.dir).expanduser().resolve()
    resume_tex = resume_dir / "resume.tex"
    if not resume_tex.exists():
        raise SystemExit(f"resume.tex not found in {resume_dir}")

    company_name = infer_company_name(resume_dir)
    candidate_name = load_candidate_name(resume_dir)
    final_pdf = resume_dir / f"{candidate_token(candidate_name)}_{candidate_token(company_name)}.pdf"

    if args.dry_run:
        print(final_pdf)
        return 0

    engine = choose_engine()
    if not engine:
        raise SystemExit(
            "No LaTeX compiler found. Install latexmk or pdflatex, "
            f"then rerun to create: {final_pdf}"
        )

    built_pdf = build_pdf(resume_dir, engine)
    shutil.copyfile(built_pdf, final_pdf)
    cleanup_generated_files(resume_dir, final_pdf)
    print(final_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
