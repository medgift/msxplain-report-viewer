"""Synchronous CRUD helpers used by request handlers and the pipeline.

Every function takes an open ``Session``; callers manage the transaction via
``get_db`` (handlers) or ``session_scope`` (pipeline threads).
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db import models
from db.models import Patient, ReportSummary, Run, SessionRow

logger = logging.getLogger(__name__)

_STEP_COLUMN = {
    "preprocessing": "step_preprocessing",
    "msxplain": "step_msxplain",
    "report": "step_report",
}

# Fixed key for the global "one processing run at a time" Postgres advisory
# lock. Any constant works as long as it's stable across processes.
_PROCESSING_ADVISORY_KEY = 728194


# ── lookups ──────────────────────────────────────────────────────────────
def get_run(session: Session, run_id: str) -> Optional[Run]:
    return session.scalar(select(Run).where(Run.run_id == run_id))


def _get_patient(session: Session, run: Run, patient_name: str) -> Optional[Patient]:
    return session.scalar(
        select(Patient).where(
            Patient.run_pk == run.id, Patient.patient_name == patient_name
        )
    )


def _get_session_row(
    session: Session, patient: Patient, session_label: str
) -> Optional[SessionRow]:
    return session.scalar(
        select(SessionRow).where(
            SessionRow.patient_pk == patient.id,
            SessionRow.session_label == session_label,
        )
    )


# ── writes: upload / processing lifecycle ────────────────────────────────
def register_upload(
    session: Session,
    run_id: str,
    patient_names,
    owner_id: Optional[str] = None,
) -> Run:
    """Create the run (if new) and ensure a patient row per name. Idempotent."""
    run = get_run(session, run_id)
    if run is None:
        run = Run(run_id=run_id, owner_id=owner_id, status=models.RUN_UPLOADING)
        session.add(run)
        session.flush()
    elif owner_id and run.owner_id is None:
        run.owner_id = owner_id

    for name in patient_names:
        if _get_patient(session, run, name) is None:
            session.add(Patient(run_pk=run.id, patient_name=name))
    return run


def start_processing(session: Session, run_id: str, patient_names) -> None:
    """Mark the run processing and (re)seed each patient to pending/pending."""
    run = get_run(session, run_id)
    if run is None:
        run = register_upload(session, run_id, patient_names)
    run.status = models.RUN_PROCESSING

    for name in patient_names:
        patient = _get_patient(session, run, name)
        if patient is None:
            patient = Patient(run_pk=run.id, patient_name=name)
            session.add(patient)
        patient.status = models.PENDING
        patient.step_preprocessing = models.PENDING
        patient.step_msxplain = models.PENDING
        patient.step_report = models.PENDING


def get_active_processing_run(session: Session) -> Optional[str]:
    """Return the run_id of the run currently processing, if any."""
    return session.scalar(
        select(Run.run_id).where(Run.status == models.RUN_PROCESSING).limit(1)
    )


def try_start_processing(
    session: Session, run_id: str, patient_names
) -> bool:
    """Atomically claim the single global processing slot for *run_id*.

    Serializes concurrent claim attempts with a transaction-scoped Postgres
    advisory lock, so the check-and-set is race-free across workers/processes.
    Unlike an in-memory lock, the slot is defined purely by DB state
    (``Run.status == processing``), so it also survives a restart. Returns
    False if a *different* run is already processing.
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": _PROCESSING_ADVISORY_KEY},
    )
    active = get_active_processing_run(session)
    if active is not None and active != run_id:
        return False
    start_processing(session, run_id, patient_names)
    return True


def fail_orphaned_processing_runs(session: Session) -> int:
    """Mark runs stuck in 'processing' as failed and return how many.

    Called once at startup: the pipeline runs in-process as a background task,
    so any run still marked processing at boot has no worker behind it (the
    process died mid-run). Clearing it frees the single-flight slot and stops
    the UI from polling a run that will never finish.
    """
    runs = session.scalars(
        select(Run).where(Run.status == models.RUN_PROCESSING)
    ).all()
    for run in runs:
        run.status = models.RUN_FAILED
        for patient in run.patients:
            if patient.status == models.PROCESSING:
                patient.status = models.FAILED
            for column in _STEP_COLUMN.values():
                if getattr(patient, column) == models.PROCESSING:
                    setattr(patient, column, models.FAILED)
    return len(runs)


def set_patient_status(
    session: Session, run_id: str, patient_name: str, status: str
) -> None:
    run = get_run(session, run_id)
    if run is None:
        return
    patient = _get_patient(session, run, patient_name)
    if patient is not None:
        patient.status = status


