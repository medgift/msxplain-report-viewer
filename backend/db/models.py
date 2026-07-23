"""ORM models for MSXplain run/status/report-summary tracking.

All tables live in the ``msx`` schema. GoTrue owns the ``auth`` schema in the
same Postgres; ``runs.owner_id`` references a Supabase ``auth.users`` UUID but
is intentionally NOT a DB-level foreign key — that would couple our migrations
to GoTrue's first-boot ordering. In team mode every authenticated user sees all
runs, so referential integrity on the owner is unnecessary.

Status/step values are plain strings (documented below) rather than Postgres
enums, to keep migrations simple and additive.
"""
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
SCHEMA = "msx"

# Run.status
RUN_UPLOADING = "uploading"
RUN_PROCESSING = "processing"
RUN_DONE = "done"
RUN_FAILED = "failed"

# Patient.status and per-step status
PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"

_UUID_PK = dict(
    primary_key=True,
    server_default=text("gen_random_uuid()"),
)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = {"schema": SCHEMA}

    id = Column(UUID(as_uuid=True), **_UUID_PK)
    run_id = Column(String, nullable=False, unique=True, index=True)
    owner_id = Column(UUID(as_uuid=True), nullable=True)  # Supabase auth.users.id
    status = Column(String, nullable=False, default=RUN_UPLOADING)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    patients = relationship(
        "Patient", back_populates="run", cascade="all, delete-orphan"
    )


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("run_pk", "patient_name", name="uq_patient_run_name"),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), **_UUID_PK)
    run_pk = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_name = Column(String, nullable=False)  # directory key

    # Cached DICOM demographics (populated on first report view).
    display_name = Column(String, nullable=True)  # DICOM PatientName
    patient_id = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)
    sex = Column(String, nullable=True)
    institution_name = Column(String, nullable=True)

    # Per-patient processing state (mirrors the former in-memory dict shape).
    status = Column(String, nullable=False, default=PENDING)
    step_preprocessing = Column(String, nullable=False, default=PENDING)
    step_msxplain = Column(String, nullable=False, default=PENDING)
    step_report = Column(String, nullable=False, default=PENDING)

    run = relationship("Run", back_populates="patients")
    sessions = relationship(
        "SessionRow", back_populates="patient", cascade="all, delete-orphan"
    )


class SessionRow(Base):
    """An imaging session (a date folder) belonging to a patient."""

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint(
            "patient_pk", "session_label", name="uq_session_patient_label"
        ),
        {"schema": SCHEMA},
    )

    id = Column(UUID(as_uuid=True), **_UUID_PK)
    patient_pk = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_label = Column(String, nullable=False)
    study_instance_uid = Column(String, nullable=True)
    report_csv_present = Column(Boolean, nullable=False, default=False)

    patient = relationship("Patient", back_populates="sessions")
    summary = relationship(
        "ReportSummary",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ReportSummary(Base):
    """One-to-one with a session: cheap searchable metrics from report.csv."""

    __tablename__ = "report_summary"
    __table_args__ = {"schema": SCHEMA}

    session_pk = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    count_periventricular = Column(Integer, nullable=False, default=0)
    count_juxtacortical = Column(Integer, nullable=False, default=0)
    count_infratentorial = Column(Integer, nullable=False, default=0)
    count_deep_white_matter = Column(Integer, nullable=False, default=0)
    count_false_positive = Column(Integer, nullable=False, default=0)
    total_lesion_volume = Column(Float, nullable=False, default=0.0)
    dissemination_space = Column(String, nullable=True)
    patient_certainty = Column(Float, nullable=True)

    session = relationship("SessionRow", back_populates="summary")
