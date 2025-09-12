# MSXplain Docker Setup

This document provides instructions for setting up the MSXplain application with Docker, including all necessary neuroimaging tools.

## Prerequisites

- Docker and Docker Compose installed
- **For GPU Support (Optional but Recommended):**
  - NVIDIA GPU with compatible drivers installed on your host machine
  - NVIDIA Docker runtime installed on your host machine (see setup below)
- FreeSurfer license file (if using FreeSurfer functionality)

**Note**: The Docker images are already GPU-ready with CUDA libraries. You only need to install NVIDIA Docker runtime on your host computer to enable GPU passthrough to containers.

## Neuroimaging Tools Included

The backend Docker image includes the following neuroimaging tools using **official Docker images** for optimal performance:

1. **FSL 6.0.7.4** - FMRIB Software Library for brain imaging analysis
2. **FreeSurfer 7.4.1** - Cortical reconstruction and volumetric segmentation *(from official `freesurfer/freesurfer:7.4.1`)*
3. **ANTs 2.6.2** - Advanced Normalization Tools for image registration *(from official `antsx/ants:2.6.2`)*
4. **dcm2niix** - DICOM to NIfTI conversion
5. **HD-BET** - Brain extraction tool
6. **elastix 5.0.1** - Image registration toolkit

## Setup Instructions

### 1. FreeSurfer License (Required if using FreeSurfer)

FreeSurfer requires a valid license file. You can obtain one for free from:
https://surfer.nmr.mgh.harvard.edu/registration.html

Once you have the license file:

1. Place it in the project root as `freesurfer_license.txt`
2. Uncomment the license volume mount in `docker-compose.yml`:
   ```yaml
   volumes:
     - ./freesurfer_license.txt:/opt/freesurfer/license.txt:ro
   ```

### 2. GPU Support (Optional but Recommended)

**Your Docker images are already GPU-ready!** You just need to enable GPU access from your host machine.

**Requirements on your host computer:**
- NVIDIA GPU with recent drivers
- NVIDIA Docker runtime

**Installation steps for your host machine:**

1. **Install NVIDIA Docker runtime on your computer:**
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
   Uncomment the GPU configuration in `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             count: 1
             capabilities: [gpu]
   ```

**What's already in the Docker images:**
- ✅ CUDA 11.7 runtime libraries
- ✅ cuDNN 8.5 for deep learning
- ✅ GPU-enabled PyTorch and MONAI
- ✅ All necessary CUDA dependencies

### 3. Configuration

Make sure you have a valid `backend/config.yml` file. You can use the example:
```bash
cp backend/config.yml.example backend/config.yml
```

Update the paths in `config.yml` to match the Docker environment:
```yaml
paths:
  fsl_dir: "/usr/share/fsl/6.0"
  freesurfer_home: "/opt/freesurfer"
  ants_dir: "/opt/ants"
```

## Running the Application

### Build and Start All Services

```bash
# Build and start all services
docker-compose up --build

# Or run in detached mode
docker-compose up -d --build
```

### Access Points

- **Frontend (React App)**: http://localhost:3001
- **Backend API**: http://localhost:8000
- **OHIF Viewer**: http://localhost:3000
- **Orthanc PACS**: http://localhost:8042

### Useful Commands

```bash
# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f backend

# Stop all services
docker-compose down

# Rebuild only backend
docker-compose build backend

# Run bash in backend container
docker-compose exec backend bash
```

## Troubleshooting

### Common Issues

1. **Out of Memory**: The neuroimaging tools require significant RAM. Ensure Docker has at least 8GB RAM allocated.

2. **FreeSurfer License**: If FreeSurfer fails, check that:
   - License file is properly mounted
   - License file is valid and not expired
   - License file has correct permissions

3. **GPU Not Available**: If GPU processing fails:
   - Verify NVIDIA Docker runtime is installed
   - Check that GPU configuration is uncommented in docker-compose.yml
   - Verify GPU is available: `docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi`

4. **Build Timeouts**: The initial build may take 30-60 minutes due to downloading large neuroimaging tools. Use:
   ```bash
   DOCKER_BUILDKIT=1 docker-compose build --progress=plain
   ```

### File Permissions

If you encounter permission issues with mounted volumes:
```bash
# Fix permissions for files directory
sudo chown -R $USER:$USER backend/files
chmod -R 755 backend/files
```

## Development

For development with hot reload:

1. Comment out the backend service in docker-compose.yml
2. Run backend locally:
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn app:app --reload --host 0.0.0.0 --port 8000
   ```
3. Keep frontend and other services running with Docker

## Environment Variables

The following environment variables are available in the backend container:

- `FSLDIR=/usr/share/fsl/6.0`
- `FSLOUTPUTTYPE=NIFTI_GZ`
- `FREESURFER_HOME=/opt/freesurfer`
- `ANTSPATH=/opt/ants/bin`
- `ORTHANC_URL=http://orthanc:8042`
- `PYTHONPATH=/app`
