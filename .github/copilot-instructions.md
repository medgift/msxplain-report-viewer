# MSXplain Report Viewer — Copilot Workspace Instructions

## Project Identity

- **Name**: MSXplain Report Viewer
- **Purpose**: Automated Multiple Sclerosis (MS) lesion segmentation, classification, uncertainty quantification, and clinical-grade report generation from brain MRI.
- **Domain**: Medical imaging / Neuroradiology / Deep Learning
- **Stack**: FastAPI (Python 3.11) + React 18 + Orthanc PACS + OHIF Viewer, Docker Compose orchestration.

---

## Repository Structure

```
/
├── docker-compose.yml              # Orchestrates all services on msxplain-network (bridge)
├── backend/
│   ├── app.py                      # FastAPI application — ALL REST endpoints
│   ├── Dockerfile                  # Multi-stage: ANTs 2.5.3 + FSL 6.0.7.4 + WMH-SynthSeg + HD-BET 1.1 + Python 3.11
│   ├── requirements.txt            # Pinned dependencies (torch 2.5.1, monai 1.4.0, lightning 2.4.0, etc.)
│   ├── files/
│   │   ├── uploads/{run_id}/       # Raw DICOM uploads per patient/session
│   │   └── processed/{run_id}/     # Pipeline outputs (NIfTI, report.csv, lesion_map, DCM-SEG)
│   ├── hd_bet_models/              # Pre-downloaded HD-BET model weights (0–4.model)
│   └── msxplain/
│       ├── msxplain_report.py      # MSXplainReport class — full pipeline orchestrator
│       ├── configs/                # MONAI bundle config, Elastix registration params
│       ├── ensemble_models/        # 5× SwinUNETR .ckpt checkpoints (seeds 1–4, 42)
│       ├── model/                  # Single UNet checkpoint (model_epoch_61.pth)
│       ├── orthanc/                # upload_to_orthanc.py — DICOM upload + segmentation management
│       ├── report_provider/        # Core ML pipeline modules
│       │   ├── predict.py          # Standard MONAI UNet inference (ROI 96³, threshold 0.3)
│       │   ├── ensemble_inference.py # SwinUNETR ensemble → pred.npz (ROI 64³, overlap 0.5)
│       │   ├── compute_uncertainty.py # Voxel/Lesion/Patient-level uncertainty
│       │   ├── parcellation_processing.py # WMH-SynthSeg + FSL brain structure masks
│       │   ├── lesion_information.py # Lesion classification + report.csv generation
│       │   ├── lesion_extraction.py  # Connected component analysis
│       │   ├── model.py           # SwinUNETR architecture (Swin Transformer + UNet decoder)
│       │   ├── datasets.py        # MONAI CacheDataset subclasses
│       │   ├── transforms.py      # MONAI transform pipelines + mask utilities
│       │   ├── data_handling.py   # NpzDataset for ensemble predictions
│       │   ├── losses.py          # Loss functions
│       │   └── metrics.py         # IoU metrics
│       ├── seglib/                 # DICOM-SEG creation library
│       │   ├── segmentation.py    # NIfTI ↔ DCM-SEG conversion
│       │   ├── helpers.py         # SimpleITK utilities, orientation matching, resampling
│       │   └── labels.py          # ROI label management
│       └── utils/utils.py         # Elastix registration param parser
├── frontend/
│   ├── Dockerfile                  # Node 22 build → nginx:alpine serve
│   ├── nginx.conf                  # Reverse proxy /api/ → msxplain_backend:5000
│   ├── package.json                # React 18, Ant Design, Axios, React Router v7
│   └── src/
│       ├── App.js                  # Routes: /, /upload, /processing, /report/:run_id/:patient/:session, /processed-runs
│       ├── components/             # HomePage, FileUpload, ProcessingStatus, ProcessedRuns, ReportPage, Viewer
│       └── context/                # ProcessingContext (activeRun, processingStatus)
└── config_ohif_orthnac/
    ├── config/
    │   ├── orthanc.json            # Orthanc PACS config (DICOMWeb, port 8042, no auth)
    │   └── nginx.conf              # OHIF viewer reverse proxy
    └── volumes/orthanc-db/         # Persistent Orthanc storage
```

