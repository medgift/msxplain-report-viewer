import os
import requests
import pydicom
import logging

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
            except:
                continue
     
    return dicom_files

def upload_to_orthanc(base_folder: str) -> None:
    """Upload DICOM files to Orthanc"""
    # Use Docker service name
    orthanc_url = "http://orthanc:8042"
    
    # First check if Orthanc is running
    try:
        response = requests.get(f"{orthanc_url}/system")
        if response.status_code != 200:
            raise Exception("Orthanc server is not responding correctly")
        logger.info("Successfully connected to Orthanc server")
    except requests.exceptions.RequestException as e:
        logger.error(f"Cannot connect to Orthanc server: {str(e)}")

    # Convert to absolute path and check directory
    base_folder = os.path.abspath(base_folder)
    logger.info(f"Scanning directory: {base_folder}")
    
    if not os.path.exists(base_folder):
        logger.error(f"Directory not found: {base_folder}")

    # Find all DICOM files
    dicom_files = find_dicom_files(base_folder)
    if not dicom_files:
        logger.error("No DICOM files found")
    
    logger.info(f"Found {len(dicom_files)} DICOM files to upload")
    
    success_count = 0
    error_count = 0
    
    # Upload each file
    for file_path in dicom_files:
        try:            
            with open(file_path, 'rb') as f:
                response = requests.post(
                    f"{orthanc_url}/instances",
                    data=f.read(),
                    headers={'Content-Type': 'application/dicom'}
                )
            
            if response.status_code == 200:
                success_count += 1
            else:
                error_count += 1
                logger.error(f"Failed to upload {os.path.basename(file_path)}")
                logger.error(f"Status code: {response.status_code}")
                logger.error(f"Response: {response.text}")
                
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing {file_path}: {str(e)}")

    logger.info(f"Upload completed. Success: {success_count}, Errors: {error_count}")
