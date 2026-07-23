"""Supabase (GoTrue) JWT verification and a fail-closed auth middleware.

GoTrue signs access tokens symmetrically (HS256) with a shared secret, so we
verify with that secret — there is no JWKS endpoint to fetch.

The middleware runs for *every* request and denies anything under ``/api/``
that isn't in ``PUBLIC_PATHS`` and doesn't carry a valid bearer token. Being a
global middleware (rather than per-route dependencies) is the mechanical
guarantee that no new route can be added unauthenticated by mistake.
"""
import os
import logging

import jwt
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
        # DICOMweb requests from the OHIF tab carry the session cookie instead
        # of a bearer header. The cookie value is itself a Supabase JWT, so it
        # goes through the exact same verification below.
        if not token and path.startswith(DICOMWEB_PREFIX):
            token = request.cookies.get(VIEWER_COOKIE) or None
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

        # Make the authenticated user available to handlers (owner_id, etc.).
        request.state.user = claims
        return await call_next(request)


def current_user_id(request) -> str:
    """Return the Supabase user id (sub) for the current request, if any."""
    user = getattr(request.state, "user", None)
    return user.get("sub") if user else None
