# Orthanc & OHIF Integration Skill

You are working on the Orthanc PACS and OHIF DICOM viewer integration for the MSXplain application. This connects the ML pipeline outputs to clinical visualization tools.

## Current Architecture

### Orthanc PACS

- **Container**: `msxplain_orthancPACS`, image `jodogne/orthanc-plugins:1.12.10`
- **Network**: `msxplain-network` bridge, hostname `orthanc`
- **REST API**: `http://orthanc:8042` (from backend), `http://localhost:8042` (from host)
- **DICOM port**: 4242, AE Title: `ORTHANC`
- **DICOMWeb**: Enabled at `/dicom-web/`, WADO at `/wado`
- **Config**: `config_ohif_orthnac/config/orthanc.json`
- **Storage**: SQLite at `/var/lib/orthanc/db/` (volume-mounted from `config_ohif_orthnac/volumes/orthanc-db/`)
- **Authentication**: None (research/internal deployment)
- **Threads**: 50 HTTP threads, metrics enabled

### OHIF Viewer (Planned — currently commented out in docker-compose.yml)

- **Image**: `lluisb3/ohif-webapp:latest`
- **Ports**: 80 (HTTP), 443 (SSL)
- **nginx config**: `config_ohif_orthnac/config/nginx.conf`
  - `/pacs/` → proxied to `http://orthanc:8042/` with CORS headers
  - `/` → serves static SPA from `/var/www/html`
- **Depends on**: `orthanc` service

### Upload Flow (`backend/msxplain/orthanc/upload_to_orthanc.py`)

```python
# 1. Health check
GET /system → verify Orthanc is responsive

# 2. Find DICOM files recursively (validated via pydicom.dcmread)

# 3. If uploading segmentations: delete existing SEG series for same StudyInstanceUID
POST /tools/find → find patient → iterate studies → match StudyInstanceUID → find SEG series → DELETE /series/{id}

# 4. Upload each DICOM file
POST /instances (Content-Type: application/dicom) → upload file bytes
```

### Query Flow (`backend/app.py`)

```python
# Search studies by PatientID
POST http://orthanc:8042/tools/find
Body: {"Level": "Study", "Query": {"PatientID": "..."}, "Expand": True}
→ Extract StudyInstanceUID from response[0]["MainDicomTags"]["StudyInstanceUID"]
```

### Frontend Integration

- `ReportPage.js`: "View Images" button constructs OHIF URL with StudyInstanceUID
- Report JSON includes `study_instance_uid` field fetched from Orthanc

### DICOM SEG Creation (`seglib/segmentation.py`)

- Uses `pydicom-seg` to create DICOM SEG from labeled NIfTI
- Labels come from `labels.csv` (roi_id, roi_name)
- False Positive lesions are EXCLUDED via `create_filtered_lesion_map()` before conversion
- Separate DCM-SEG files for FLAIR-space and T1-space label maps
- Label names include uncertainty: `"Periventricular (0.123)"` when LLU available

## Strict Rules

1. **Always use Docker service name** `orthanc` for backend→Orthanc communication. NEVER `localhost`.
2. **Never delete raw MR series** — only SEG modality series. Always check `Modality` tag.
3. **Match StudyInstanceUID** before any delete to avoid cross-session data loss.
4. **Orthanc unavailability must NOT crash the pipeline** — log errors and continue.
5. **DICOM metadata access**: Always via `getattr(ds, 'Tag', default)` — never assume tags exist.
6. **DICOMWeb compliance**: Use WADO-RS/STOW-RS/QIDO-RS standard paths.
7. **OHIF nginx CORS**: Maintain CORS headers on the `/pacs/` proxy.
8. **Volume persistence**: Never modify the Orthanc DB mount point path.
9. **Version pin**: Keep `jodogne/orthanc-plugins:1.12.10` — do not upgrade without testing DICOMWeb compatibility.
10. **Segmentation upload order**: Always delete old SEGs first, then upload new ones, within the same StudyInstanceUID scope.

## Output Requirements

- Modified Python files or Docker/nginx configs as needed.
- If modifying `orthanc.json`: document each change with a comment explaining why.
- If enabling OHIF: uncomment and update `docker-compose.yml`, verify nginx proxy paths.
- If adding Orthanc queries: use `POST /tools/find` with Level/Query/Expand pattern.
- Provide `curl` commands to verify integration works.
