#!/usr/bin/env python3

from __future__ import annotations

import argparse


DEFAULT_CANDIDATE_NAME = "Liam Van"
DEFAULT_EMPLOYER = "Oracle"
DEFAULT_TEAM = "OCI's Google Cloud Integration team"
MAX_LENGTH = 300


def first_name(name: str) -> str:
    cleaned = " ".join(name.split()).strip()
    if not cleaned:
        return ""
    return cleaned.split(" ", 1)[0]


def recruiter_note(target_name: str, company: str, role: str) -> str:
    greeting = f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
    return (
        f"{greeting} I'm {DEFAULT_CANDIDATE_NAME}, a SWE at {DEFAULT_EMPLOYER} on "
        f"{DEFAULT_TEAM}. I'd love to connect and learn more about {company}'s {role} "
        "role. Any insight would be greatly appreciated. Thanks, Liam"
    )


def engineer_note(target_name: str, company: str, role: str) -> str:
    greeting = f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
    return (
        f"{greeting} I'm {DEFAULT_CANDIDATE_NAME}, a SWE at {DEFAULT_EMPLOYER} on "
        f"{DEFAULT_TEAM}. I'd love to connect and learn more about your experience at "
        f"{company} and the {role} role. Thanks, Liam"
    )


def general_note(target_name: str, company: str, role: str) -> str:
    greeting = f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
    return (
        f"{greeting} I'm {DEFAULT_CANDIDATE_NAME}, a SWE at {DEFAULT_EMPLOYER} on "
        f"{DEFAULT_TEAM}. I'd love to connect and learn more about {company}'s {role} "
        "opportunity. Thanks, Liam"
    )


def compact_company_role(company: str, role: str) -> tuple[str, str]:
    compact_role = " ".join(role.split())
    replacements = [
        ("New College Grad", "New Grad"),
        ("Software Engineer", "SWE"),
        ("Full Stack", "Full-Stack"),
        ("Backend", "Backend"),
        ("Frontend", "Frontend"),
        ("Engineer", "Eng"),
        (" and ", " & "),
    ]
    for before, after in replacements:
        compact_role = compact_role.replace(before, after)
    compact_company = " ".join(company.split())
    return compact_company, compact_role


def shrink_note(note: str, company: str, role: str, variant: str, target_name: str) -> str:
    if len(note) <= MAX_LENGTH:
        return note

    company, role = compact_company_role(company, role)

    shorter_team = "OCI's Google Cloud Integration team"
    shortest_team = "OCI"

    templates = {
        "recruiter": [
            lambda: (
                f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
            )
            + f" I'm Liam Van, a SWE at Oracle on {shorter_team}. I'd love to connect and learn more about {company}'s {role} role. Thanks, Liam",
            lambda: (
                f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
            )
            + f" I'm Liam Van, a SWE at Oracle on {shortest_team}. I'd love to connect and learn more about {company}'s {role} role. Thanks, Liam",
        ],
        "engineer": [
            lambda: (
                f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
            )
            + f" I'm Liam Van, a SWE at Oracle on {shorter_team}. I'd love to connect and learn more about your experience at {company} and the {role} role. Thanks, Liam",
            lambda: (
                f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
            )
            + f" I'm Liam Van, a SWE at Oracle on {shortest_team}. I'd love to connect and learn more about your experience at {company} and the {role} role. Thanks, Liam",
        ],
        "general": [
            lambda: (
                f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
            )
            + f" I'm Liam Van, a SWE at Oracle on {shorter_team}. I'd love to connect and learn more about {company}'s {role} opportunity. Thanks, Liam",
            lambda: (
                f"Hi {first_name(target_name)}," if target_name.strip() else "Hi,"
            )
            + f" I'm Liam Van, a SWE at Oracle on {shortest_team}. I'd love to connect and learn more about {company}'s {role} opportunity. Thanks, Liam",
        ],
    }

    for builder in templates[variant]:
        candidate = builder()
        if len(candidate) <= MAX_LENGTH:
            return candidate

    brute_force = templates[variant][-1]()
    if len(brute_force) <= MAX_LENGTH:
        return brute_force
    return brute_force[: MAX_LENGTH - 1].rstrip() + "…"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a LinkedIn connection note for recruiter or engineer outreach."
    )
    parser.add_argument("--company", required=True, help="Target company")
    parser.add_argument("--role", required=True, help="Target role title")
    parser.add_argument("--target-name", default="", help="Recipient full name")
    parser.add_argument(
        "--variant",
        choices=("recruiter", "engineer", "general"),
        default="recruiter",
        help="Which note style to generate",
    )
    args = parser.parse_args()

    builders = {
        "recruiter": recruiter_note,
        "engineer": engineer_note,
        "general": general_note,
    }
    note = builders[args.variant](args.target_name, args.company, args.role)
    note = shrink_note(note, args.company, args.role, args.variant, args.target_name)

    print(note)
    print("")
    print(f"Length: {len(note)} / {MAX_LENGTH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
