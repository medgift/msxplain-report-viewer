import traceback
import os
from datetime import datetime
from fastapi import FastAPI, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import pandas as pd
import math
import nibabel as nib
import numpy as np
from io import BytesIO
from PIL import Image
import pydicom
from typing import List, Dict
import shutil
import asyncio
from msxplain.msxplain_report import MSXplainReport
from fastapi.background import BackgroundTasks
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# Global variable to store processing status
processing_status: Dict[str, dict] = {}

# Define constants for file paths
UPLOAD_FOLDER = "files/uploads"
PROCESSED_FOLDER = "files/processed"

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],  # React app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Create a thread pool executor
thread_pool = ThreadPoolExecutor(max_workers=4)

def sanitize_data(data):
    # Recursively check the data and replace invalid values
    if isinstance(data, float):
        if math.isinf(data) or math.isnan(data):
            return None  # Replace invalid values with None
    elif isinstance(data, dict):
        return {key: sanitize_data(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(value) for value in data]
    return data

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

# Route to get data from the Excel file
@app.get("/api/report/{patient_name}")          
async def get_report(patient_name: str):
    try:
        file_path = f"files/report_4031-{patient_name}.xlsx"  # Path to your file
        df = pd.read_excel(file_path)
        
        # Clean data
        sanitized_data = sanitize_data(df.to_dict(orient="records"))
        
        # Initialize variables
        lesion_counts = df['Lesion Type'].value_counts().to_dict()  # Counts by lesion type
        lesion_voxels_sum = df.loc[df['Lesion Type'] != 'False Positive', 'Lesion Voxels'].sum()
        lesion_volume_sum = df.loc[df['Lesion Type'] != 'False Positive', 'Lesion Volume'].sum()
        
        # Convert data to native Python types
        lesion_counts = convert_numpy_types(lesion_counts)
        lesion_volume_sum = float(lesion_volume_sum) # Ensure it is a native float
    
        # Extract lesion numbers
        false_positives = lesion_counts.get('False Positive', 0)
        periventricular_lesions = lesion_counts.get('Periventricular', 0)
        juxtacortical_lesions = lesion_counts.get('Juxtacortical', 0)
        infratentorial_lesions = lesion_counts.get('Infratentorial', 0)
        wm_lesions = lesion_counts.get('Deep White Matter', 0)
        
        # Load DICOM file and extract metadata
        dicom_base_folder = f"files/DICOMS/4031-{patient_name}/"
        dicom_date_folder = next((f for f in os.listdir(dicom_base_folder) if os.path.isdir(os.path.join(dicom_base_folder, f))), None)
        dicom_flair_folder = next((f for f in os.listdir(os.path.join(dicom_base_folder, dicom_date_folder)) if 'flair' in f.lower()), None)
        if dicom_date_folder and dicom_flair_folder:
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
                patient_name = patient_id = patient_birth_date = patient_sex = None
        else:
            patient_name = patient_id = patient_birth_date = patient_sex = None
        
        # Check if McDonald Criteria is fulfilled
        lesion_areas = [periventricular_lesions, juxtacortical_lesions, infratentorial_lesions, wm_lesions]
        affected_areas = sum(1 for lesion in lesion_areas if lesion > 0)

        if affected_areas >= 2:
            dissemination_space = "Fulfilled"
        else:
            dissemination_space = "Not fulfilled"

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
            "patient_sex": patient_sex if patient_sex else "Unknown"
        }
        return report_data
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": "Error generating report"},
            status_code=500
        )

