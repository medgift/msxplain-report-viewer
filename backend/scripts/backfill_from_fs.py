"""Populate the msx.* tables from the existing processed-runs filesystem.

Idempotent: safe to re-run. Walks files/processed/<run>/<patient>/<session>/
exactly like the old get_processed_runs did, and upserts run/patient/session
rows plus report_summary (via the shared compute_report_summary). Backfilled
runs get owner_id = NULL. NOTE: under strict per-user isolation a NULL owner is
hidden from every user, so backfilled runs will not appear in the UI until an
owner is assigned (e.g. an admin UPDATE of msx.runs.owner_id).

Usage (inside the backend container or with DATABASE_URL set):
    python scripts/backfill_from_fs.py [--processed-dir files/processed]
"""
import argparse
import logging
import os
import sys

# Allow running as `python scripts/backfill_from_fs.py` from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import crud, models  # noqa: E402
from db.engine import session_scope, wait_for_db  # noqa: E402
from db.summary import compute_report_summary  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill")


def _subdirs(path):
    return [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]


def backfill(processed_dir: str) -> None:
    if not os.path.isdir(processed_dir):
        logger.warning("Processed dir not found: %s", processed_dir)
        return

    runs = _subdirs(processed_dir)
    logger.info("Found %d run(s) under %s", len(runs), processed_dir)

    for run_id in runs:
        run_path = os.path.join(processed_dir, run_id)
        patient_names = _subdirs(run_path)
        with session_scope() as session:
            crud.register_upload(session, run_id, patient_names)
            any_report = False
            for patient_name in patient_names:
                patient_path = os.path.join(run_path, patient_name)
                for session_label in _subdirs(patient_path):
                    session_path = os.path.join(patient_path, session_label)
                    summary = compute_report_summary(session_path)
                    if summary is not None:
                        crud.upsert_report_summary(
                            session, run_id, patient_name, session_label, summary
                        )
                        any_report = True
                    else:
                        crud.upsert_session(
                            session,
                            run_id,
                            patient_name,
                            session_label,
                            report_csv_present=False,
                        )
            crud.set_run_status(
                session,
                run_id,
                models.RUN_DONE if any_report else models.RUN_UPLOADING,
            )
        logger.info("Backfilled run %s (%d patients)", run_id, len(patient_names))


def main():
    parser = argparse.ArgumentParser(description="Backfill msx.* from filesystem")
    parser.add_argument(
        "--processed-dir",
        default=os.getenv("PROCESSED_FOLDER", "files/processed"),
    )
    args = parser.parse_args()
    wait_for_db()
    backfill(args.processed_dir)
    logger.info("Backfill complete.")


if __name__ == "__main__":
    main()