---

## Service Architecture (Docker Compose)

| Service | Container | Ports | Role |
|---------|-----------|-------|------|
| `msxplain_backend` | `msxplain_backend` | 5000:5000 | FastAPI + ML pipeline (GPU) |
| `msxplain_frontend` | `msxplain_frontend` | 3001:80 | React SPA via nginx |
| `orthanc` | `msxplain_orthancPACS` | 8042:8042, 4242:4242 | DICOM PACS + DICOMWeb |
| `ohif_viewer` | *(planned)* | 80:80, 443:443 | OHIF DICOM viewer |

All services share the `msxplain-network` bridge network.

- **Frontend → Backend**: nginx proxy `/api/` → `http://msxplain_backend:5000`
- **Backend → Orthanc**: `http://orthanc:8042` (Docker service name)
- **OHIF → Orthanc**: DICOMWeb at `/dicom-web/`
- **NEVER** use `localhost` or hardcoded IPs for service-to-service communication.

---

## Data Flow (12-step pipeline)

```
1. Upload:     DICOM folders → POST /api/upload-dicoms → files/uploads/{run_id}/{patient}/{session}/
2. Trigger:    POST /api/process-scans/{run_id} → BackgroundTasks
3. Ingest:     Upload raw FLAIR+T1 DICOMs to Orthanc
4. Convert:    dcm2niix → flair.nii.gz, t1.nii.gz
5. Preprocess: fslorient → N4BiasFieldCorrection → HD-BET → ANTs rigid registration
6. Segment:    Ensemble SwinUNETR (5 models) → pred.npz  OR  UNet fallback → pred.nii.gz
7. Uncertain:  compute_uncertainties() → voxel_uncs, lesion_uncs, patient_uncs.csv, pred.nii.gz
8. Parcellate: WMH-SynthSeg → seg.nii.gz → FSL threshold → structure masks
9. Classify:   lesion_information.py → report.csv (Periventricular/Juxtacortical/Infratentorial/Deep WM/FP)
10. Register:  ANTs inverse transform → lesion_map_flair_space_ants.nii.gz
11. Export:    Segmentation → DCM-SEG (filtered, no FP) → upload to Orthanc
12. Serve:     GET /api/report/... → JSON with lesion counts, uncertainty, McDonald Criteria
```

---

## Coding Standards

### Python (Backend)

- **PEP 8** strictly. Max line length: 120.
- **Type hints** on ALL function signatures (`from typing import List, Dict, Optional, Tuple, Union`).
- **Docstrings**: Google-style on every public function/class. Include Args, Returns, Raises.
- **Logging**: Use `logging.getLogger(__name__)` — NEVER `print()`.
  - `info()` for pipeline step transitions and timing.
  - `debug()` for per-slice/per-lesion details.
  - `warning()` for recoverable issues.
  - `error()` for failures, always with `traceback.print_exc()`.
- **Error handling**: Wrap every external tool call (`subprocess`, `requests`, file I/O) in try/except. Medical data processing must NEVER silently fail.
- **Imports**: stdlib → third-party → local, separated by blank lines. Relative imports within `msxplain/`.
- **Constants**: Module-level UPPER_SNAKE_CASE. Paths via `os.path.join()` or `pathlib.Path`.

### Medical Data Handling

- **DICOM tags**: Always `getattr(ds, 'Tag', default)` — never assume a tag exists.
- **NIfTI I/O**: `nibabel` for read/write, `SimpleITK` for spatial metadata operations.
- **Orientation**: Be explicit about RAS vs LPS. Use `fslorient` or `sitk.DICOMOrientImageFilter`.
- **NumPy → JSON**: Convert via `convert_numpy_types()` before serialization.
- **Patient IDs**: Sanitize for filesystem: `''.join(c for c in pid if c.isalnum() or c in '_-')`.
- **Volume units**: Always mm³, from `img.header.get_zooms()`.

