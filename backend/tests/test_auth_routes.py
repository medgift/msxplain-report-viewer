"""Mechanical guarantee that every /api route is authenticated.

Auth is enforced by a single global middleware (AuthMiddleware) rather than
per-route dependencies, so coverage can't be forgotten on a new route. This
test locks in that invariant: the middleware is installed, and the only
publicly reachable /api path is the health check.

Run inside the backend environment:  pytest backend/tests
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A JWT secret must be present for the module to import cleanly.
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")

import app as app_module  # noqa: E402
from auth import (  # noqa: E402
    AuthMiddleware,
    DICOMWEB_PREFIX,
    PUBLIC_PATHS,
    decode_supabase_jwt,
)


def _api_paths():
    return {
        r.path
        for r in app_module.app.routes
        if getattr(r, "path", "").startswith("/api/")
    }


def _route(path):
    for r in app_module.app.routes:
        if getattr(r, "path", None) == path:
            return r
    return None


def test_auth_middleware_installed():
    classes = [m.cls for m in app_module.app.user_middleware]
    assert AuthMiddleware in classes, "AuthMiddleware must be installed"


def test_public_paths_are_minimal_and_real():
    api_paths = _api_paths()
    # Every public path must actually be a registered route.
    for path in PUBLIC_PATHS:
        assert path in api_paths, f"Public path {path} is not a registered route"
    # Health is the ONLY public /api route. Adding another must be deliberate.
    assert PUBLIC_PATHS == {"/api/health"}


def test_docs_disabled():
    assert app_module.app.docs_url is None
    assert app_module.app.redoc_url is None
    assert app_module.app.openapi_url is None


def test_bad_token_is_rejected():
    import jwt

    with pytest.raises(jwt.PyJWTError):
        decode_supabase_jwt("not-a-real-token")


def test_dicomweb_proxy_is_read_only():
    """The DICOMweb proxy must accept only GET (no STOW upload / DELETE)."""
    route = _route("/api/dicom-web/{path:path}")
    assert route is not None, "DICOMweb proxy route must be registered"
    # FastAPI adds HEAD automatically for a GET route; nothing else allowed.
    assert set(route.methods) <= {"GET", "HEAD"}, route.methods


def test_dicomweb_proxy_is_not_public():
    """The proxy is under /api/ and NOT allow-listed, so it stays authed."""
    assert "/api/dicom-web/{path:path}" not in PUBLIC_PATHS
    # The middleware's cookie fallback is scoped to exactly this prefix.
    assert DICOMWEB_PREFIX == "/api/dicom-web/"


def test_viewer_session_is_post_and_authed():
    route = _route("/api/viewer-session")
    assert route is not None, "viewer-session route must be registered"
    assert "POST" in set(route.methods)
    assert "/api/viewer-session" not in PUBLIC_PATHS
