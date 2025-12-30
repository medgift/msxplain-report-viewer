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

def delete_existing_segmentations(patient_id: str, orthanc_url: str = "http://orthanc:8042") -> bool:
    """
    Delete existing segmentation series for a patient in Orthanc
    
    Args:
        patient_id: The patient ID to search for
        orthanc_url: Orthanc server URL
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Checking for existing segmentations for patient: {patient_id}")
        
        # Search for patient in Orthanc
        search_url = f"{orthanc_url}/tools/find"
        query = {
            "Level": "Patient",
            "Query": {
                "PatientID": patient_id
            },
            "Expand": True
        }
        
        response = requests.post(search_url, json=query)
        
        if response.status_code != 200:
            logger.warning(f"Failed to query Orthanc: {response.status_code}")
            return False
        
        patients = response.json()
        
        if not patients:
            logger.info(f"No existing patient found in Orthanc for: {patient_id}")
            return True
        
        deleted_count = 0
        
        # For each patient match
        for patient in patients:
            patient_uid = patient.get('ID')
            
            # Get all studies for this patient
            for study_uid in patient.get('Studies', []):
                study_url = f"{orthanc_url}/studies/{study_uid}"
                study_data = requests.get(study_url).json()
                
                # Get all series in this study
                for series_uid in study_data.get('Series', []):
                    series_url = f"{orthanc_url}/series/{series_uid}"
                    series_data = requests.get(series_url).json()
                    
                    # Check if this is a segmentation series
                    main_tags = series_data.get('MainDicomTags', {})
                    modality = main_tags.get('Modality', '')
                    series_desc = main_tags.get('SeriesDescription', '')
                    
                    # Check if it's a segmentation (Modality=SEG or description contains segmentation)
                    is_segmentation = (
                        modality == 'SEG' or 
                        'segmentation' in series_desc.lower() or
                        'seg' in series_desc.lower()
                    )
                    
                    if is_segmentation:
                        logger.info(f"Found existing segmentation series: {series_uid}")
                        logger.info(f"  Modality: {modality}, Description: {series_desc}")
                        
                        # Delete this series
                        delete_url = f"{orthanc_url}/series/{series_uid}"
                        delete_response = requests.delete(delete_url)
                        
                        if delete_response.status_code == 200:
                            deleted_count += 1
                            logger.info(f"✓ Deleted existing segmentation: {series_uid}")
                        else:
                            logger.warning(f"✗ Failed to delete segmentation: {delete_response.status_code}")
        
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} existing segmentation(s)")
        else:
            logger.info("No existing segmentations found to delete")
        
        return True
        
    except Exception as e:
        logger.error(f"Error deleting existing segmentations: {e}")
        import traceback
        traceback.print_exc()
        return False


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
    
    # Check if we're uploading segmentations - only delete existing ones if so
    patient_id = None
    contains_segmentations = False
    
    try:
        # Check first file for patient ID and if any files are segmentations
        ds = pydicom.dcmread(dicom_files[0])
        patient_id = getattr(ds, 'PatientID', None)
        
        # Check if any of the files being uploaded are segmentations
        for file_path in dicom_files[:10]:  # Check first 10 files for efficiency
            try:
                ds = pydicom.dcmread(file_path)
                modality = getattr(ds, 'Modality', '')
                series_desc = getattr(ds, 'SeriesDescription', '')
                
                if modality == 'SEG' or 'segmentation' in series_desc.lower():
                    contains_segmentations = True
                    break
            except:
                continue
        
        if patient_id:
            logger.info(f"Detected Patient ID: {patient_id}")
            
            # Only delete existing segmentations if we're uploading new segmentations
            if contains_segmentations:
                logger.info("Uploading new segmentations - will delete existing ones first")
                delete_existing_segmentations(patient_id, orthanc_url)
            else:
                logger.info("Not uploading segmentations - keeping existing segmentations")
        else:
            logger.warning("No Patient ID found in DICOM files")
    except Exception as e:
        logger.warning(f"Could not extract Patient ID: {e}")
    
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
