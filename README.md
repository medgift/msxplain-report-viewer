# react_report

v1.0: First approach to create the report from the results of MSReport-Provider and a Viewer with the axial plane with the lesion map overlapping
v2.0: The system incorporates an uploading Page to upload a folder with more than 1 patient, the structure Folder/Patients/Session/Images(T1 and FLAIR). The folder can be processed using the MSReport provider Pipeline (Preprocessing, MSXplain Report Provider, Report generator).
v3.0: Complete incorporation of Report Provider with skull stripping, updating the model, converting the lesion_map to dicom_seg, and registering to flair space. Start the incorporation of the OHIF Viewer + Orthanc. 

## Quick Start

### First Time Setup:
Create a `.env` file with your user configuration (important for file permissions):
```bash
# Create .env file with your user ID and group ID
echo "UID=$(id -u)" > .env
echo "GID=$(id -g)" >> .env
```

Or copy from the example and edit:
```bash
cp .env.example .env
# Edit .env to match your user ID (run 'id -u' to get it)
```

### Using the start script (Recommended):
```bash
./start.sh start
```

### Manual start:
```bash
# Start all services (will use UID/GID from .env file)
docker compose up -d
```

### Access the application:
- **Frontend**: http://localhost:3001 (or http://YOUR_SERVER_IP:3001)
- **Backend API**: http://localhost:5000
- **Orthanc PACS**: http://localhost:8042
- **Orthanc DICOM**: port 4242

## Docker
For docker this needs to be copied in the before building the image:

backend:
    - msxplain/model/*
    <!-- - config.yml -->
    - secrets/*
    - hd_bet_models/*

frontend:
    - public/*


# Create backend files directories if they don't exist*
mkdir -p backend/files/uploads
mkdir -p backend/files/processed

*Careful with permissions. They have to belong to the user building and running teh docker images.

# App not running after building succesfully. Check this:
Problem Summary:
The frontend container was running but didn't have the bundle.js file properly built and copied to the nginx html directory
This caused the browser to fail loading the JavaScript bundle with ERR_CONNECTION_REFUSED
Solution:
I rebuilt the frontend Docker image from scratch using docker compose build msxplain_frontend --no-cache, which:

Installed all Node.js dependencies with Yarn
Built the React application using webpack in production mode
Generated bundle.js (266 KiB) and index.html
Copied these files to the nginx html directory in the final container
