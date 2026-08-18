"""Authorization invariants: strict per-user isolation on run-scoped routes.

test_auth_routes locks in *authentication* (is the caller logged in?). This
suite locks in *authorization* (may THIS caller see THIS run?), the gap that
previously let any authenticated user read every other user's runs, reports and
imaging:

  * the DICOMweb proxy path guard that blocks escaping the /dicom-web/ namespace
    onto Orthanc's raw REST API (the confirmed ../../studies/{id}/archive
    full-study download);
  * the study-UID extraction that feeds the per-study ownership check;
  * the wiring that every run-scoped route receives the ``request`` it needs to
    resolve the owner (so scoping can't be silently dropped on a future edit).

DB-level ownership (crud.run_owned_by / user_owns_studies) is exercised by the
integration suite against Postgres; the models are Postgres-specific (schema,
gen_random_uuid, dialect UUID) so they are not unit-tested on SQLite here.

Run inside the backend environment:  pytest backend/tests
"""
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")

from fastapi import HTTPException  # noqa: E402
from starlette.datastructures import QueryParams  # noqa: E402

import app as app_module  # noqa: E402


# ── DICOMweb proxy path guard (path-traversal / REST-escape) ──────────────
# Well-formed DICOMweb paths the *path validator* must accept (it only blocks
# traversal / namespace escape). Passing the path guard is NOT authorization:
# a request still has to resolve to a study the caller owns (user_owns_studies),
# and non-study-rooted paths like `series/...`/`instances/...` resolve to no
# study and are then refused with a 404 by the proxy. OHIF in this deep-linked,
# wadors config only ever issues study-rooted requests.
_LEGIT_PATHS = [
    "studies",
    "studies/1.2.840/series",
    "studies/1.2.840/series/1.3/instances/1.9/frames/1",
    "studies/1.2/metadata",
    "series/1.2.3",
    "instances/1.2.3/rendered",
]

# Traversal / REST-escape / malformed; all must be rejected.
_ATTACK_PATHS = [
    "../../studies/x/archive",   # confirmed exploit: full-study ZIP download
    "../studies",
    "studies/../../patients",
    "/studies",
    "patients/1/media",          # non-DICOMweb Orthanc REST root
    "tools/find",
    "studies/x/../../../instances",
    "studies//archive",          # empty segment
    "",
    "studies\\..\\..",           # backslash traversal
]


@pytest.mark.parametrize("path", _LEGIT_PATHS)
def test_validate_dicomweb_path_accepts_ohif_requests(path):
    app_module._validate_dicomweb_path(path)  # must not raise


@pytest.mark.parametrize("path", _ATTACK_PATHS)
def test_validate_dicomweb_path_blocks_traversal(path):
    with pytest.raises(HTTPException):
        app_module._validate_dicomweb_path(path)


# ── study-UID extraction feeding the ownership check ──────────────────────
def test_study_uids_extracted_from_path():
    assert app_module._dicomweb_study_uids(
        "studies/1.2.3/series", QueryParams("")
    ) == {"1.2.3"}
    assert app_module._dicomweb_study_uids(
        "studies/1.2.3", QueryParams("")
    ) == {"1.2.3"}


def test_study_uids_extracted_from_qido_query():
    # Both the plural (OHIF) and singular (QIDO standard) key names, and the
    # comma-separated multi-UID form, must be picked up.
    assert app_module._dicomweb_study_uids(
        "studies", QueryParams("StudyInstanceUIDs=9.9.9")
    ) == {"9.9.9"}
    assert app_module._dicomweb_study_uids(
        "studies", QueryParams("StudyInstanceUID=9.9.9")
    ) == {"9.9.9"}
    assert app_module._dicomweb_study_uids(
        "studies", QueryParams("StudyInstanceUIDs=a,b")
    ) == {"a", "b"}


def test_study_uids_empty_for_unscoped_requests():
    # Bare enumeration and non-study roots resolve to no study, which the proxy
    # treats as forbidden (fail-closed) rather than proxying cross-tenant data.
    assert app_module._dicomweb_study_uids("studies", QueryParams("")) == set()
    assert app_module._dicomweb_study_uids(
        "studies", QueryParams("limit=10")
    ) == set()
    assert app_module._dicomweb_study_uids("series/1.2.3", QueryParams("")) == set()
    assert app_module._dicomweb_study_uids(
        "instances/1.2.3", QueryParams("")
    ) == set()


# ── wiring: run-scoped routes must enforce ownership ──────────────────────
def _route(path):
    for r in app_module.app.routes:
        if getattr(r, "path", None) == path:
            return r
    return None


def _route_dep_calls(route):
    """Every dependency callable (recursively) wired into a route."""
    calls = set()

    def walk(dep):
        for sub in dep.dependencies:
            if sub.call is not None:
                calls.add(sub.call)
            walk(sub)

    walk(route.dependant)
    return calls


# Read routes enforce isolation through the shared dependency, so the check
# can't be forgotten. Lock in that Depends(require_run_owner) is wired in.
_OWNER_DEP_ROUTES = {
    "/api/report/{run_id}/{patient_name}/{session}",
    "/api/nifti/{run_id}/{patient_name}/{session}/{filename}",
    "/api/nifti-lesion-types/{run_id}/{patient_name}/{session}",
}


@pytest.mark.parametrize("path", sorted(_OWNER_DEP_ROUTES))
def test_read_route_enforces_owner_dependency(path):
    route = _route(path)
    assert route is not None, f"{path} must be registered"
    assert app_module.require_run_owner in _route_dep_calls(route), (
        f"{path} must enforce ownership via Depends(require_run_owner)"
    )


# These routes do their own ownership/study checks (different responses, write
# semantics, or study-UID scoping), so they need `request` to resolve the
# caller. Lock the parameter in so scoping can't be silently dropped.
_SELF_CHECK_ROUTES = {
    "/api/process-status/{run_id}",
    "/api/processed-runs",
    "/api/process-scans/{run_id}",
    "/api/dicom-web/{path:path}",
    "/api/upload-dicoms",
}


@pytest.mark.parametrize("path", sorted(_SELF_CHECK_ROUTES))
def test_self_check_route_receives_request(path):
    route = _route(path)
    assert route is not None, f"{path} must be registered"
    params = inspect.signature(route.endpoint).parameters
    assert "request" in params, (
        f"{path} must take `request` to resolve the caller for its owner check"
    )
