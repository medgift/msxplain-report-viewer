import os
import requests
import pydicom
from pathlib import Path
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def find_dicom_files(base_folder: str) -> list:
    """Find all DICOM files recursively"""
    dicom_files = []
    for root, _, files in os.walk(base_folder):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            try:
                # Try to read as DICOM - will raise error if not DICOM
                pydicom.dcmread(file_path)
                dicom_files.append(file_path)
                logger.info(f"Found DICOM file: {file_path}")
            except:
                continue
    return dicom_files

def upload_to_orthanc(base_folder: str) -> None:
    """Upload DICOM files to Orthanc"""
    orthanc_url = "http://localhost:8042"
    
    # First check if Orthanc is running
    try:
        response = requests.get(f"{orthanc_url}/system")
        if response.status_code != 200:
            raise Exception("Orthanc server is not responding correctly")
        logger.info("Successfully connected to Orthanc server")
    except requests.exceptions.RequestException as e:
        logger.error(f"Cannot connect to Orthanc server: {str(e)}")
        sys.exit(1)

    # Convert to absolute path and check directory
    base_folder = os.path.abspath(base_folder)
    logger.info(f"Scanning directory: {base_folder}")
    
    if not os.path.exists(base_folder):
        logger.error(f"Directory not found: {base_folder}")
        sys.exit(1)

    # Find all DICOM files
    dicom_files = find_dicom_files(base_folder)
    if not dicom_files:
        logger.error("No DICOM files found")
        sys.exit(1)
    
    logger.info(f"Found {len(dicom_files)} DICOM files to upload")
    
    success_count = 0
    error_count = 0
    
    # Upload each file
    for file_path in dicom_files:
        try:
            ds = pydicom.dcmread(file_path)
            patient_id = getattr(ds, 'PatientID', 'Unknown')
            study_id = getattr(ds, 'StudyInstanceUID', 'Unknown')
            
            logger.info(f"Uploading: {os.path.basename(file_path)}")
            logger.info(f"Patient ID: {patient_id}")
            logger.info(f"Study UID: {study_id}")
            
            with open(file_path, 'rb') as f:
                response = requests.post(
                    f"{orthanc_url}/instances",
                    data=f.read(),
                    headers={'Content-Type': 'application/dicom'}
                )
            
            if response.status_code == 200:
                success_count += 1
                logger.info(f"Successfully uploaded: {os.path.basename(file_path)}")
            else:
                error_count += 1
                logger.error(f"Failed to upload {os.path.basename(file_path)}")
                logger.error(f"Status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
                
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing {file_path}: {str(e)}")

    logger.info(f"Upload completed. Success: {success_count}, Errors: {error_count}")
    
    # Check available studies
    try:
        logger.info("Checking available studies in Orthanc...")
        response = requests.get(f"{orthanc_url}/studies")
        if response.status_code == 200:
            studies = response.json()
            logger.info(f"Found {len(studies)} studies in Orthanc")
            for study_id in studies:
                study_info = requests.get(f"{orthanc_url}/studies/{study_id}")
                if study_info.status_code == 200:
                    info = study_info.json()
                    logger.info(f"Study: {info.get('PatientID', 'Unknown')} - {info.get('StudyDescription', 'No description')}")
        else:
            logger.warning(f"Could not retrieve studies: {response.status_code} - {response.text}")
    except Exception as e:
        logger.warning(f"Error checking studies: {str(e)}")

if __name__ == "__main__":
    try:
        UPLOAD_FOLDER = "files/processed/run_20250521_110026/4031-5900/20220705"
        upload_to_orthanc(UPLOAD_FOLDER)
    except KeyboardInterrupt:
        logger.info("Upload process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Upload process failed: {str(e)}")
        sys.exit(1)