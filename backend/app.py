import traceback
import os
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
import time
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.background import BackgroundTasks
import uvicorn
import pandas as pd
import nibabel as nib
import numpy as np
import pydicom
import requests
from typing import List, Dict, Optional
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from msxplain.msxplain_report import MSXplainReport
from msxplain.orthanc.upload_to_orthanc import upload_to_orthanc
import scipy.stats as stats
import logging

from alembic import command
from alembic.config import Config as AlembicConfig

from auth import AuthMiddleware, current_user_id, VIEWER_COOKIE, _bearer_token
from db import crud, models
from db.engine import get_db, session_scope, wait_for_db
from db.summary import compute_report_summary

logger = logging.getLogger(__name__)

# Configure logging at application startup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def format_elapsed_time(elapsed_seconds):
    """Format elapsed time as hours, minutes, seconds"""
    hours, remainder = divmod(elapsed_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}h {int(minutes)}m {seconds:.2f}s"

def _run_migrations() -> None:
    """Apply Alembic migrations to head at startup (after the DB is reachable)."""
    wait_for_db()
    cfg = AlembicConfig(os.path.join(os.path.dirname(__file__), "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "alembic")
    )
    command.upgrade(cfg, "head")
    logger.info("Database migrations applied.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _run_migrations()
    except Exception:
        logger.error("Database migration failed at startup")
        traceback.print_exc()
        raise
    # Reconcile runs left 'processing' by a previous crash/restart: the pipeline
    # runs in-process, so none of them can still be running now.
    try:
        with session_scope() as db:
            orphaned = crud.fail_orphaned_processing_runs(db)
        if orphaned:
            logger.warning(
                "Marked %d orphaned processing run(s) as failed at startup",
                orphaned,
            )
    except Exception:
        logger.error("Could not reconcile orphaned runs at startup")
        traceback.print_exc()
    yield


# Docs are disabled in this deployment: no public /docs, /redoc or /openapi.json.
app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# GPU pipeline runs are serialized to one at a time. The single-flight guard
# lives in the DB (crud.try_start_processing, an advisory-locked check-and-set
# on Run.status), so it holds across workers/processes and survives restarts —
# unlike the previous in-memory lock.

# Define constants for file paths
UPLOAD_FOLDER = "files/uploads"
PROCESSED_FOLDER = "files/processed"

# Upload guards
MAX_UPLOAD_FILES = 20000            # per request (a DICOM series is many files)
MAX_UPLOAD_BYTES = 2 * 1024 ** 3    # 2 GiB per request

# Get CORS origins from environment variable. In production this is the single
# public origin; "*" is only for local development.
cors_origins = os.getenv("CORS_ORIGINS", "*")
allowed_origins = cors_origins.split(",") if cors_origins != "*" else ["*"]

# NOTE ON MIDDLEWARE ORDER: Starlette runs the LAST-added middleware outermost.
# AuthMiddleware is added first and CORS second, so CORS wraps auth and even a
# 401 from AuthMiddleware carries the correct CORS headers.
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Resolved absolute roots for path traversal checks
_PROCESSED_ROOT = Path(PROCESSED_FOLDER).resolve()
_UPLOAD_ROOT = Path(UPLOAD_FOLDER).resolve()


def _safe_path(root: Path, *segments: str) -> Path:
    """Resolve a path under *root* and reject traversal attempts.

    Args:
        root: The trusted root directory (already resolved).
        *segments: Untrusted path segments (e.g. run_id, patient_name, session).

    Returns:
        The resolved absolute Path.

    Raises:
        HTTPException 403: If the resolved path escapes *root*.
    """
    candidate = (root / os.path.join(*segments)).resolve()
    if not candidate.is_relative_to(root):
        raise HTTPException(status_code=403, detail="Invalid path parameters.")
    return candidate


@app.get("/api/health")
async def health():
    """Public liveness probe (allow-listed in AuthMiddleware)."""
    return {"status": "ok"}


# ── OHIF viewer: session cookie + read-only DICOMweb proxy ────────────────
# The browser-side OHIF viewer must reach Orthanc's DICOMweb, but Orthanc is
# never exposed to users. These two endpoints are the only, tightly-scoped
# bridge:
#   * POST /api/viewer-session issues a short-lived HttpOnly cookie so the
#     viewer's requests are authenticated without OHIF having to set headers.
#   * GET  /api/dicom-web/* streams QIDO/WADO reads to Orthanc (with Orthanc's
#     own credentials). Only GET is defined, so STOW uploads and DELETEs return
#     405 — the viewer can read images but never modify or export via the PACS.
VIEWER_COOKIE_MAX_AGE = 3600  # seconds; matches the Supabase token lifetime

# Dedicated audit logger. All viewer access to patient imaging flows through
# the two endpoints below, so this is the single place to record "who viewed
# what". It logs user id + study/resource UIDs only (never PHI), so the audit
# trail is itself safe to retain. Route "msxplain.audit" to its own durable
# sink in deployment if you need a separable, tamper-evident log.
audit_logger = logging.getLogger("msxplain.audit")


def _client_ip(request: Request) -> str:
    """Best-effort client IP for audit lines (real IP is behind the proxy)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


# Hop-by-hop and length/encoding headers must not be copied verbatim onto the
# streamed response (Starlette re-chunks the body itself).
_DICOMWEB_STRIP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-encoding",
    "content-length",
}


@app.post("/api/viewer-session")
def open_viewer_session(request: Request):
    """Set the HttpOnly cookie the OHIF viewer uses to authenticate DICOMweb.

    The caller is already authenticated (AuthMiddleware validated the bearer);
    we copy that access token into a cookie scoped to the DICOMweb proxy path
    so the browser attaches it automatically to same-origin viewer requests.
    OHIF itself never sees or handles the token.
    """
    token = _bearer_token(request.headers.get("Authorization", ""))
    if not token:
        # Should be unreachable (middleware requires it), but never set an
        # empty cookie.
        raise HTTPException(status_code=401, detail="Authentication required")

    # Secure flag follows the external scheme (Traefik terminates TLS and sets
    # X-Forwarded-Proto); over plain-http local dev the cookie stays non-secure
    # so the browser still stores it.
    is_https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp = Response(status_code=204)
    resp.set_cookie(
        key=VIEWER_COOKIE,
        value=token,
        max_age=VIEWER_COOKIE_MAX_AGE,
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/api/dicom-web",
    )
    audit_logger.info(
        "viewer-session opened user=%s ip=%s",
        current_user_id(request),
        _client_ip(request),
    )
    return resp


@app.get("/api/dicom-web/{path:path}")
def dicomweb_proxy(path: str, request: Request):
    """Authenticated, read-only DICOMweb passthrough to Orthanc for OHIF."""
    from msxplain.orthanc.upload_to_orthanc import ORTHANC_URL, orthanc_auth

    upstream_url = f"{ORTHANC_URL}/dicom-web/{path}"
    # Forward only content negotiation; the user's Authorization/cookie is NOT
    # forwarded — we authenticate to Orthanc with its own credentials.
    fwd_headers = {}
    accept = request.headers.get("Accept")
    if accept:
        fwd_headers["Accept"] = accept

    try:
        upstream = requests.get(
            upstream_url,
            params=list(request.query_params.multi_items()),
            headers=fwd_headers,
            auth=orthanc_auth(),
            stream=True,
            timeout=300,
        )
    except Exception as exc:
        audit_logger.warning(
            "dicomweb user=%s ip=%s status=ERROR path=%s",
            current_user_id(request), _client_ip(request), path,
        )
        logger.error(f"DICOMweb upstream error: {exc}")
        raise HTTPException(status_code=502, detail="DICOM backend unavailable.")

    # Audit trail: who fetched which DICOMweb resource (path carries the
    # study/series/instance UIDs; no PHI is logged).
    audit_logger.info(
        "dicomweb user=%s ip=%s status=%s path=%s",
        current_user_id(request),
        _client_ip(request),
        upstream.status_code,
        path,
    )

    resp_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _DICOMWEB_STRIP_HEADERS
    }
    return StreamingResponse(
        upstream.iter_content(chunk_size=64 * 1024),
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("Content-Type"),
    )


# Create a thread pool executor
thread_pool = ThreadPoolExecutor(max_workers=4)

def convert_numpy_types(data):
    # Convert numpy data types to native Python types
    if isinstance(data, pd.Series) or isinstance(data, dict):
        return {key: convert_numpy_types(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_numpy_types(value) for value in data]
    elif isinstance(data, (pd.Timestamp, pd.Timedelta)):
        return str(data)
    elif isinstance(data, (int, float, str)):
        return data
    else:
        # Convert numpy scalar types to Python native types
        if hasattr(data, "item"):
            return data.item()
    return data

def format_birth_date(date_str):
    try:
        date_obj = datetime.strptime(date_str, '%Y%m%d')
        return date_obj.strftime('%d/%m/%Y')
    except ValueError:
        return "Unknown"

# Reference distributions from the test set (used to locate a patient/lesion
# within the population via percentile rank).
#   PSU_data.csv – patient-level: columns include 'PSC' (certainty = 1 − PSU)
#   LLU_data.csv – lesion-level: column 'LLU' (uncertainty); certainty = 1 − LLU
PSU_DATA_FILEPATH = os.path.join(os.path.dirname(__file__), "msxplain", "configs", "PSU_data.csv")
LLU_DATA_FILEPATH = os.path.join(os.path.dirname(__file__), "msxplain", "configs", "LLU_data.csv")


@lru_cache(maxsize=8)
def _load_reference_certainties(filepath: str, value_col: str, invert: bool) -> Optional[np.ndarray]:
    """Load a pooled reference distribution of certainty values from the test set.

    The result is cached per (filepath, value_col, invert): reference
    distributions are static deployment artifacts, so this avoids re-parsing the
    CSV on every /api/report request. A missing file caches as None for the
    process lifetime — provision the CSV before startup, or restart after adding.

    Args:
        filepath: Path to the reference CSV.
        value_col: Column to read (e.g. 'PSC' for patient-level, 'LLU' for lesion-level).
        invert: If True, the column holds uncertainty and certainty = 1 − value.

    Returns:
        np.ndarray of certainty values (0–1), or None if unavailable.
    """
    try:
        if not os.path.exists(filepath):
            logger.warning(f"Reference distribution not found: {filepath}")
            return None
        ref_df = pd.read_csv(filepath)
        if value_col not in ref_df.columns:
            logger.warning(f"Column '{value_col}' missing in {filepath}")
            return None
        values = pd.to_numeric(ref_df[value_col], errors='coerce').dropna().to_numpy()
        if values.size == 0:
            return None
        return 1.0 - values if invert else values
    except Exception as e:
        logger.warning(f"Could not load reference distribution {filepath}: {e}")
        return None


def _percentile_of(certainty: Optional[float], reference: Optional[np.ndarray]) -> Optional[float]:
    """Return the percentile (0–100) of a certainty value within a reference distribution.

    Higher certainty → higher percentile (i.e. "X % of the population scored lower").
    Returns None when the value or reference data is unavailable.
    """
    if certainty is None or reference is None or reference.size == 0:
        return None
    try:
        return round(float(stats.percentileofscore(reference, certainty, kind='mean')), 1)
    except Exception as e:
        logger.warning(f"Could not compute percentile: {e}")
        return None


# Allowed NIfTI filenames that can be served for 3D visualization
_ALLOWED_NIFTI_FILES = frozenset({
    "flair_brain.nii.gz",
    "lesion_map_flair_space_ants.nii.gz",
    "lesion_map.nii.gz",
    "flair.nii.gz",
    "flair_brain_mask.nii.gz",
    "lesion_types.nii.gz",
})

# Lesion type → integer code (matches Orthanc DCM-SEG colour scheme)
_LESION_TYPE_CODES: Dict[str, int] = {
    "Periventricular": 1,
    "Juxtacortical": 2,
    "Infratentorial": 3,
    "Deep White Matter": 4,
}


@app.get("/api/nifti-lesion-types/{run_id}/{patient_name}/{session}")
async def get_lesion_types_nifti(run_id: str, patient_name: str, session: str):
    """Generate and serve a type-coded lesion NIfTI for 3D visualisation.

    Reads the per-instance ``lesion_map_flair_space_ants.nii.gz`` and the
    ``report.csv``, then maps every lesion voxel to a categorical type code::

        0 = background / False Positive (transparent)
        1 = Periventricular   (Dark Red   [139,   0,   0])
        2 = Juxtacortical     (Light Red  [255, 102, 102])
        3 = Infratentorial    (Dark Blue  [  0,   0, 139])
        4 = Deep White Matter (Light Blue [173, 216, 230])

    The generated file is cached on disk as ``lesion_types.nii.gz`` so
    subsequent requests are served instantly.

    Args:
        run_id (str): Processing run identifier.
        patient_name (str): Sanitised patient directory name.
        session (str): Session date directory name.

    Returns:
        FileResponse: The type-coded ``.nii.gz`` file.

    Raises:
        HTTPException 404: If the required source files are missing.
    """
    base_dir = _safe_path(_PROCESSED_ROOT, run_id, patient_name, session)
    lesion_map_path = base_dir / "lesion_map_flair_space_ants.nii.gz"
    report_path = base_dir / "report.csv"
    output_path = base_dir / "lesion_types.nii.gz"

    # Serve cached version if already generated
    if output_path.exists():
        return FileResponse(
            str(output_path),
            media_type="application/gzip",
            filename="lesion_types.nii.gz",
            headers={"Cache-Control": "max-age=3600"},
        )

    if not lesion_map_path.exists():
        raise HTTPException(status_code=404, detail="Lesion map NIfTI not found.")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report CSV not found.")

    try:
        # Build instance-ID → type-code mapping from report.csv
        report_df = pd.read_csv(report_path)
        index_to_code: Dict[int, int] = {}
        for _, row in report_df.iterrows():
            idx = int(row["Lesion Index"])
            ltype = str(row["Lesion Type"]).strip()
            index_to_code[idx] = _LESION_TYPE_CODES.get(ltype, 0)

        # Load the instance-labelled lesion map
        img = nib.load(lesion_map_path)
        data = np.asarray(img.dataobj, dtype=np.int32)

        # Remap: instance ID → categorical type code
        type_data = np.zeros_like(data, dtype=np.int8)
        for instance_id, type_code in index_to_code.items():
            type_data[data == instance_id] = type_code

        # Save the type-coded NIfTI (preserving affine + header geometry)
        type_img = nib.Nifti1Image(type_data, img.affine)
        type_img.header.set_data_dtype(np.int8)
        nib.save(type_img, str(output_path))

        logger.info(
            "Generated lesion_types.nii.gz for %s/%s/%s (%d lesions mapped)",
            run_id, patient_name, session, len(index_to_code),
        )
    except Exception as exc:
        logger.error("Failed to generate lesion_types.nii.gz: %s", exc)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Error generating lesion type map")

    return FileResponse(
        str(output_path),
        media_type="application/gzip",
        filename="lesion_types.nii.gz",
        headers={"Cache-Control": "max-age=3600"},
    )


@app.get("/api/nifti/{run_id}/{patient_name}/{session}/{filename}")
async def get_nifti_file(run_id: str, patient_name: str, session: str, filename: str):
    """Serve a NIfTI file for browser-side 3D visualization (e.g. NiiVue).

    Only a fixed allow-list of filenames is accessible to prevent arbitrary
    file disclosure.  The returned Content-Type is ``application/gzip`` so
    that ``@niivue/niivue`` can load the volume directly from the URL.

    Args:
        run_id (str): Processing run identifier.
        patient_name (str): Sanitized patient name used as the directory name.
        session (str): Session date string used as the sub-directory name.
        filename (str): Name of the NIfTI file to return (must be in allow-list).

    Returns:
        FileResponse: The raw ``.nii.gz`` file.

    Raises:
        HTTPException 403: If the requested filename is not in the allow-list.
        HTTPException 404: If the file does not exist in the processed folder.
    """
    if filename not in _ALLOWED_NIFTI_FILES:
        raise HTTPException(status_code=403, detail=f"File '{filename}' is not allowed for serving.")

    file_path = _safe_path(_PROCESSED_ROOT, run_id, patient_name, session, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"NIfTI file not found: {filename}")

    return FileResponse(
        str(file_path),
        media_type="application/gzip",
        filename=filename,
        headers={"Cache-Control": "max-age=3600"},
    )


# Route to get data from the Excel file
@app.get("/api/report/{run_id}/{patient_name}/{session}")
async def get_report(run_id: str, patient_name: str, session: str, db=Depends(get_db)):
    try:
        # Directory name (path param), captured before the DICOM read may
        # overwrite `patient_name` with the DICOM PatientName below.
        dir_patient = patient_name
        patient_dir = _safe_path(_PROCESSED_ROOT, run_id, patient_name, session)

        # Construct the correct file path using run_id and session
        file_path = os.path.join(patient_dir, f"report.csv")
        
        logger.info(f"Looking for report at: {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Report file not found: {file_path}")
            
        df = pd.read_csv(file_path)
        
        # Initialize variables
        lesion_counts = df['Lesion Type'].value_counts().to_dict()
        lesion_volume_sum = df.loc[df['Lesion Type'] != 'False Positive', 'Lesion Volume'].sum()
        
        # Convert data to native Python types
        lesion_counts = convert_numpy_types(lesion_counts)
        lesion_volume_sum = float(lesion_volume_sum)
    
        # Extract lesion numbers
        false_positives = lesion_counts.get('False Positive', 0)
        periventricular_lesions = lesion_counts.get('Periventricular', 0)
        juxtacortical_lesions = lesion_counts.get('Juxtacortical', 0)
        infratentorial_lesions = lesion_counts.get('Infratentorial', 0)
        wm_lesions = lesion_counts.get('Deep White Matter', 0)
        
        # Prefer cached demographics + study UID from the DB to skip the
        # per-request DICOM read and Orthanc query. Falls back to computing
        # (and then caching) them when the cache is cold.
        _meta = None
        try:
            _meta = crud.get_report_meta(db, run_id, dir_patient, session)
        except Exception as meta_e:
            logger.warning(f"Could not read cached report meta: {meta_e}")

        _demographics_cached = bool(
            _meta and _meta.get("patient_id") and _meta.get("birth_date")
        )
        _study_uid_cached = bool(_meta and _meta.get("study_instance_uid"))

        # Load DICOM file and extract metadata from the uploaded folder
        dicom_base_folder = os.path.join(UPLOAD_FOLDER, run_id, patient_name)

        if _demographics_cached:
            patient_name = _meta.get("display_name") or dir_patient
            patient_id = _meta.get("patient_id") or "Unknown"
            patient_birth_date = _meta.get("birth_date") or "Unknown"
            patient_sex = _meta.get("sex") or "Unknown"
        else:
            try:
                dicom_date_folder = next((f for f in os.listdir(dicom_base_folder)
                                        if os.path.isdir(os.path.join(dicom_base_folder, f))), None)
                if dicom_date_folder:
                    dicom_flair_folder = next((f for f in os.listdir(os.path.join(dicom_base_folder, dicom_date_folder))
                                             if 'flair' in f.lower()), None)
                    if dicom_flair_folder:
                        dicom_folder = os.path.join(dicom_base_folder, dicom_date_folder, dicom_flair_folder)
                        dicom_files = [f for f in os.listdir(dicom_folder)]
                        if dicom_files:
                            dicom_file_path = os.path.join(dicom_folder, dicom_files[0])
                            dicom_data = pydicom.dcmread(dicom_file_path)
                            patient_name = str(dicom_data.PatientName)
                            patient_id = str(dicom_data.PatientID)
                            patient_birth_date = format_birth_date(str(dicom_data.PatientBirthDate))
                            patient_sex = str(dicom_data.PatientSex)
                        else:
                            patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"
                    else:
                        patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"
                else:
                    patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"
            except Exception as e:
                logger.error(f"Error reading DICOM metadata: {str(e)}")
                patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"

        # Get StudyInstanceUID from Orthanc for this patient (unless cached).
        study_instance_uid = _meta.get("study_instance_uid") if _study_uid_cached else None
        if not _study_uid_cached:
            try:
                # Query Orthanc for studies by patient ID using the tools/find API
                orthanc_url = "http://orthanc:8042"

                # Use Orthanc's tools/find API to search for studies by PatientID
                search_payload = {
                    "Level": "Study",
                    "Query": {
                        "PatientID": patient_id
                    },
                    "Expand": True
                }

                from msxplain.orthanc.upload_to_orthanc import orthanc_auth
                search_response = requests.post(
                    f"{orthanc_url}/tools/find",
                    json=search_payload,
                    auth=orthanc_auth()
                )

                if search_response.status_code == 200:
                    studies = search_response.json()
                    logger.info(f"Found {len(studies)} studies for patient {patient_id}")
                    if studies:
                        # Get the StudyInstanceUID from the first study
                        first_study = studies[0]
                        study_instance_uid = first_study.get('MainDicomTags', {}).get('StudyInstanceUID')
                        logger.info(f"StudyInstanceUID: {study_instance_uid}")
                    else:
                        logger.warning(f"No studies found for patient {patient_id}")
                else:
                    logger.error(f"Failed to query Orthanc: {search_response.status_code}")
            except Exception as e:
                logger.error(f"Error retrieving StudyInstanceUID from Orthanc: {str(e)}")
                traceback.print_exc()

        # Cache freshly-computed demographics + study UID for future requests.
        if not (_demographics_cached and _study_uid_cached):
            try:
                with session_scope() as _cache_db:
                    crud.upsert_session(
                        _cache_db, run_id, dir_patient, session,
                        study_instance_uid=study_instance_uid,
                        report_csv_present=True,
                        demographics={
                            "display_name": patient_name if patient_name != "Unknown" else None,
                            "patient_id": patient_id if patient_id != "Unknown" else None,
                            "birth_date": patient_birth_date if patient_birth_date != "Unknown" else None,
                            "sex": patient_sex if patient_sex != "Unknown" else None,
                            "institution_name": None,
                        },
                    )
            except Exception as cache_e:
                logger.warning(f"Could not cache report meta: {cache_e}")

        # Check if McDonald Criteria is fulfilled
        lesion_areas = [periventricular_lesions, juxtacortical_lesions, infratentorial_lesions, wm_lesions]
        affected_areas = sum(1 for lesion in lesion_areas if lesion > 0)

        if affected_areas >= 2:
            dissemination_space = "Fulfilled"
        else:
            dissemination_space = "Not fulfilled"

        # Build certainty data from report.csv (certainty = 1 − uncertainty).
        # Percentiles locate the patient/lesions within the test-set population.
        certainty_data = {
            "patient_certainty": None,
            "patient_percentile": None,
            "lesion_type_certainties": {},
            "lesion_type_percentiles": {},
        }

        # Reference test-set distributions (certainty values, 0–1)
        psc_reference = _load_reference_certainties(PSU_DATA_FILEPATH, "PSC", invert=False)
        llc_reference = _load_reference_certainties(LLU_DATA_FILEPATH, "LLU", invert=True)

        try:
            # Get patient-level certainty (1 − PSU) from first row if available
            if 'PSU' in df.columns and not df.empty:
                psu_value = df['PSU'].iloc[0]
                if pd.notna(psu_value):
                    certainty_data["patient_certainty"] = round(1.0 - float(psu_value), 6)
                    certainty_data["patient_percentile"] = _percentile_of(
                        certainty_data["patient_certainty"], psc_reference
                    )
                    logger.info(
                        f"Patient certainty (1-PSU): {certainty_data['patient_certainty']} "
                        f"(percentile: {certainty_data['patient_percentile']})"
                    )
            
            # Calculate average lesion-level certainty for each lesion type.
            # New runs use 'LLC' (Lesion-Level Certainty, direct certainty value 0–1).
            # Old runs use 'LLU' (Lesion-Level Uncertainty, 0–1); certainty = 1 − LLU.
            lesion_col: Optional[str] = None
            use_inversion: bool = False
            if 'LLC' in df.columns:
                lesion_col = 'LLC'
                use_inversion = False
            elif 'LLU' in df.columns:
                lesion_col = 'LLU'
                use_inversion = True
                logger.info("Falling back to LLU column (old run); computing certainty as 1 − LLU")

            if lesion_col is not None:
                true_lesions_df = df[df['Lesion Type'] != 'False Positive'].copy()

                for lesion_type in ['Periventricular', 'Juxtacortical', 'Infratentorial', 'Deep White Matter']:
                    type_lesions = true_lesions_df[true_lesions_df['Lesion Type'] == lesion_type]
                    avg_certainty = None
                    if not type_lesions.empty and lesion_col in type_lesions.columns:
                        col_values = type_lesions[lesion_col].dropna()
                        if not col_values.empty:
                            avg_val = float(col_values.mean())
                            avg_certainty = round(1.0 - avg_val if use_inversion else avg_val, 6)
                            logger.debug(f"Average certainty for {lesion_type}: {avg_certainty}")
                    certainty_data["lesion_type_certainties"][lesion_type] = avg_certainty
                    certainty_data["lesion_type_percentiles"][lesion_type] = _percentile_of(
                        avg_certainty, llc_reference
                    )
                        
        except Exception as e:
            logger.warning(f"Error loading certainty data from report: {str(e)}")
            traceback.print_exc()

        # Extract scanner/acquisition metadata from dcm2niix sidecar JSONs
        scanner_info: Dict[str, Optional[str]] = {
            "manufacturer": None,
            "model": None,
            "field_strength": None,
            "institution": None,
            "software_version": None,
        }
        try:
            import json as _json
            # Try flair.json first, fall back to t1.json
            for sidecar_name in ("flair.json", "t1.json"):
                sidecar_path = os.path.join(patient_dir, sidecar_name)
                if os.path.exists(sidecar_path):
                    with open(sidecar_path, "r") as sf:
                        sidecar = _json.load(sf)
                    scanner_info["manufacturer"] = sidecar.get("Manufacturer")
                    scanner_info["model"] = sidecar.get("ManufacturersModelName") or sidecar.get("ManufacturerModelName")
                    field = sidecar.get("MagneticFieldStrength")
                    if field is not None:
                        scanner_info["field_strength"] = f"{field}T"
                    scanner_info["institution"] = sidecar.get("InstitutionName")
                    scanner_info["software_version"] = sidecar.get("SoftwareVersions")
                    logger.info(f"Loaded scanner info from {sidecar_name}: {scanner_info}")
                    break
        except Exception as e:
            logger.warning(f"Could not load scanner metadata from sidecar JSON: {e}")

        # Format response
        report_data = {
            "lesions": {
                "false_positive": false_positives if false_positives > 0 else "None",
                "periventricular": periventricular_lesions if periventricular_lesions > 0 else "None",
                "juxtacortical": juxtacortical_lesions if juxtacortical_lesions > 0 else "None",
                "infratentorial": infratentorial_lesions if infratentorial_lesions > 0 else "None",
                "wm": wm_lesions if wm_lesions > 0 else "None",
            },
            "lesion_summary": lesion_counts,  # Full count of lesion types
            "lesion_volume": lesion_volume_sum,
            "dissemination_space": dissemination_space,
            "patient_name": patient_name if patient_name else "Unknown",
            "patient_id": patient_id if patient_id else "Unknown",
            "patient_birth_date": patient_birth_date if patient_birth_date else "Unknown",
            "patient_sex": patient_sex if patient_sex else "Unknown",
            "study_instance_uid": study_instance_uid if study_instance_uid else None,
            "certainty": certainty_data,
            "scanner": scanner_info,
        }
        return report_data
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": "Error generating report"},
            status_code=500
        )


@app.post("/api/upload-dicoms")
async def upload_dicoms(
    request: Request,
    files: List[UploadFile] = File(...),
    run_id: str = None,
):
    try:
        # Use provided run_id or generate new one. Reject client-supplied
        # run_ids that try to escape the uploads root.
        if not run_id:
            run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        base_dir = _safe_path(_UPLOAD_ROOT, run_id)
        os.makedirs(base_dir, exist_ok=True)

        if len(files) > MAX_UPLOAD_FILES:
            raise HTTPException(
                status_code=413,
                detail=f"Too many files in one request (max {MAX_UPLOAD_FILES}).",
            )

        total_bytes = 0
        CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks
        for file in files:
            # file.filename is fully client-controlled. Strip the leading
            # component (the browser prepends the picked folder name) and run
            # the remaining parts through _safe_path to block traversal
            # (../, absolute paths, zip-slip) -> arbitrary file write / RCE.
            raw = file.filename or ""
            parts = [p for p in raw.split("/")[1:] if p not in ("", ".", "..")]
            if not parts:
                continue
            file_path = _safe_path(_UPLOAD_ROOT, run_id, *parts)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "wb") as buffer:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        buffer.close()
                        os.remove(file_path)
                        raise HTTPException(
                            status_code=413,
                            detail="Upload exceeds the maximum allowed size.",
                        )
                    buffer.write(chunk)

        # Get list of patient directories (top-level dirs under the run).
        patient_dirs = [
            d
            for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
        ]

        # Record the run and its patients (idempotent across chunked batches).
        owner_id = current_user_id(request)
        with session_scope() as session:
            crud.register_upload(session, run_id, patient_dirs, owner_id=owner_id)

        return JSONResponse(
            content={
                "message": "Files uploaded successfully. Batch processed.",
                "run_id": run_id,
                "patients": patient_dirs,
            },
            status_code=200,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in upload: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": "Upload failed."},
            status_code=500,
        )

@app.post("/api/process-scans/{run_id}")
async def start_processing(run_id: str, background_tasks: BackgroundTasks):
    claimed = False
    try:
        base_dir = _safe_path(_UPLOAD_ROOT, run_id)

        if not os.path.exists(base_dir):
            return JSONResponse({
                'error': f"Upload directory not found: {run_id}"
            }, status_code=404)

        # Get patient directories inside DICOMS folder
        patient_dirs = [item for item in os.listdir(base_dir)
                       if os.path.isdir(os.path.join(base_dir, item))]

        if not patient_dirs:
            return JSONResponse({
                'error': "No patient directories found"
            }, status_code=400)

        logger.info(f"Found {len(patient_dirs)} patient directories: {patient_dirs}")

        # Single-flight: atomically claim the one global processing slot (races
        # are resolved in the DB, so this holds across workers and restarts).
        # Also seeds DB status, replacing the old in-memory dict.
        with session_scope() as session:
            claimed = crud.try_start_processing(session, run_id, patient_dirs)

        if not claimed:
            with session_scope() as session:
                active = crud.get_active_processing_run(session)
            return JSONResponse({
                'error': f"Another run ({active}) is currently processing."
            }, status_code=409)

        # Add to background tasks
        background_tasks.add_task(process_all_patients, run_id, str(base_dir), patient_dirs)

        return JSONResponse({
            'message': f"Processing started for {len(patient_dirs)} patients",
            'total_patients': len(patient_dirs),
            'patients': patient_dirs
        })

    except HTTPException:
        raise
    except Exception as e:
        # Release the slot if we claimed it before failing to schedule the run.
        if claimed:
            try:
                with session_scope() as session:
                    crud.set_run_status(session, run_id, models.RUN_FAILED)
            except Exception:
                logger.error("Could not release processing slot after failure")
        logger.error(f"Error starting processing: {str(e)}")
        traceback.print_exc()
        return JSONResponse({
            'error': "Failed to start processing."
        }, status_code=500)

def process_all_patients(run_id: str, base_dir: str, patient_dirs: list):
    """Process all patients sequentially with progress updates"""

    def _set_status(patient, value):
        with session_scope() as db:
            crud.set_patient_status(db, run_id, patient, value)

    def _set_step(patient, step, value):
        with session_scope() as db:
            crud.set_patient_step(db, run_id, patient, step, value)

    try:
        logger.info(f"Starting processing for run {run_id}...")

        for i, patient_dir in enumerate(patient_dirs):
            try:
                _set_status(patient_dir, models.PROCESSING)

                logger.info(f"[{i+1}/{len(patient_dirs)}] Processing patient: {patient_dir}")
                
                # Create thread pool for CPU-intensive tasks
                with ThreadPoolExecutor(max_workers=12) as executor:
                    # Process each step in the thread pool
                    patient_path = os.path.join(base_dir, patient_dir)
                    # Get patient directories inside DICOMS folder
                    session_dirs = [item for item in os.listdir(patient_path) 
                                    if os.path.isdir(os.path.join(patient_path, item))]
                    patient_output_dir = os.path.join(PROCESSED_FOLDER, run_id, patient_dir)
                    os.makedirs(patient_output_dir, exist_ok=True)
                    
                    for session in session_dirs:
                        session_path = os.path.join(patient_path, session)
                        session_output_dir = os.path.join(patient_output_dir, session)
                        os.makedirs(session_output_dir, exist_ok=True)
                        try:
                           
                            # Start timing
                            series_start_time = time.time()
                           
                            # Find FLAIR and T1 directories
                            flair_dir, t1_dir = executor.submit(
                                find_input_directories, session_path
                            ).result()
                            
                            # Upload T1 and FLAIR DCM files to Orthanc
                            upload_to_orthanc(flair_dir)
                            upload_to_orthanc(t1_dir)

                            # Preprocessing step
                            _set_step(patient_dir, 'preprocessing', models.PROCESSING)
                            msxplain = MSXplainReport(
                                flair_dir=flair_dir,
                                t1_dir=t1_dir,
                                output_dir=session_output_dir
                            )
                            
                            nifti_files = executor.submit(
                                msxplain.convert_dicoms_to_nifti
                            ).result()
                            
                            preprocessed_files = executor.submit(
                                msxplain.preprocess_images, nifti_files
                            ).result()
                            
                            elapsed = time.time() - series_start_time
                            logger.info(f"Preprocessing completed in {format_elapsed_time(elapsed)}")
                            
                            _set_step(patient_dir, 'preprocessing', models.COMPLETED)

                            # MSXplain step

                            # Start timing
                            pipeline_start_time = time.time()

                            _set_step(patient_dir, 'msxplain', models.PROCESSING)
                            prediction_file = executor.submit(
                                msxplain.run_msxplain, preprocessed_files
                            ).result()

                            _set_step(patient_dir, 'msxplain', models.COMPLETED)

                            # Report generation step
                            _set_step(patient_dir, 'report', models.PROCESSING)
                            report_df = executor.submit(
                                msxplain.generate_report, prediction_file
                            ).result()
                            
                            labels_path = executor.submit(
                                msxplain.compute_labels, report_df
                            ).result()
                            
                            elapsed = time.time() - pipeline_start_time
                            logger.info(f"MSXplain pipeline and report generation completed in {format_elapsed_time(elapsed)}")
                            
                            # Register lesion_map to Flair original space
                            # lesion_map_flair_space = executor.submit(
                            #     msxplain.register_lesion_map_to_flair
                            # ).result()
                            
                            lesion_map_flair_space_ants = executor.submit(
                                msxplain.register_lesion_map_to_flair_ants
                            ).result()
                            
                            _set_step(patient_dir, 'report', models.COMPLETED)
                            _set_status(patient_dir, models.COMPLETED)

                            # Persist the session + its summary metrics. The DB
                            # is the source of truth for listing/status, so this
                            # must happen once the report.csv exists.
                            try:
                                summary = compute_report_summary(session_output_dir)
                                with session_scope() as db:
                                    if summary is not None:
                                        crud.upsert_report_summary(
                                            db, run_id, patient_dir, session, summary
                                        )
                                    else:
                                        crud.upsert_session(
                                            db, run_id, patient_dir, session,
                                            report_csv_present=False,
                                        )
                            except Exception as sum_e:
                                logger.warning(f"Failed to persist report summary: {sum_e}")

                            lesion_map_path = Path(os.path.join(session_output_dir, "lesion_map.nii.gz"))
                            lesion_map_flair_space_path = Path(os.path.join(session_output_dir, "lesion_map_flair_space_ants.nii.gz"))
                            
                            # Create filtered lesion maps (without False Positives) for DCM-SEG conversion
                            filtered_lesion_map_flair, flair_was_filtered = executor.submit(
                                msxplain.create_filtered_lesion_map, lesion_map_flair_space_path, report_df, "_flair_dcmseg"
                            ).result()
                            
                            filtered_lesion_map_t1, t1_was_filtered = executor.submit(
                                msxplain.create_filtered_lesion_map, lesion_map_path, report_df, "_t1_dcmseg"
                            ).result()
                            
                            # Convert segmentation to DICOM-SEG using filtered lesion maps
                            logger.info("Converting filtered NIFTI label maps to DCM SEG...")
                            executor.submit(
                                msxplain.nifti_to_dcmseg, filtered_lesion_map_flair, labels_path, Path(flair_dir), "flair"
                            ).result()
                            
                            executor.submit(
                                msxplain.nifti_to_dcmseg, filtered_lesion_map_t1, labels_path, Path(t1_dir), "t1n"
                            ).result()
                            
                            # Clean up intermediate filtered NIFTI files (only if they were created)
                            logger.info("Cleaning up intermediate filtered NIFTI files...")
                            if flair_was_filtered and os.path.exists(filtered_lesion_map_flair):
                                logger.info(f"Removing filtered file: {filtered_lesion_map_flair}")
                                os.remove(filtered_lesion_map_flair)
                            if t1_was_filtered and os.path.exists(filtered_lesion_map_t1):
                                logger.info(f"Removing filtered file: {filtered_lesion_map_t1}")
                                os.remove(filtered_lesion_map_t1)
                            
                            # ── Certainty-filtered DCM-SEG (high-confidence lesions only) ──
                            # Generates parallel DICOM SEG files that contain ONLY lesions
                            # with LLC > 0.75 (clinically validated certainty threshold).
                            try:
                                certainty_labels_path = executor.submit(
                                    msxplain.compute_uncertainty_labels, report_df, 0.25
                                ).result()

                                # Filter FLAIR-space lesion map by certainty
                                unc_flair_map, unc_flair_has_lesions = executor.submit(
                                    msxplain.create_uncertainty_filtered_lesion_map,
                                    lesion_map_flair_space_path, report_df, 0.25, "_flair_certainty"
                                ).result()

                                # Filter T1-space lesion map by certainty
                                unc_t1_map, unc_t1_has_lesions = executor.submit(
                                    msxplain.create_uncertainty_filtered_lesion_map,
                                    lesion_map_path, report_df, 0.25, "_t1_certainty"
                                ).result()

                                # Convert to DCM-SEG only if at least one lesion survived
                                if unc_flair_has_lesions:
                                    logger.info("Converting certainty-filtered FLAIR label map to DCM SEG...")
                                    executor.submit(
                                        msxplain.nifti_to_dcmseg,
                                        unc_flair_map, certainty_labels_path,
                                        Path(flair_dir), "flair_certainty"
                                    ).result()
                                else:
                                    logger.info("No high-confidence FLAIR lesions — skipping certainty DCM-SEG")

                                if unc_t1_has_lesions:
                                    logger.info("Converting certainty-filtered T1 label map to DCM SEG...")
                                    executor.submit(
                                        msxplain.nifti_to_dcmseg,
                                        unc_t1_map, certainty_labels_path,
                                        Path(t1_dir), "t1n_certainty"
                                    ).result()
                                else:
                                    logger.info("No high-confidence T1 lesions — skipping certainty DCM-SEG")

                                # Clean up intermediate certainty-filtered NIfTI files
                                for unc_path in [unc_flair_map, unc_t1_map]:
                                    if os.path.exists(unc_path):
                                        os.remove(unc_path)
                                if os.path.exists(certainty_labels_path):
                                    os.remove(certainty_labels_path)

                            except Exception as unc_e:
                                logger.warning(
                                    f"Certainty-filtered DCM-SEG generation failed "
                                    f"(non-blocking): {unc_e}"
                                )
                                traceback.print_exc()

                            # ── Brain-region overlay DCM-SEGs ──────────────
                            # Regions-only and Regions+Lesions for both FLAIR and T1.
                            # FLAIR: regions registered from T1→FLAIR via ANTs inverse.
                            # T1: regions already in native T1 space (parcellation_dir).
                            try:
                                # Register regions to FLAIR space
                                flair_regions_dir = executor.submit(
                                    msxplain.register_regions_to_flair_ants
                                ).result()

                                if flair_regions_dir is None:
                                    raise RuntimeError("Region registration to FLAIR space failed")

                                # ── FLAIR regions-only ──
                                reg_flair_nifti, reg_flair_labels, reg_flair_ok = executor.submit(
                                    msxplain.create_regions_nifti_and_labels,
                                    flair_regions_dir
                                ).result()

                                if reg_flair_ok:
                                    logger.info("Converting FLAIR regions-only NIfTI to DCM-SEG...")
                                    executor.submit(
                                        msxplain.nifti_to_dcmseg,
                                        reg_flair_nifti, reg_flair_labels,
                                        Path(flair_dir), "flair_regions"
                                    ).result()
                                else:
                                    logger.info("No FLAIR region masks — skipping regions-only DCM-SEG")

                                # ── FLAIR regions + lesions ──
                                rl_flair_nifti, rl_flair_labels, rl_flair_ok = executor.submit(
                                    msxplain.create_regions_with_lesions_nifti_and_labels,
                                    lesion_map_flair_space_path, report_df,
                                    flair_regions_dir
                                ).result()

                                if rl_flair_ok:
                                    logger.info("Converting FLAIR regions+lesions NIfTI to DCM-SEG...")
                                    executor.submit(
                                        msxplain.nifti_to_dcmseg,
                                        rl_flair_nifti, rl_flair_labels,
                                        Path(flair_dir), "flair_regions_lesions"
                                    ).result()
                                else:
                                    logger.info("No FLAIR regions+lesions content — skipping DCM-SEG")

                                # ── T1 regions-only (native T1 space) ──
                                reg_t1_nifti, reg_t1_labels, reg_t1_ok = executor.submit(
                                    msxplain.create_regions_nifti_and_labels,
                                    None  # uses parcellation_dir (T1 space)
                                ).result()

                                if reg_t1_ok:
                                    logger.info("Converting T1 regions-only NIfTI to DCM-SEG...")
                                    executor.submit(
                                        msxplain.nifti_to_dcmseg,
                                        reg_t1_nifti, reg_t1_labels,
                                        Path(t1_dir), "t1n_regions"
                                    ).result()
                                else:
                                    logger.info("No T1 region masks — skipping regions-only DCM-SEG")

                                # ── T1 regions + lesions ──
                                rl_t1_nifti, rl_t1_labels, rl_t1_ok = executor.submit(
                                    msxplain.create_regions_with_lesions_nifti_and_labels,
                                    lesion_map_path, report_df,
                                    None  # uses parcellation_dir (T1 space)
                                ).result()

                                if rl_t1_ok:
                                    logger.info("Converting T1 regions+lesions NIfTI to DCM-SEG...")
                                    executor.submit(
                                        msxplain.nifti_to_dcmseg,
                                        rl_t1_nifti, rl_t1_labels,
                                        Path(t1_dir), "t1n_regions_lesions"
                                    ).result()
                                else:
                                    logger.info("No T1 regions+lesions content — skipping DCM-SEG")

                                # Clean up intermediate NIfTI/labels files
                                for tmp in [
                                    reg_flair_nifti, reg_flair_labels,
                                    rl_flair_nifti, rl_flair_labels,
                                    reg_t1_nifti, reg_t1_labels,
                                    rl_t1_nifti, rl_t1_labels,
                                ]:
                                    if tmp and os.path.exists(tmp):
                                        os.remove(tmp)

                            except Exception as reg_e:
                                logger.warning(
                                    f"Region overlay DCM-SEG generation failed "
                                    f"(non-blocking): {reg_e}"
                                )
                                traceback.print_exc()

                            # Upload ALL DCM-SEG outputs to Orthanc
                            # (includes original, certainty-filtered, and region overlays)
                            upload_to_orthanc(session_output_dir)
                            
                            elapsed = time.time() - series_start_time
                            logger.info(f"Complete series processing finished in {format_elapsed_time(elapsed)}")

                        except Exception as e:
                            logger.error(f"Error processing session {session} for patient {patient_dir}: {str(e)}")
                            traceback.print_exc()

            except Exception as e:
                logger.error(f"Error processing patient {patient_dir}: {str(e)}")
                traceback.print_exc()
                _set_status(patient_dir, models.FAILED)

        logger.info(f"All processing completed for run {run_id}")
        with session_scope() as db:
            crud.set_run_status(db, run_id, models.RUN_DONE)

    except Exception as e:
        logger.error(f"Error in process_all_patients: {str(e)}")
        traceback.print_exc()
        try:
            with session_scope() as db:
                crud.set_run_status(db, run_id, models.RUN_FAILED)
        except Exception:
            logger.error("Could not mark run failed")
    # The single-flight slot is released implicitly: the run is no longer in
    # 'processing' status once it reaches 'done' or 'failed' above.

def find_input_directories(patient_path):
    """Helper function to find FLAIR and T1 directories"""
    flair_dir = None
    t1_dir = None
    
    for root, dirs, files in os.walk(patient_path):
        dir_name = os.path.basename(root).lower()
        if 'flair' in dir_name and not flair_dir:
            flair_dir = root
        elif 't1' in dir_name and not t1_dir:
            t1_dir = root
        if flair_dir and t1_dir:
            break
            
    if not flair_dir or not t1_dir:
        raise ValueError(f"Could not find FLAIR and T1 directories in {patient_path}")
        
    return flair_dir, t1_dir


@app.get("/api/process-status/{run_id}")
def get_process_status(run_id: str, db=Depends(get_db)):
    try:
        logger.debug(f"Getting status for run: {run_id}")

        # DB is the source of truth and survives restarts.
        status = crud.get_run_status_json(db, run_id)
        if status is not None:
            return status

        # Run not found anywhere.
        return JSONResponse({
            'message': f'Run {run_id} not found',
            'status': 'inactive',
            'total_patients': 0,
            'patients': {}
        })

    except Exception as e:
        logger.error(f"Error getting process status: {str(e)}")
        traceback.print_exc()
        return JSONResponse({
            'error': "Error getting process status.",
            'status': 'error'
        }, status_code=500)

@app.get("/api/processed-runs")
def get_processed_runs(db=Depends(get_db)):
    try:
        # Indexed DB read (ordered newest-first); replaces the os.walk scan.
        return crud.list_runs_json(db)
    except Exception as e:
        logger.error(f"Error getting processed runs: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": "Error getting processed runs."},
            status_code=500
        )

def main():
    """Run the FastAPI application"""
    uvicorn.run(app, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