def set_patient_step(
    session: Session, run_id: str, patient_name: str, step: str, status: str
) -> None:
    column = _STEP_COLUMN.get(step)
    if column is None:
        return
    run = get_run(session, run_id)
    if run is None:
        return
    patient = _get_patient(session, run, patient_name)
    if patient is not None:
        setattr(patient, column, status)


def set_run_status(session: Session, run_id: str, status: str) -> None:
    run = get_run(session, run_id)
    if run is not None:
        run.status = status


def upsert_session(
    session: Session,
    run_id: str,
    patient_name: str,
    session_label: str,
    study_instance_uid: Optional[str] = None,
    report_csv_present: Optional[bool] = None,
    demographics: Optional[dict] = None,
) -> Optional[SessionRow]:
    """Create/update a session row (and optionally patient demographics)."""
    run = get_run(session, run_id)
    if run is None:
        return None
    patient = _get_patient(session, run, patient_name)
    if patient is None:
        patient = Patient(run_pk=run.id, patient_name=patient_name)
        session.add(patient)
        session.flush()

    if demographics:
        for field in (
            "display_name",
            "patient_id",
            "birth_date",
            "sex",
            "institution_name",
        ):
            value = demographics.get(field)
            if value is not None:
                setattr(patient, field, value)

    row = _get_session_row(session, patient, session_label)
    if row is None:
        row = SessionRow(patient_pk=patient.id, session_label=session_label)
        session.add(row)
        session.flush()
    if study_instance_uid is not None:
        row.study_instance_uid = study_instance_uid
    if report_csv_present is not None:
        row.report_csv_present = report_csv_present
    return row


def upsert_report_summary(
    session: Session,
    run_id: str,
    patient_name: str,
    session_label: str,
    summary: dict,
) -> None:
    """Store the derived summary metrics for a session (1:1)."""
    row = upsert_session(
        session, run_id, patient_name, session_label, report_csv_present=True
    )
    if row is None:
        return
    existing = session.get(ReportSummary, row.id)
    if existing is None:
        existing = ReportSummary(session_pk=row.id)
        session.add(existing)
    for key, value in summary.items():
        if hasattr(existing, key):
            setattr(existing, key, value)


# ── reads: rebuild the JSON shapes the frontend expects ──────────────────
def get_run_status_json(session: Session, run_id: str) -> Optional[dict]:
    run = get_run(session, run_id)
    if run is None:
        return None
    patients = {
        p.patient_name: {
            "status": p.status,
            "steps": {
                "preprocessing": p.step_preprocessing,
                "msxplain": p.step_msxplain,
                "report": p.step_report,
            },
        }
        for p in run.patients
    }
    return {
        "status": run.status,
        "total_patients": len(patients),
        "patients": patients,
    }


def list_runs_json(session: Session) -> list:
    runs = session.scalars(select(Run).order_by(Run.created_at.desc())).all()
    result = []
    for run in runs:
        patients = []
        total_sessions = 0
        for patient in run.patients:
            session_statuses = []
            for srow in patient.sessions:
                total_sessions += 1
                has_report = bool(srow.report_csv_present)
                # A session is "Complete" once its report exists; otherwise it
                # is still processing.
                status = "Complete" if has_report else "Processing"
                session_statuses.append(
                    {
                        "date": srow.session_label,
                        "status": status,
                        "report": has_report,
                    }
                )
            patients.append(
                {
                    "id": patient.patient_name,
                    "sessions": session_statuses,
                    "status": (
                        "Complete"
                        if session_statuses
                        and all(s["status"] == "Complete" for s in session_statuses)
                        else "Processing"
                    ),
                }
            )
        created = run.created_at or datetime.utcnow()
        result.append(
            {
                "id": run.run_id,
                "date": created.strftime("%Y-%m-%d %H:%M:%S"),
                "patients": patients,
                "total_patients": len(patients),
                "total_sessions": total_sessions,
            }
        )
    return result


def get_report_meta(
    session: Session, run_id: str, patient_name: str, session_label: str
) -> Optional[dict]:
    """Return cached demographics + study UID for a session, if recorded."""
    run = get_run(session, run_id)
    if run is None:
        return None
    patient = _get_patient(session, run, patient_name)
    if patient is None:
        return None
    row = _get_session_row(session, patient, session_label)
    return {
        "patient_name": patient.patient_name,
        "display_name": patient.display_name,
        "patient_id": patient.patient_id,
        "birth_date": patient.birth_date,
        "sex": patient.sex,
        "institution_name": patient.institution_name,
        "study_instance_uid": row.study_instance_uid if row else None,
    }
