# MSXplain Report Viewer

A web-based application for processing and viewing Multiple Sclerosis (MS) brain MRI scans with automated lesion detection and reporting.

## 1. Overview

### Version History
- **v1.0**: First approach to create the report from the results of MSReport-Provider and a handcraft Viewer with the axial plane with the lesion map overlapping
- **v2.0**: Incorporation of the MSReport Provider Pipeline (Preprocessing, MSXplain Report Provider, Report generator). A new upload page allows users to upload folders containing multiple patients following the required structure: Folder/Patients/Session/Images (T1 and FLAIR).
- **v3.0**: Complete incorporation of Report Provider with skull stripping, updating the model, converting the lesion_map to dicom_seg, and registering to flair space. Start the incorporation of the OHIF Viewer + Orthanc.
- **v4.0**: Fully dockerized application with complete integration of OHIF Viewer and Orthanc PACS. All components run in Docker containers with proper user permissions. Image registration now uses ANTs tools instead of elastix for improved performance and consistency.
- **v5.0**: Replaced FreeSurfer/SAMSEG parcellation with WMH-SynthSeg for faster and lighter brain structure segmentation. Added SwinUNETR ensemble inference (5 models) with voxel-level, lesion-level (LLU), and patient-level (PSU) uncertainty quantification. Uncertainty-filtered DICOM-SEG exports (LLU < 0.25 threshold). Upgraded to Python 3.11, PyTorch 2.7 (CUDA 12.8), pytorch-lightning 2.6, and MONAI 1.4. Built dcm2niix from source with JPEG 2000 and JPEG-LS support. False Positive lesions are now excluded from DICOM-SEG exports while remaining visible in the web report.
- **v5.1**: Replace uncertainty with certainty and add a plot showing the certainty distribution for the test set in the report. Upload to Orthanc a mask with the 4 important atlas regions.
- **v5.2**: Added 3D brain visualisation in the report page using a Brain3DViewer component. New backend endpoints serve NIfTI files and generate type-coded lesion maps (Periventricular, Juxtacortical, Infratentorial, Deep White Matter) for interactive 3D rendering. Removed hardcoded follow-up and assessment sections from the report.
- **v5.3**: Redesigned the report page into a horizontal, single-screen dashboard that puts the most important results above the fold on a typical widescreen display: a patient-info strip, a patient-level band (wide 3D/MPR viewer + certainty plot) and a lesion-level band (region findings + certainty plot), with the McDonald criteria, technique and atrophy below. Replaced the backend-rendered matplotlib certainty histogram with new frontend-rendered SVG gaussian plots (`CertaintyGaussian`): a fixed bell curve where the patient (and each lesion type) is placed by its percentile within the test population, annotated with quartile lines (Q1–Q3) and a central 95%-interval bracket, plus an info tooltip explaining the reference distribution. The backend `/api/report` endpoint now returns patient- and lesion-level percentiles computed from `PSU_data.csv` (patient-level) and `LLU_data.csv` (pooled lesion-level), and the obsolete `/api/certainty-histogram` endpoint and matplotlib dependency were removed.

### Repository Structure
```
.
├── backend/              # FastAPI server with MSXplain processing pipeline
│   ├── app.py           # Main FastAPI application
│   ├── msxplain/        # MSXplain report provider modules
│   ├── files/           # Data directory (uploads, processed)
│   └── hd_bet_models/   # Brain extraction models
├── frontend/            # React web application
│   ├── src/             # React components and logic
│   └── public/          # Static assets
├── config_ohif_orthnac/ # OHIF Viewer and Orthanc PACS configuration
├── docker-compose.yml   # Docker orchestration configuration
└── .env                 # Environment configuration (user-specific)
```

## 2. Prerequisites

- Docker Engine installed
- **For GPU Support (Optional but Recommended):**
  - NVIDIA GPU with compatible drivers
  - NVIDIA Docker runtime installed (see section 4.3 below for installation)
- At least 8GB RAM (16GB recommended)
- 50GB+ free disk space for processing data

## 3. Installation & Setup

### 3.1 Neuroimaging Tools Included

The backend Docker image includes the following neuroimaging tools using **official Docker images** for optimal performance:

1. **FSL 6.0.7.4** - FMRIB Software Library for brain imaging analysis
2. **WMH-SynthSeg** - White matter hyperintensity and brain structure segmentation (replaces FreeSurfer/SAMSEG)
3. **ANTs 2.5.3** - Advanced Normalization Tools for image registration and transformation *(from official `antsx/ants:2.5.3`)*
4. **dcm2niix** - DICOM to NIfTI conversion (built from source with JPEG 2000 and JPEG-LS support)
5. **HD-BET 1.1** - Brain extraction tool

### 3.2 Environment Configuration

**Important**: The application runs as the user specified in the `.env` file. This ensures that all files created by the Docker containers have the correct permissions and can be accessed by your host user.

**First Time Setup:**

1. Create your `.env` file from the example:
```bash
cp .env.example .env
```

