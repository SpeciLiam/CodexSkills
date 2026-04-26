#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


def read_candidate_name(readme_path: Path) -> str:
    if not readme_path.exists():
        return "Candidate Name"
    for line in readme_path.read_text().splitlines():
        if line.lower().startswith("candidate_name:"):
            value = line.split(":", 1)[1].strip()
            if value:
                return value
    return "Candidate Name"


def infer_candidate_name(target_dir: Path) -> str:
    local = target_dir / "README.md"
    if local.exists():
        return read_candidate_name(local)
    for ancestor in target_dir.parents:
        generic = ancestor / "generic-resume" / "README.md"
        if generic.exists():
            return read_candidate_name(generic)
    return "Candidate Name"


def latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def role_summary(role: str) -> str:
    lowered = role.lower()
    parts: list[str] = []
    if "backend" in lowered or "back-end" in lowered:
        parts.append("backend engineering")
    if "full-stack" in lowered or "full stack" in lowered:
        parts.append("full-stack product development")
    if "frontend" in lowered or "front-end" in lowered:
        parts.append("frontend product development")
    if "data" in lowered:
        parts.append("data-intensive systems")
    if "platform" in lowered or "infrastructure" in lowered:
        parts.append("platform and infrastructure work")
    if not parts:
        parts.append("software engineering")
    return ", ".join(parts)


def default_opening(company: str, role: str) -> str:
    return (
        f"I am excited to apply for the {role} role at {company}. "
        f"My recent work has focused on {role_summary(role)}, building reliable systems in production, "
        "and contributing across the stack when needed."
    )


def default_interest(company: str, role: str, company_focus: str) -> str:
    if company_focus.strip():
        return (
            f"I am especially interested in {company} because of its work in {company_focus.strip()}, "
            f"and because this role pairs that domain with the kind of {role_summary(role)} work I enjoy most. "
            "I am drawn to teams where engineers can own meaningful features end-to-end, learn quickly, "
            "and contribute directly to customer-facing product outcomes."
        )
    return (
        f"I am especially interested in {company} because this role combines the kind of {role_summary(role)} work "
        "I enjoy most with real product ownership and customer impact. "
        "I am drawn to teams where engineers can own meaningful features end-to-end, learn quickly, "
        "and contribute directly to customer-facing product outcomes."
    )


def build_letter(company: str, candidate_name: str, opening: str, why_interest: str, closing: str) -> str:
    today = date.today().strftime("%B %-d, %Y")
    paragraphs = [opening.strip(), why_interest.strip(), closing.strip()]
    body = "\n\n".join(
        rf"\noindent {latex_escape(paragraph)}" for paragraph in paragraphs if paragraph
    )
    return rf"""\documentclass[letterpaper,11pt]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage[hidelinks]{{hyperref}}
\usepackage[T1]{{fontenc}}
\usepackage[scaled]{{helvet}}
\renewcommand*\familydefault{{\sfdefault}}
\pagenumbering{{gobble}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.9em}}

\begin{{document}}

\begin{{flushleft}}
\textbf{{\Large {latex_escape(candidate_name)}}} \\
Seattle, WA \\
\href{{mailto:liamvanpj@gmail.com}}{{liamvanpj@gmail.com}} \\
\href{{https://liamvan.dev}}{{liamvan.dev}}
\end{{flushleft}}

{latex_escape(today)}

\noindent Dear {latex_escape(company)} Hiring Team,

{body}

\noindent Sincerely, \\
{latex_escape(candidate_name)}

\end{{document}}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a basic company-specific cover letter LaTeX file.")
    parser.add_argument("--dir", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--company-focus", default="")
    parser.add_argument("--opening", default="")
    parser.add_argument("--why-interest", default="")
    parser.add_argument("--closing", default="")
    args = parser.parse_args()

    target_dir = Path(args.dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    candidate_name = infer_candidate_name(target_dir)

    opening = args.opening or default_opening(args.company, args.role)
    why_interest = args.why_interest or default_interest(args.company, args.role, args.company_focus)
    closing = args.closing or (
        "I would welcome the opportunity to contribute, keep learning quickly, and help build thoughtful products "
        "with a team that values ownership and execution."
    )

    tex_path = target_dir / "cover_letter.tex"
    tex_path.write_text(build_letter(args.company, candidate_name, opening, why_interest, closing))
    print(tex_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
