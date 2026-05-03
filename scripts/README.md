# Recruiting Pipeline Scripts

Run `python3 scripts/check.sh` before committing tracker edits. It validates the markdown tracker schemas and refreshes the derived SQLite mirror.

Run `python3 scripts/mirror_to_sqlite.py` on a fresh clone to bootstrap `application-trackers/trackers.sqlite`. Markdown remains authoritative; SQLite is read-only derived state for queries and dashboards.

Run `python3 scripts/calibration_report.py` weekly after enough applications have outcomes. Adjust `confidence_score()` in `skills/finish-applications/scripts/build_application_queue.py` by hand based on the report, then commit the tuning change with the report period in the message. There is no auto-tuning yet.
