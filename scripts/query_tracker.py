#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "application-trackers" / "trackers.sqlite"


def print_rows(cursor: sqlite3.Cursor) -> None:
    columns = [description[0] for description in cursor.description or []]
    if columns:
        print("\t".join(columns))
    for row in cursor.fetchall():
        print("\t".join("" if value is None else str(value) for value in row))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run common read-only queries against the tracker SQLite mirror.")
    parser.add_argument("--status", help="Filter application rows by status")
    parser.add_argument("--since", help="Filter application rows with date_added >= YYYY-MM-DD")
    parser.add_argument("--company", help="Search applications by company")
    parser.add_argument("--sql", help="Run a read-only SELECT query")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"Missing {DB_PATH}. Run: python3 scripts/mirror_to_sqlite.py")

    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        if args.sql:
            if not args.sql.strip().lower().startswith("select"):
                raise SystemExit("--sql only accepts SELECT queries")
            cursor = conn.execute(args.sql)
        else:
            where = ["removed_at IS NULL"]
            params: list[str] = []
            if args.status:
                where.append("status = ?")
                params.append(args.status)
            if args.since:
                where.append("date_added >= ?")
                params.append(args.since)
            if args.company:
                where.append("company LIKE ?")
                params.append(f"%{args.company}%")
            cursor = conn.execute(
                """
                SELECT date_added, company, role, status, applied, fit_score, source, posting_key
                FROM applications
                WHERE """ + " AND ".join(where) + """
                ORDER BY date_added DESC, company COLLATE NOCASE
                """,
                params,
            )
        print_rows(cursor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