2. Edit `.env` with your user configuration:
```bash
# Set your user ID and group ID (important for file permissions!)
# Run these commands to get your values:
id -u  # Your user ID
id -g  # Your group ID

# Edit .env and set:
UID=1000     # Replace with your user ID
GID=1000     # Replace with your group ID
```

Or create it automatically:
```bash
echo "UID=$(id -u)" > .env
echo "GID=$(id -g)" >> .env
```

3. Configure additional options in `.env` (optional):
```bash
# Port Configuration
FRONTEND_PORT=3001          # Web interface port
BACKEND_PORT=5000           # API server port
ORTHANC_HTTP_PORT=8042      # PACS web interface
ORTHANC_DICOM_PORT=4242     # DICOM protocol port

# CORS Configuration
CORS_ORIGINS=*              # For development: allow all origins
# CORS_ORIGINS=http://your-server:3001  # For production: specify exact origins
```

### 3.3 Required Files and Directories

Before building, ensure these files are in place:

**Backend:**
- `backend/msxplain/model/*` - MSXplain UNet model weights
- `backend/msxplain/ensemble_models/*` - SwinUNETR ensemble checkpoints (5 models)
- `backend/hd_bet_models/*` - Brain extraction models
- `backend/msxplain/configs/PSU_data.csv` - Reference patient-level distribution (test set) used to place the patient on the patient-level certainty plot (not tracked in git; obtain separately)
- `backend/msxplain/configs/LLU_data.csv` - Reference lesion-level distribution (test set) used to place each lesion type on the lesion-level certainty plot (not tracked in git; obtain separately)

**Frontend:**
- `frontend/public/*` - Static assets

Create necessary data directories:
```bash
mkdir -p backend/files/uploads
mkdir -p backend/files/processed
```

**Important**: These directories will be owned by the user specified in `.env` (UID:GID), ensuring proper permissions.

### 3.4 Starting the Application

```bash
# Build and start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### 3.5 Accessing the Application

Once running, access these services:
- **Frontend Web UI**: http://localhost:3001 (or http://YOUR_SERVER_IP:3001)
- **Backend API**: http://localhost:5000
- **Orthanc PACS**: http://localhost:8042
- **Orthanc DICOM**: port 4242

Default Orthanc credentials: `orthanc` / `orthanc` (configure in `config_ohif_orthnac/config/orthanc.json`)

## 4. Docker Architecture

### 4.1 Fully Dockerized Application

The entire MSXplain application runs in Docker containers, providing:

- **Isolation**: Each component runs in its own container with specific dependencies
- **Reproducibility**: Same environment across development and production
- **Portability**: Easy deployment on any system with Docker
- **User Permissions**: Containers run as your host user (UID/GID from `.env`) to ensure:
  - Files created by containers are owned by your user
  - No permission issues when accessing files from host
  - Safe file system operations without root privileges

**Container Services:**

1. **msxplain_backend** (FastAPI + Python)
   - Runs as user `UID:GID` specified in `.env`
   - Processes MRI scans using neuroimaging tools
   - Includes: FSL, WMH-SynthSeg, ANTs, HD-BET, PyTorch
   - GPU-enabled (optional) for faster processing
   - Data persisted in `./backend/files` volume

2. **msxplain_frontend** (React + Nginx)
   - Serves web interface on port 3001
   - Communicates with backend API
   - Static files built and served by Nginx

3. **orthanc** (PACS Server)
   - DICOM image storage and retrieval
   - Web viewer on port 8042
   - DICOM protocol on port 4242
   - Data persisted in `./config_ohif_orthnac/volumes/orthanc-db`

**Volume Mounts:**
```
Host                              →  Container
./backend/files                   →  /app/files              (Data persistence)
./config_ohif_orthnac/volumes     →  /var/lib/orthanc/db/   (PACS data)
```

All volumes maintain your host user ownership, preventing permission conflicts.

### 4.2 Building Images

**Build all images:**
```bash
docker compose build
```

**Build specific service:**
```bash
docker compose build msxplain_backend
docker compose build msxplain_frontend
```

**Rebuild without cache (if needed):**
```bash
docker compose build --no-cache msxplain_frontend
```

### 4.3 GPU Support (Optional but Recommended)

**Note**: The Docker images are already GPU-ready with CUDA libraries. You only need to install NVIDIA Docker runtime on your host computer to enable GPU passthrough to containers.

**What's already in the Docker images:**
- ✅ CUDA 12.8 runtime libraries (via PyTorch)
- ✅ GPU-enabled PyTorch 2.7 and MONAI 1.4
- ✅ All necessary CUDA dependencies

**Requirements on your host computer:**
- NVIDIA GPU with recent drivers
- NVIDIA Docker runtime

**Installation steps for your host machine:**

1. **Install NVIDIA Docker runtime:**
   ```bash
   # Ubuntu/Debian
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   sudo apt-get update && sudo apt-get install -y nvidia-docker2
   sudo systemctl restart docker
   ```

2. **Test GPU access:**
   ```bash
   # This should show your GPU info
   docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
   ```

3. **Enable GPU in docker-compose.yml:**
   The GPU configuration is already present in `docker-compose.yml`. It's enabled by default:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: all
             capabilities: [gpu]
   ```

### 4.4 Environment Variables

