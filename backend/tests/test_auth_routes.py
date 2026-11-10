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


# ── Viewer lock-down: sign-out must revoke OHIF access ────────────────────
import time as _time  # noqa: E402

import jwt as _jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import auth as auth_module  # noqa: E402
from auth import VIEWER_AUTH_PATH, VIEWER_COOKIE  # noqa: E402

_SID = "11111111-2222-3333-4444-555555555555"


def _token(session_id=_SID, exp_in=600):
    return _jwt.encode(
        {
            "sub": "user-1",
            "aud": auth_module.JWT_AUD,
            "exp": int(_time.time()) + exp_in,
            "session_id": session_id,
        },
        auth_module.SUPABASE_JWT_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def client(monkeypatch):
    """TestClient with the auth.sessions lookup stubbed (no Postgres)."""
    live = {_SID}
    monkeypatch.setattr(auth_module, "_query_session_live", lambda sid: sid in live)
    auth_module._live_sessions.clear()
    c = TestClient(app_module.app)
    c.live_sessions = live
    yield c
    auth_module._live_sessions.clear()


def test_viewer_auth_route_is_authed():
    route = _route(VIEWER_AUTH_PATH)
    assert route is not None
    assert VIEWER_AUTH_PATH not in PUBLIC_PATHS


def test_viewer_session_can_be_closed():
    methods = set()
    for r in app_module.app.routes:
        if getattr(r, "path", None) == "/api/viewer-session":
            methods |= set(r.methods)
    assert {"POST", "DELETE"} <= methods


def test_viewer_auth_requires_cookie(client):
    assert client.get(VIEWER_AUTH_PATH).status_code == 401


def test_viewer_auth_accepts_live_session_cookie(client):
    client.cookies.set(VIEWER_COOKIE, _token())
    assert client.get(VIEWER_AUTH_PATH).status_code == 204


def test_viewer_cookie_rejected_after_sign_out(client):
    """The reported bug: a lingering cookie must die with the session."""
    client.cookies.set(VIEWER_COOKIE, _token())
    assert client.get(VIEWER_AUTH_PATH).status_code == 204
    client.live_sessions.clear()          # GoTrue deleted the session
    auth_module._live_sessions.clear()    # past the short positive-cache TTL
    assert client.get(VIEWER_AUTH_PATH).status_code == 401
    assert client.get("/api/dicom-web/studies/1.2.3/metadata").status_code == 401


def test_viewer_cookie_without_session_id_rejected(client):
    client.cookies.set(VIEWER_COOKIE, _token(session_id=None))
    assert client.get(VIEWER_AUTH_PATH).status_code == 401


def test_viewer_cookie_not_accepted_on_other_api_routes(client):
    """Cookie is now path=/, but must still only authenticate viewer paths."""
    client.cookies.set(VIEWER_COOKIE, _token())
    assert client.get("/api/processed-runs").status_code == 401


def test_session_check_db_error_fails_closed(client, monkeypatch):
    def boom(sid):
        raise RuntimeError("db down")

    monkeypatch.setattr(auth_module, "_query_session_live", boom)
    client.cookies.set(VIEWER_COOKIE, _token())
    assert client.get(VIEWER_AUTH_PATH).status_code == 401


def test_viewer_session_cookie_is_site_wide_and_cleared_on_delete(client):
    bearer = {"Authorization": f"Bearer {_token()}"}
    set_resp = client.post("/api/viewer-session", headers=bearer)
    assert set_resp.status_code == 204
    set_cookies = set_resp.headers.get_list("set-cookie")
    assert any(
        c.startswith(f"{VIEWER_COOKIE}=") and "Path=/;" in c and "HttpOnly" in c
        for c in set_cookies
    ), set_cookies

    del_resp = client.delete("/api/viewer-session", headers=bearer)
    assert del_resp.status_code == 204
    cleared = [c for c in del_resp.headers.get_list("set-cookie")
               if c.startswith(f'{VIEWER_COOKIE}=""') or "Max-Age=0" in c]
    assert len(cleared) == 2, del_resp.headers.get_list("set-cookie")
