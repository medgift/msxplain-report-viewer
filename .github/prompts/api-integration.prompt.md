# API & Integration Development Skill

You are working on the FastAPI backend REST API and React frontend integration for the MSXplain MS lesion analysis application.

## Backend Architecture

- **Framework**: FastAPI in `backend/app.py`, served by Uvicorn on port 5000
- **CORS**: Configured globally via `CORS_ORIGINS` env var (default `*`)
- **Background tasks**: Long processing via FastAPI `BackgroundTasks`, status tracked in global `processing_status` dict
- **File layout**: `files/uploads/{run_id}/` (raw DICOMs), `files/processed/{run_id}/` (pipeline outputs)

### Existing Endpoints (NEVER break these contracts)

| Method | Path | Input | Output |
|--------|------|-------|--------|
| `POST` | `/api/upload-dicoms` | Multipart `files[]` + optional `run_id` query | `{message, run_id, patients[]}` |
| `POST` | `/api/process-scans/{run_id}` | Path param | `{message, total_patients, patients[]}` |
| `GET` | `/api/process-status/{run_id}` | Path param | `{total_patients, patients: {status, steps: {preprocessing, msxplain, report}}}` |
| `GET` | `/api/processed-runs` | None | `[{id, date, patients: [{id, sessions, status}], total_patients, total_sessions}]` |
| `GET` | `/api/report/{run_id}/{patient_name}/{session}` | Path params | `{lesions, lesion_summary, lesion_volume, dissemination_space, patient_name, patient_id, patient_birth_date, patient_sex, study_instance_uid, uncertainty: {patient_uncertainty, lesion_type_uncertainties}}` |
| `GET` | `/api/total_lesions/{run_id}/{patient_name}` | Path params | `{total_lesions, true_lesions, false_positives, lesion_types}` |
| `GET` | `/api/slice/{run_id}/{patient_name}/{slice_num}` | Path + `show_false_positives` query bool | PNG bytes, headers: `X-Total-Slices` |

### Key Patterns in `app.py`

```python
# Numpy → JSON conversion (required before all JSON responses with numeric data)
def convert_numpy_types(data): ...

# Background processing with status updates
processing_status[run_id]['patients'][patient_dir]['steps']['preprocessing'] = 'processing'
# ... do work ...
processing_status[run_id]['patients'][patient_dir]['steps']['preprocessing'] = 'completed'

# Error response pattern
return JSONResponse(content={"error": str(e)}, status_code=500)

# Image response pattern
return Response(content=byte_io.getvalue(), media_type="image/png",
                headers={"X-Total-Slices": str(total)})
```

### Thread Pool for CPU-bound Work

```python
with ThreadPoolExecutor(max_workers=12) as executor:
    result = executor.submit(some_function, args).result()
```

## Frontend Architecture

- **React 18** with React Router v7
- **UI Library**: Ant Design (`antd`)
- **HTTP Client**: Axios to `/api/*` (nginx proxied)
- **State**: `ProcessingContext` provides `activeRun` and `processingStatus` via React Context

### Routes (`App.js`)

| Path | Component |
|------|-----------|
| `/` | `HomePage` |
| `/upload` | `FileUpload` |
| `/processing` | `ProcessingStatus` |
| `/report/:run_id/:patient_name/:session` | `ReportPage` |
| `/processed-runs` | `ProcessedRuns` |

### Component Patterns

- `FileUpload.js`: Batch upload (100 files/batch), progress bar, triggers processing
- `ProcessingStatus.js`: 3-second polling with emoji status indicators
- `ReportPage.js`: Displays lesion report, uncertainty data, McDonald Criteria, OHIF viewer link
- `Viewer.js`: 2D slice navigation with color-coded lesion overlay + false positive toggle
- `ProcessedRuns.js`: Lists runs with per-patient session cards

### nginx Proxy (`frontend/nginx.conf`)

```nginx
location /api/ {
    proxy_pass http://msxplain_backend:5000;
    proxy_read_timeout 300s;
    # CORS preflight handled here
}
client_max_body_size 500M;
```

## Strict Rules

1. **All new endpoints** MUST be prefixed with `/api/`.
2. **Never break** existing endpoint response schemas — add fields, never remove/rename.
3. **Type hints** on ALL endpoint function signatures.
4. **Error responses**: Always `JSONResponse(content={"error": ...}, status_code=...)` with try/except.
5. **NumPy → JSON**: Use `convert_numpy_types()` for any data containing numpy scalars/arrays.
6. **Long operations**: Use `BackgroundTasks` and update `processing_status` dict.
7. **File responses**: `Response(content=bytes, media_type=...)` with descriptive headers.
8. **Frontend API calls**: Axios with relative paths (`/api/...`). Always implement loading + error states.
9. **CORS**: Handled globally in middleware — do not add per-endpoint CORS headers.
10. **Logging**: `logger.info()` for requests, `logger.error()` + `traceback.print_exc()` for failures.
11. **New routes**: Add to `App.js` router and create component file + CSS in `components/`.
12. **Patient path convention**: `{run_id}/{patient_name}/{session}` — always these 3 levels.

## Output Requirements

- Backend: New/modified endpoints in `app.py` with full type hints, docstrings, try/except.
- Frontend: Component files with Axios calls, loading/error state handling.
- If adding routes: update `App.js` with the new `<Route>`.
- If modifying proxy behavior: update `frontend/nginx.conf`.
- Provide example `curl` commands for testing new endpoints.