The dockerized application uses environment variables instead of configuration files. All neuroimaging tool paths are automatically configured in the Docker container:

**Environment variables set in backend container:**
- `FSLDIR=/usr/share/fsl` - FSL installation directory
- `FSLOUTPUTTYPE=NIFTI_GZ` - FSL output format
- `WMHSYNTHSEG_HOME=/app/wmh_synthseg` - WMH-SynthSeg installation directory
- `ANTSPATH=/opt/ants/bin` - ANTs binaries directory
- `ORTHANC_URL=http://orthanc:8042` - Orthanc PACS server URL
- `PYTHONPATH=/app` - Python module path
- `CORS_ORIGINS` - Set via `.env` file for API access control

**Note**: After dockerization (v4.0), the application no longer uses `config.yml`. All paths are hardcoded in the Docker container for consistency and reproducibility.

## 5. Troubleshooting

### Permission Issues

If you encounter permission denied errors:

1. **Check your `.env` file:**
   ```bash
   cat .env
   # Should show your actual UID and GID
   ```

2. **Fix ownership of existing files:**
   ```bash
   sudo chown -R $(id -u):$(id -g) backend/files
   sudo chown -R $(id -u):$(id -g) config_ohif_orthnac/volumes
   ```

3. **Restart containers:**
   ```bash
   docker compose down
   docker compose up -d
   ```

### Frontend Not Loading (bundle.js missing)

**Problem**: Browser shows `ERR_CONNECTION_REFUSED` when loading JavaScript bundle.

**Solution**: Rebuild the frontend image from scratch:
```bash
docker compose build msxplain_frontend --no-cache
docker compose up -d msxplain_frontend
```

This ensures:
- Node.js dependencies are properly installed
- Webpack builds the React application
- `bundle.js` and `index.html` are copied to Nginx

### Backend Processing Errors

1. **Check logs:**
   ```bash
   docker compose logs -f msxplain_backend
   ```

2. **Verify required files exist:**
   - `backend/msxplain/model/*`
   - `backend/msxplain/ensemble_models/*`
   - `backend/hd_bet_models/*`

3. **Check GPU access (if using GPU):**
   ```bash
   docker exec msxplain_backend nvidia-smi
   ```

### Container Won't Start

1. **Check container status:**
   ```bash
   docker compose ps
   docker compose logs [service_name]
   ```

2. **Verify ports are not in use:**
   ```bash
   netstat -tuln | grep -E '3001|5000|8042|4242'
   ```

3. **Check Docker resources:**
   ```bash
   docker system df
   docker system prune  # Clean up unused resources
   ```

### Out of Memory Issues

The neuroimaging tools require significant RAM. Ensure Docker has at least 8GB RAM allocated.

```bash
# Check Docker memory limit
docker info | grep Memory

# Increase memory in Docker Desktop settings if needed
```

### GPU Not Available

If GPU processing fails:

1. **Verify NVIDIA Docker runtime is installed:**
   ```bash
   docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
   ```

2. **Check GPU configuration in docker-compose.yml** (should be uncommented)

3. **Test GPU inside container:**
   ```bash
   docker exec msxplain_backend nvidia-smi
   ```

4. **Check NVIDIA drivers on host:**
   ```bash
   nvidia-smi
   ```

### Build Timeouts

The initial build may take 30-60 minutes due to downloading large neuroimaging tools:

```bash
# Use BuildKit for better progress output
DOCKER_BUILDKIT=1 docker compose build --progress=plain
```

## 6. Development

### File Structure for Docker Build

**Backend requirements:**
- `msxplain/model/*` - UNet model weights and configurations
- `msxplain/ensemble_models/*` - SwinUNETR ensemble checkpoints (5 seeds)
- `hd_bet_models/*` - Pre-trained brain extraction models

**Frontend requirements:**
- `public/*` - HTML templates and static assets

**Data directories** (created automatically, owned by UID:GID from `.env`):
- `backend/files/uploads/` - Uploaded patient data
- `backend/files/processed/` - Processing results
- `backend/files/DICOMS/` - DICOM files

### Monitoring and Logs

```bash
# View all logs
docker compose logs -f

# View specific service logs
docker compose logs -f msxplain_backend
docker compose logs -f msxplain_frontend
docker compose logs -f orthanc

# Check container resource usage
docker stats
```

### Updating Configuration

After changing configuration files:

1. **Orthanc config** (`config_ohif_orthnac/config/orthanc.json`):
   ```bash
   docker compose restart orthanc
   ```

3. **Environment variables** (`.env`):
   ```bash
   docker compose down
   docker compose up -d
   ```

## 7. Additional Resources

- **Report_template_USB.pdf** - Report template documentation
- **docker-compose.yml** - Docker services configuration
- **.env.example** - Environment configuration template

**Note**: Since v4.0, all configuration is done via Docker environment variables and the `.env` file. The `config.yml` file is no longer used. Since v5.0, FreeSurfer is no longer required — parcellation is handled by WMH-SynthSeg.

## 8. Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs: `docker compose logs -f`
3. Verify `.env` configuration matches your user
4. Ensure all required files are in place before building
