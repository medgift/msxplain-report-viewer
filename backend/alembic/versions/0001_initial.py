"""initial msx schema: runs, patients, sessions, report_summary

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-03
"""
from alembic import op

from db.models import Base, SCHEMA

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

_RLS_TABLES = ["runs", "patients", "sessions", "report_summary"]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    # gen_random_uuid(): built into PG13+ core, pgcrypto provides it otherwise.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Models are the single source of truth for the initial layout.
    Base.metadata.create_all(bind=bind)

    # Deny-all RLS as defense-in-depth. The backend connects as the table
    # owner/superuser and bypasses RLS; any other role (e.g. a leaked anon key
    # reaching Postgres) gets nothing because no policies are defined.
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
