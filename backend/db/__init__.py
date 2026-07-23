"""Database package for MSXplain: engine, ORM models, CRUD helpers.

The backend talks to Postgres directly with a single synchronous SQLAlchemy
engine. Request handlers that touch the DB are declared as plain ``def`` so
FastAPI runs them in its threadpool; the pipeline (which already runs in worker
threads) uses the same engine via ``session_scope()``.
"""
