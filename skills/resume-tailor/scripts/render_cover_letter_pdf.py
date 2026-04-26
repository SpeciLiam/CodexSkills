#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def read_candidate_name(readme_path: Path) -> str | None:
    if not readme_path.exists():
        return None
    for line in readme_path.read_text().splitlines():
        if line.lower().startswith("candidate_name:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value
    return None


def load_candidate_name(target_dir: Path) -> str:
    local = read_candidate_name(target_dir / "README.md")
    if local:
        return local
    for ancestor in target_dir.parents:
        generic = read_candidate_name(ancestor / "generic-resume" / "README.md")
        if generic:
            return generic
    return "Candidate Name"


def token(value: str) -> str:
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


def build_pdf(target_dir: Path, engine: list[str]) -> Path:
    filename = "cover_letter.tex"
    if Path(engine[0]).name == "latexmk":
        subprocess.run([*engine, filename], cwd=target_dir, check=True)
    elif Path(engine[0]).name == "tectonic":
        subprocess.run([*engine, filename], cwd=target_dir, check=True)
    else:
        subprocess.run([*engine, filename], cwd=target_dir, check=True)
        subprocess.run([*engine, filename], cwd=target_dir, check=True)
    built = target_dir / "cover_letter.pdf"
    if not built.exists():
        raise SystemExit(f"Expected PDF was not created: {built}")
    return built


def cleanup(target_dir: Path, final_pdf: Path) -> None:
    keep = {"cover_letter.tex", "resume.tex", "README.md", final_pdf.name}
    for path in target_dir.iterdir():
        if path.name in keep:
            continue
        if path.name == "cover_letter.pdf" or path.suffix in {".aux", ".log", ".out", ".xdv", ".fls", ".fdb_latexmk"}:
            path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a cover letter PDF next to a tailored resume.")
    parser.add_argument("--dir", required=True)
    args = parser.parse_args()

    target_dir = Path(args.dir).expanduser().resolve()
    tex = target_dir / "cover_letter.tex"
    if not tex.exists():
        raise SystemExit(f"cover_letter.tex not found in {target_dir}")

    company_name = infer_company_name(target_dir)
    candidate_name = load_candidate_name(target_dir)
    final_pdf = target_dir / f"{token(candidate_name)}_{token(company_name)}_Cover_Letter.pdf"

    engine = choose_engine()
    if not engine:
        raise SystemExit(f"No LaTeX compiler found. Install latexmk or pdflatex, then rerun to create: {final_pdf}")

    built = build_pdf(target_dir, engine)
    shutil.copyfile(built, final_pdf)
    cleanup(target_dir, final_pdf)
    print(final_pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