@app.get("/api/total_lesions/{patient_name}")
async def get_total_lesions(patient_name: str):
    try:
        # Load report data
        report_df = pd.read_excel(f"files/report_4031-{patient_name}.xlsx")
        
        # Count lesions by type
        lesion_counts = report_df['Lesion Type'].value_counts()
        
        # Get false positives count
        false_positives = len(report_df[report_df['Lesion Type'] == 'False Positive'])
        
        # Get true lesions count (all lesions except false positives)
        true_lesions = len(report_df[report_df['Lesion Type'] != 'False Positive'])
        
        print("Lesion counts from report:")
        print(lesion_counts)
        print(f"True lesions: {true_lesions}")
        print(f"False positives: {false_positives}")
        
        return {
            "total_lesions": len(report_df),
            "true_lesions": true_lesions,
            "false_positives": false_positives,
            "lesion_types": lesion_counts.to_dict()
        }
    except Exception as e:
        print(f"Error getting lesion counts: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/api/slice/{patient_name}/{slice_num}")
async def get_slice(patient_name: str, slice_num: int, show_false_positives: bool = False):
    try:
        # Load NIFTI files
        lesion_file_path = f"files/NIFTI/4031-{patient_name}/lesion_map.nii.gz"
        brain_file_path = f"files/NIFTI/4031-{patient_name}/flair.nii.gz" 
        
        # Load report data
        report_df = pd.read_excel(f"files/report_4031-{patient_name}.xlsx")
        
        lesion_img = nib.load(lesion_file_path)
        brain_img = nib.load(brain_file_path)
        
        lesion_data = lesion_img.get_fdata()
        brain_data = brain_img.get_fdata()
        
        # Get the requested slices
        lesion_slice = lesion_data[:, :, slice_num]
        brain_slice = brain_data[:, :, slice_num]
        
        # Rotate and flip
        lesion_slice = np.flip(np.rot90(lesion_slice), axis=1)
        brain_slice = np.flip(np.rot90(brain_slice), axis=1)
        
        print(f"Slice {slice_num} information:")
        print(f"  Shape after rotation: {lesion_slice.shape}")
        print(f"  Lesion values: {np.unique(lesion_slice)}")
        print(f"  Brain range: [{brain_slice.min()}, {brain_slice.max()}]")
        
        # Define colors for each lesion type
        lesion_type_colors = {
            'Deep White Matter': (255, 0, 0),              # Red
            'Juxtacortical': (0, 255, 0),   # Green
            'Periventricular': (0, 0, 255), # Blue
            'Infratentorial': (255, 255, 0), # Yellow
            'False Positive': (128, 128, 128) # Gray - match Excel naming
        }
        
        # Create RGBA image with brain background
        colored_slice = np.zeros((*lesion_slice.shape, 4), dtype=np.uint8)
        
        # Normalize and set brain background
        brain_normalized = ((brain_slice - brain_slice.min()) / 
                          (brain_slice.max() - brain_slice.min() + 1e-8) * 255).astype(np.uint8)
        colored_slice[:, :, 0] = brain_normalized
        colored_slice[:, :, 1] = brain_normalized
        colored_slice[:, :, 2] = brain_normalized
        colored_slice[:, :, 3] = 255
        
        # Get unique lesion values in this slice
        unique_lesions = np.unique(lesion_slice)
        unique_lesions = unique_lesions[unique_lesions > 0.01]
        
        if len(unique_lesions) > 0:
            print(f"Found {len(unique_lesions)} lesions in slice {slice_num}")
            print(f"Show false positives mode: {show_false_positives}")
            
            for lesion_value in unique_lesions:
                # Find this lesion in the report using Lesion Index
                lesion_info = report_df[report_df['Lesion Index'] == lesion_value]
                
                if not lesion_info.empty:
                    lesion_type = lesion_info['Lesion Type'].iloc[0]
                    is_false_positive = lesion_type == 'False Positive'
                    
                    # Skip lesions based on view mode
                    if show_false_positives:
                        # In false positive mode, only show false positives
                        if not is_false_positive:
                            print(f"  Skipping non-false positive lesion {lesion_value}")
                            continue
                    else:
                        # In normal mode, skip false positives
                        if is_false_positive:
                            print(f"  Skipping false positive lesion {lesion_value}")
                            continue
                    
                    # Create mask for this lesion
                    lesion_mask = (np.abs(lesion_slice - lesion_value) < 0.5)
                    
                    # Get color based on lesion type
                    color = lesion_type_colors[lesion_type]
                    
                    # Set transparency
                    alpha = 150 if is_false_positive else 200
                    
                    # Apply color to the lesion
                    colored_slice[lesion_mask] = [*color, alpha]
                    
                    print(f"  Showing lesion {lesion_value}: type={lesion_type}, is_false_positive={is_false_positive}")
        
        # Convert to PIL Image and return
        slice_img = Image.fromarray(colored_slice, mode='RGBA')
        slice_img = slice_img.resize((slice_img.size[0] * 2, slice_img.size[1] * 2), Image.NEAREST)
        
        byte_io = BytesIO()
        slice_img.save(byte_io, format='PNG')
        byte_io.seek(0)
        
        return Response(
            content=byte_io.getvalue(),
            media_type="image/png",
            headers={
                "Content-Disposition": "inline",
                "filename": f"slice_{slice_num}.png",
                "X-Total-Slices": str(lesion_data.shape[2])
            }
        )
    
    except Exception as e:
        print(f"Error processing slice: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )
        
@app.post("/api/upload-dicoms")
async def upload_dicoms(files: List[UploadFile] = File(...)):
    try:
        # Generate unique run ID
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        base_dir = os.path.join(UPLOAD_FOLDER, run_id)
        
        # Create base directory
        os.makedirs(base_dir, exist_ok=True)
        
        # Save all files maintaining their structure
        for file in files:
            # Get the full path from the filename (includes patient/session/modality structure)
            file_path = os.path.join(base_dir, file.filename)
            
            # Create directories if they don't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save the file
            content = await file.read()
            with open(file_path, "wb") as buffer:
                buffer.write(content)
        
        # Get list of patient directories
        patient_dirs = [d for d in os.listdir(base_dir) 
                       if os.path.isdir(os.path.join(base_dir, d))]
        
        # Process each patient and their sessions
        for patient_dir in patient_dirs:
            patient_path = os.path.join(base_dir, patient_dir)
            session_dirs = [d for d in os.listdir(patient_path)
                          if os.path.isdir(os.path.join(patient_path, d))]
            
            # Process each session for this patient
            for session_dir in session_dirs:
                session_path = os.path.join(patient_path, session_dir)
                flair_dir = os.path.join(session_path, "flair")
                t1_dir = os.path.join(session_path, "t1")
                
                # Verify that both flair and t1 directories exist
                if os.path.exists(flair_dir) and os.path.exists(t1_dir):
                    # Create a unique ID for this patient-session combination
                    session_id = f"{patient_dir}_{session_dir}"
                    
                    # Start processing pipeline for this session
                    process_task = asyncio.create_task(
                        process_scans(run_id, session_id, [flair_dir, t1_dir])
                    )
        
        return JSONResponse(
            content={
                "message": f"Files uploaded successfully. Processing started for {len(patient_dirs)} patients.",
                "run_id": run_id,
                "patients": patient_dirs
            },
            status_code=200
        )
    except Exception as e:
        print(f"Error in upload: {str(e)}")
        traceback.print_exc()
        # Clean up any partially created directories
        if 'base_dir' in locals():
            shutil.rmtree(base_dir, ignore_errors=True)
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

def validate_dicoms(directory):
    """Validate that all files in directory are valid DICOM files"""
    try:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            pydicom.dcmread(file_path)
        return True
    except Exception as e:
        print(f"DICOM validation error: {str(e)}")
        return False

@app.post("/api/process-scans/{run_id}")
async def start_processing(run_id: str):
    try:
        base_dir = os.path.join(UPLOAD_FOLDER, run_id)
        
        if not os.path.exists(base_dir):
            return JSONResponse({
                'error': f"Upload directory not found: {run_id}"
            }, status_code=404)
        
        # Look for DICOMS directory first
        dicoms_dir = os.path.join(base_dir, "DICOMS")
        if not os.path.exists(dicoms_dir):
            return JSONResponse({
                'error': "DICOMS directory not found"
            }, status_code=400)
        
        # Get patient directories inside DICOMS folder
        patient_dirs = []
        for item in os.listdir(dicoms_dir):
            if item.startswith("4031-"):  # Pattern for patient directories
                item_path = os.path.join(dicoms_dir, item)
                if os.path.isdir(item_path):
                    patient_dirs.append(item)
        
        if not patient_dirs:
            return JSONResponse({
                'error': "No patient directories found"
            }, status_code=400)
        
        print(f"Found {len(patient_dirs)} patient directories: {patient_dirs}")
        
        # Initialize processing status for all patients
        processing_status[run_id] = {
            'patients': {
                patient_dir: {
                    'status': 'pending',
                    'steps': {
                        'preprocessing': 'pending',
                        'msxplain': 'pending',
                        'report': 'pending'
                    }
                }
                for patient_dir in patient_dirs
            }
        }
        
        # Start processing in background
        asyncio.create_task(process_all_patients(run_id, dicoms_dir, patient_dirs))
        
        return JSONResponse({
            'message': f"Processing started for {len(patient_dirs)} patients",
            'patients': patient_dirs
        })
        
    except Exception as e:
        print(f"Error starting processing: {str(e)}")
        traceback.print_exc()
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

async def process_all_patients(run_id: str, base_dir: str, patient_dirs: list):
    """Process all patients sequentially with progress updates"""
    try:
        print(f"\nStarting processing for run {run_id}")
        print(f"Will process these patients in order: {patient_dirs}")
        
        for i, patient_dir in enumerate(patient_dirs):
            try:
                # Update status to processing
                status = processing_status[run_id]['patients'][patient_dir]
                status['status'] = 'processing'
                
                # Notify progress update
                await notify_progress(run_id)
                
                print(f"\n[{i+1}/{len(patient_dirs)}] Processing patient: {patient_dir}")
                patient_path = os.path.join(base_dir, patient_dir)
                
                # Find FLAIR and T1 directories
                flair_dir = None
                t1_dir = None
                
                print(f"Searching for FLAIR and T1 in: {patient_path}")
                for root, dirs, files in os.walk(patient_path):
                    dir_name = os.path.basename(root).lower()
                    if 'flair' in dir_name and not flair_dir:
                        flair_dir = root
                        print(f"Found FLAIR directory: {flair_dir}")
                    elif 't1' in dir_name and not t1_dir:
                        t1_dir = root
                        print(f"Found T1 directory: {t1_dir}")
                    if flair_dir and t1_dir:
                        break
                
                if not flair_dir or not t1_dir:
                    raise ValueError(f"Could not find FLAIR and T1 directories in {patient_path}")
                
                # Initialize MSXplainReport with unique output directory for each patient
                patient_output_dir = os.path.join(PROCESSED_FOLDER, run_id, patient_dir)
                os.makedirs(patient_output_dir, exist_ok=True)
                
                print(f"Created output directory: {patient_output_dir}")
                
                msxplain = MSXplainReport(
                    flair_dir=flair_dir,
                    t1_dir=t1_dir,
                    output_dir=patient_output_dir
                )
                
                # Preprocessing step
                print(f"Starting preprocessing for {patient_dir}")
                status['steps']['preprocessing'] = 'processing'
                await notify_progress(run_id)
                
                nifti_files = msxplain.convert_dicoms_to_nifti()
                preprocessed_files = msxplain.preprocess_images(nifti_files)
                
                status['steps']['preprocessing'] = 'completed'
                await notify_progress(run_id)
                print(f"Completed preprocessing for {patient_dir}")
                
                # MSXplain step
                print(f"Starting MSXplain for {patient_dir}")
                status['steps']['msxplain'] = 'processing'
                await notify_progress(run_id)
                
                prediction_file = msxplain.run_msxplain(preprocessed_files)
                
                if not os.path.exists(prediction_file):
                    raise ValueError(f"MSXplain failed to generate prediction for {patient_dir}")
                
                status['steps']['msxplain'] = 'completed'
                await notify_progress(run_id)
                print(f"Completed MSXplain for {patient_dir}")
                
                # Report generation step
                print(f"Starting report generation for {patient_dir}")
                status['steps']['report'] = 'processing'
                await notify_progress(run_id)
                
                # Generate report
                report_df = msxplain.generate_report(prediction_file)
                
                # Save report to Excel file
                report_path = os.path.join(patient_output_dir, f"report_4031-{msxplain.patient_id}.xlsx")
                report_df.to_excel(report_path, index=False)
                
                if not os.path.exists(report_path):
                    raise ValueError(f"Failed to save report for {patient_dir}")
                
                status['steps']['report'] = 'completed'
                await notify_progress(run_id)
                print(f"Completed report generation for {patient_dir}")
                
                # Mark patient as completed
                status['status'] = 'completed'
                await notify_progress(run_id)
                print(f"Completed all processing for patient {patient_dir} [{i+1}/{len(patient_dirs)}]")
                
            except Exception as e:
                print(f"Error processing patient {patient_dir}: {str(e)}")
                traceback.print_exc()
                status['status'] = 'error'
                for step in status['steps']:
                    if status['steps'][step] == 'processing':
                        status['steps'][step] = 'error'
                await notify_progress(run_id)
        
        print(f"\nAll processing completed for run {run_id}")
        print("Final status:")
        for patient, status in processing_status[run_id]['patients'].items():
            print(f"- {patient}: {status['status']}")
        
    except Exception as e:
        print(f"Error in process_all_patients: {str(e)}")
        traceback.print_exc()

async def notify_progress(run_id: str):
    """Notify progress to connected clients"""
    try:
        # Add a small delay to allow status updates to propagate
        await asyncio.sleep(0.1)
    except Exception as e:
        print(f"Error in notify_progress: {str(e)}")

@app.get("/api/process-status/{run_id}")
async def get_processing_status(run_id: str):
    try:
        if run_id not in processing_status:
            return JSONResponse({
                'error': f"No status found for run {run_id}"
            }, status_code=404)
            
        status_info = processing_status[run_id]
        print(f"Status for run {run_id}:", status_info)
        
        return JSONResponse(
            content=status_info,
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
        
    except Exception as e:
        print(f"Error checking status: {str(e)}")
        traceback.print_exc()
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

@app.get("/api/patients")
async def get_patients():
    try:
        # Get list of processed patient directories
        processed_dir = PROCESSED_FOLDER
        if not os.path.exists(processed_dir):
            return []
            
        patients = []
        for patient_id in os.listdir(processed_dir):
            patient_dir = os.path.join(processed_dir, patient_id)
            if os.path.isdir(patient_dir):
                # Get patient status
                status = "Complete"
                if not os.path.exists(os.path.join(patient_dir, "report_complete")):
                    status = "Processing"
                
                # Get scan date from directory name or metadata
                try:
                    scan_date = datetime.strptime(
                        patient_id.split('_')[1], 
                        '%Y%m%d'
                    ).strftime('%Y-%m-%d')
                except:
                    scan_date = "Unknown"
                
                patients.append({
                    "id": patient_id,
                    "scan_date": scan_date,
                    "status": status
                })
        
        return sorted(patients, key=lambda x: x['scan_date'], reverse=True)
        
    except Exception as e:
        print(f"Error getting patients: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

def main():
    """Run the FastAPI application"""
    uvicorn.run(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    main()