### React (Frontend)

- **Functional components** with hooks only.
- **State**: `ProcessingContext` for cross-component; local `useState`/`useEffect` otherwise.
- **API calls**: Axios to `/api/*` (nginx proxied). Handle loading, success, and error states.
- **Styling**: Component-scoped CSS. Ant Design (`antd`) as UI library.

---

## ML Pipeline Rules

- **Model weights are immutable** — never modify `ensemble_models/` or `model/` files.
- **Ensemble**: Always use ALL 5 checkpoints. Never subset.
- **Uncertainty is mandatory** when ensemble models are present. Must produce PSU and LLU values.
- **Thresholds**: Ensemble=0.5, UNet=0.3. Do not change without clinical validation.
- **Pruning**: ≤3 voxels (ensemble), <4 voxels (report). These filter noise.
- **GPU memory**: Always `torch.no_grad()` + `torch.cuda.empty_cache()` after inference.
- **Reproducibility**: All tools version-pinned in Dockerfile with commit SHAs.

---

## API Contract (DO NOT break existing endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/upload-dicoms` | Upload DICOM folder batch |
| `POST` | `/api/process-scans/{run_id}` | Trigger background processing |
| `GET` | `/api/process-status/{run_id}` | Poll processing progress |
| `GET` | `/api/processed-runs` | List all completed runs |
| `GET` | `/api/report/{run_id}/{patient_name}/{session}` | Full report JSON |

**New endpoints**: Always `/api/` prefix. try/except + JSONResponse errors. Full type hints.

---

## Docker Rules

- **Dockerfile**: Maintain multi-stage build order (ANTs copy → pip install → FSL → WMH-SynthSeg → app copy).
- **Non-root execution**: Backend runs as `msxplain` user (UID 1000).
- **GPU**: Backend container uses NVIDIA GPU reservation in Docker Compose.
- **Volumes**: `./backend/files:/app/files` persists data across restarts.
- **Version pins**: All external tools pinned by commit SHA or exact version tag.

---

## Orthanc Integration

- Upload: `POST http://orthanc:8042/instances` with `Content-Type: application/dicom`.
- Search: `POST http://orthanc:8042/tools/find` with `{Level, Query, Expand}`.
- Delete: Only SEG series matching same `StudyInstanceUID`. NEVER delete raw MR.
- DICOMWeb: Enabled at `/dicom-web/` and `/wado`. No auth.
- Config: `config_ohif_orthnac/config/orthanc.json`, image `jodogne/orthanc-plugins:1.12.10`.

---

## Key Constants

- **Lesion types**: `Periventricular`, `Juxtacortical`, `Infratentorial`, `Deep White Matter`, `False Positive`.
- **McDonald Criteria DIS**: ≥2 of the 4 non-FP regions affected → "Fulfilled".
- **Report CSV columns**: `ID, Lesion Count, Lesion Type, Lesion Index, Lesion Center, Lesion Voxels, Lesion Volume, LLU, PSU, Note`.
- **Patient path**: `files/processed/{run_id}/{patient_name}/{session}/` — always 3 levels.
- **Slice rendering**: `np.rot90` + `np.flip(axis=1)` for radiological orientation.

---

## Common Pitfalls

1. FLAIR/T1 detection is by folder name containing `flair` or `t1` (case-insensitive).
2. Background processing uses `processing_status` global dict — the only allowed mutable global.
3. DCM-SEG export filters out False Positive lesions before conversion.
4. Orthanc URLs must use Docker service name `orthanc`, never `localhost`.
5. `client_max_body_size 500M` in nginx for large DICOM uploads.
6. File uploads use 8MB chunked reads to prevent memory exhaustion.
