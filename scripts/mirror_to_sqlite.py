#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tracker_table import clean_text, extract_table, first_link_or_text, parse_int


ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS_MD = ROOT / "application-trackers" / "applications.md"
INTAKE_MD = ROOT / "application-trackers" / "job-intake.md"
DB_PATH = ROOT / "application-trackers" / "trackers.sqlite"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def setup(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS applications (
          posting_key TEXT PRIMARY KEY,
          company TEXT, role TEXT, location TEXT, source TEXT,
          job_link TEXT, date_added TEXT, resume_folder TEXT, resume_pdf TEXT,
          status TEXT, applied TEXT, fit_score INTEGER, reach_out TEXT,
          notes TEXT, contact_recruiter TEXT, contact_engineer TEXT,
          mirrored_at TEXT, removed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_apps_company ON applications(company);
        CREATE INDEX IF NOT EXISTS idx_apps_date ON applications(date_added);

        CREATE TABLE IF NOT EXISTS intake (
          posting_key TEXT PRIMARY KEY,
          company TEXT, role TEXT, location TEXT, source TEXT,
          url TEXT, posted_at TEXT, captured_at TEXT,
          fit_score INTEGER, status TEXT, notes TEXT,
          mirrored_at TEXT, removed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_intake_status ON intake(status);
        """
    )


def application_rows(mirrored_at: str) -> list[dict[str, object]]:
    table = extract_table(APPLICATIONS_MD, {"Company", "Role", "Posting Key"})
    rows: list[dict[str, object]] = []
    fallback = 0
    for md_row in table.rows:
        if len(md_row.cells) != len(table.header):
            continue
        row = md_row.row
        posting_key = clean_text(row.get("Posting Key", ""))
        if not posting_key:
            fallback += 1
            posting_key = f"missing-posting-key-{fallback}"
        rows.append(
            {
                "posting_key": posting_key,
                "company": clean_text(row.get("Company", "")),
                "role": clean_text(row.get("Role", "")),
                "location": clean_text(row.get("Location", "")),
                "source": clean_text(row.get("Source", "")),
                "job_link": first_link_or_text(row.get("Job Link", "")),
                "date_added": clean_text(row.get("Date Added", "")),
                "resume_folder": first_link_or_text(row.get("Resume Folder", "")),
                "resume_pdf": first_link_or_text(row.get("Resume PDF", "")),
                "status": clean_text(row.get("Status", "")),
                "applied": clean_text(row.get("Applied", "")),
                "fit_score": parse_int(row.get("Fit Score", "")),
                "reach_out": clean_text(row.get("Reach Out", "")),
                "notes": clean_text(row.get("Notes", "")),
                "contact_recruiter": clean_text(row.get("Recruiter Contact", "")),
                "contact_engineer": clean_text(row.get("Engineer Contact", "")),
                "mirrored_at": mirrored_at,
            }
        )
    return rows


def intake_rows(mirrored_at: str) -> list[dict[str, object]]:
    table = extract_table(INTAKE_MD, {"Source", "Company", "Posting Key"})
    rows: list[dict[str, object]] = []
    fallback = 0
    for md_row in table.rows:
        if len(md_row.cells) != len(table.header):
            continue
        row = md_row.row
        posting_key = clean_text(row.get("Posting Key", "")) or clean_text(row.get("Tracker Posting Key", ""))
        if not posting_key:
            fallback += 1
            posting_key = f"missing-intake-key-{fallback}"
        rows.append(
            {
                "posting_key": posting_key,
                "company": clean_text(row.get("Company", "")),
                "role": clean_text(row.get("Role", "")),
                "location": clean_text(row.get("Location", "")),
                "source": clean_text(row.get("Source", "")),
                "url": first_link_or_text(row.get("Job URL", "")),
                "posted_at": clean_text(row.get("Posted Age", "")),
                "captured_at": clean_text(row.get("Discovered At", "")),
                "fit_score": parse_int(row.get("Fit Score", "")),
                "status": clean_text(row.get("Status", "")),
                "notes": clean_text(row.get("Reason", "")),
                "mirrored_at": mirrored_at,
            }
        )
    return rows


def upsert_rows(conn: sqlite3.Connection, table: str, rows: list[dict[str, object]], mirrored_at: str) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "posting_key")
    assignments = f"{assignments}, removed_at=NULL"
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}, removed_at) "
        f"VALUES ({placeholders}, NULL) "
        f"ON CONFLICT(posting_key) DO UPDATE SET {assignments}"
    )
    conn.executemany(sql, [[row.get(column) for column in columns] for row in rows])
    keys = [str(row["posting_key"]) for row in rows]
    conn.execute(
        f"UPDATE {table} SET removed_at = ? WHERE removed_at IS NULL AND posting_key NOT IN ({', '.join('?' for _ in keys)})",
        [mirrored_at, *keys],
    )


def main() -> int:
    mirrored_at = now_iso()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    apps = application_rows(mirrored_at)
    intake = intake_rows(mirrored_at)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("BEGIN")
        setup(conn)
        upsert_rows(conn, "applications", apps, mirrored_at)
        upsert_rows(conn, "intake", intake, mirrored_at)
        conn.commit()
    print(f"Mirrored {len(apps)} applications, {len(intake)} intake rows to {DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
