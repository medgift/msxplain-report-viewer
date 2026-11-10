"""Supabase (GoTrue) JWT verification and a fail-closed auth middleware.

GoTrue signs access tokens symmetrically (HS256) with a shared secret, so we
verify with that secret — there is no JWKS endpoint to fetch.

The middleware runs for *every* request and denies anything under ``/api/``
that isn't in ``PUBLIC_PATHS`` and doesn't carry a valid bearer token. Being a
global middleware (rather than per-route dependencies) is the mechanical
guarantee that no new route can be added unauthenticated by mistake.
"""
import os
import time
import uuid
import logging

import jwt
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
JWT_AUD = os.getenv("SUPABASE_JWT_AUD", "authenticated")

# The public Supabase demo secret. It is world-known, so accepting it would let
# anyone forge a valid token. Refuse to start rather than fail open.
_DEMO_JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"
if SUPABASE_JWT_SECRET == _DEMO_JWT_SECRET:
    raise RuntimeError(
        "SUPABASE_JWT_SECRET is set to the public Supabase demo secret. "
        "Generate a unique value (e.g. `openssl rand -base64 48`) and set "
        "JWT_SECRET before starting."
    )

# Routes reachable without a token. Keep this list as small as possible.
PUBLIC_PATHS = {"/api/health"}

# The OHIF viewer makes same-origin DICOMweb requests (under this prefix) that
# it cannot attach an Authorization header to. For that prefix ONLY we also
# accept a short-lived HttpOnly session cookie issued by /api/viewer-session.
DICOMWEB_PREFIX = "/api/dicom-web/"
VIEWER_COOKIE = "dcmw"
# nginx `auth_request` target guarding the OHIF app itself (/viewer/). It is the
# only other path where the viewer cookie is accepted.
VIEWER_AUTH_PATH = "/api/viewer-auth"


def _cookie_allowed(path: str) -> bool:
    return path.startswith(DICOMWEB_PREFIX) or path == VIEWER_AUTH_PATH


# ── Server-side session revocation for the viewer cookie ──────────────────
# A JWT is stateless: signing out in the SPA does not invalidate it, so a
# lingering `dcmw` cookie would keep the viewer working until the token
# expires. For cookie-authenticated requests we therefore also require the
# token's GoTrue session (`session_id` claim) to still exist in auth.sessions.
# GoTrue deletes that row on sign-out (and on inactivity/timebox expiry), so
# viewer access dies with the session. Positive results are cached briefly so
# the hundreds of per-frame WADO requests don't each hit Postgres; the TTL is
# the maximum time a signed-out cookie can still be honoured.
_SESSION_LIVE_TTL = 10.0  # seconds
_live_sessions: dict = {}


def _query_session_live(session_id: str) -> bool:
    from db.engine import session_scope

    with session_scope() as db:
        row = db.execute(
            text(
                "SELECT 1 FROM auth.sessions WHERE id = :sid "
                "AND (not_after IS NULL OR not_after > now())"
            ),
            {"sid": session_id},
        ).first()
    return row is not None


def session_is_live(session_id) -> bool:
    """True iff the GoTrue session behind a token has not been revoked."""
    try:
        sid = str(uuid.UUID(str(session_id)))
    except (ValueError, TypeError):
        return False
    now = time.monotonic()
    expires = _live_sessions.get(sid)
    if expires is not None and expires > now:
        return True
    if not _query_session_live(sid):
        _live_sessions.pop(sid, None)
        return False
    if len(_live_sessions) > 10_000:  # bound memory; entries are tiny
        _live_sessions.clear()
    _live_sessions[sid] = now + _SESSION_LIVE_TTL
    return True


def decode_supabase_jwt(token: str) -> dict:
    """Validate signature, expiry and audience; return the claims."""
    if not SUPABASE_JWT_SECRET:
        raise RuntimeError("SUPABASE_JWT_SECRET is not configured")
    return jwt.decode(
        token,
        SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience=JWT_AUD,
    )


def _bearer_token(header_value: str):
    if header_value and header_value.lower().startswith("bearer "):
        return header_value[7:].strip()
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        # Let CORS preflight, public routes, and non-API paths through.
        if (
            request.method == "OPTIONS"
            or path in PUBLIC_PATHS
            or not path.startswith("/api/")
        ):
            return await call_next(request)

        token = _bearer_token(request.headers.get("Authorization", ""))
        # DICOMweb requests from the OHIF tab (and nginx's /viewer/ auth
        # check) carry the session cookie instead of a bearer header. The
        # cookie value is itself a Supabase JWT, so it goes through the exact
        # same verification below, plus a session-revocation check.
        from_cookie = False
        if not token and _cookie_allowed(path):
            token = request.cookies.get(VIEWER_COOKIE) or None
            from_cookie = token is not None
        if not token:
            return JSONResponse(
                {"detail": "Authentication required"}, status_code=401
            )
        try:
            claims = decode_supabase_jwt(token)
        except jwt.PyJWTError as exc:
            logger.info("Rejected token: %s", exc)
            return JSONResponse(
                {"detail": "Invalid or expired token"}, status_code=401
            )
        except RuntimeError as exc:
            logger.error("Auth misconfiguration: %s", exc)
            return JSONResponse(
                {"detail": "Server auth misconfigured"}, status_code=500
            )

        if from_cookie:
            try:
                live = await run_in_threadpool(
                    session_is_live, claims.get("session_id")
                )
            except Exception as exc:  # noqa: BLE001 - fail closed on DB errors
                logger.error("Viewer session check failed: %s", exc)
                live = False
            if not live:
                return JSONResponse(
                    {"detail": "Session has ended"}, status_code=401
                )

        # Make the authenticated user available to handlers (owner_id, etc.).
        request.state.user = claims
        return await call_next(request)


def current_user_id(request) -> str:
    """Return the Supabase user id (sub) for the current request, if any."""
    user = getattr(request.state, "user", None)
    return user.get("sub") if user else None
