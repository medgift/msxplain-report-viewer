import traceback
import os
from datetime import datetime
from fastapi import FastAPI, Response, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import pandas as pd
import nibabel as nib
import numpy as np
from io import BytesIO
from PIL import Image
import pydicom
from typing import List, Dict
import shutil
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
@app.get("/api/report/{run_id}/{patient_name}")          
async def get_report(run_id: str, patient_name: str):
    try:
        # Construct the correct file path using run_id
        file_path = os.path.join(PROCESSED_FOLDER, run_id, patient_name, f"report_{patient_name}.xlsx")
        
        print(f"Looking for report at: {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Report file not found: {file_path}")
            
        df = pd.read_excel(file_path)
        
        # Initialize variables
        lesion_counts = df['Lesion Type'].value_counts().to_dict()
        lesion_volume_sum = df.loc[df['Lesion Type'] != 'False Positive', 'Lesion Volume'].sum()
        
        # Convert data to native Python types
        lesion_counts = convert_numpy_types(lesion_counts)
        lesion_volume_sum = float(lesion_volume_sum)
    
        # Extract lesion numbers
        false_positives = lesion_counts.get('False Positive', 0)
        periventricular_lesions = lesion_counts.get('Periventricular', 0)
        juxtacortical_lesions = lesion_counts.get('Juxtacortical', 0)
        infratentorial_lesions = lesion_counts.get('Infratentorial', 0)
        wm_lesions = lesion_counts.get('Deep White Matter', 0)
        
        # Load DICOM file and extract metadata from the uploaded folder
        dicom_base_folder = os.path.join(UPLOAD_FOLDER, run_id, "DICOMS", patient_name)
        
        try:
            dicom_date_folder = next((f for f in os.listdir(dicom_base_folder) 
                                    if os.path.isdir(os.path.join(dicom_base_folder, f))), None)
            if dicom_date_folder:
                dicom_flair_folder = next((f for f in os.listdir(os.path.join(dicom_base_folder, dicom_date_folder)) 
                                         if 'flair' in f.lower()), None)
                if dicom_flair_folder:
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
                        patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"
                else:
                    patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"
            else:
                patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"
        except Exception as e:
            print(f"Error reading DICOM metadata: {str(e)}")
            patient_name = patient_id = patient_birth_date = patient_sex = "Unknown"

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

@app.get("/api/total_lesions/{run_id}/{patient_name}")
async def get_total_lesions(run_id: str, patient_name: str):
    try:
        # Construct the correct path
        report_path = os.path.join(PROCESSED_FOLDER, run_id, patient_name, f"report_{patient_name}.xlsx")
        
        if not os.path.exists(report_path):
                                raise FileNotFoundError(f"Report file not found: {report_path}")

        report_df = pd.read_excel(report_path)
        
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
        
        
def hex_to_rgb(hex):
  return tuple(int(hex[i:i+2], 16) for i in (0, 2, 4))

hex_to_rgb('FFA501') # (255, 165, 1)

@app.get("/api/slice/{run_id}/{patient_name}/{slice_num}")
async def get_slice(run_id: str, patient_name: str, slice_num: int, show_false_positives: bool = False):
    try:
        # Construct the correct path            
        base_path = os.path.join(PROCESSED_FOLDER, run_id, patient_name)

        if not os.path.exists(base_path):
            raise FileNotFoundError(f"Patient directory not found: {base_path}")
        
        # Load the lesion and brain images
        lesion_file_path = os.path.join(base_path, "lesion_map.nii.gz")
        brain_file_path = os.path.join(base_path, "flair_registered.nii.gz")
        lesion_img = nib.load(lesion_file_path)
        brain_img = nib.load(brain_file_path)
        lesion_data = lesion_img.get_fdata()
        brain_data = brain_img.get_fdata()
        
        # Load the report file
        report_path = os.path.join(base_path, f"report_{patient_name}.xlsx")
        report_df = pd.read_excel(report_path)
        
        if not all(os.path.exists(f) for f in [lesion_file_path, brain_file_path, report_path]):
            raise FileNotFoundError("One or more required files not found")
        
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
                'Deep White Matter': hex_to_rgb('880808'), # Red
                'Juxtacortical': hex_to_rgb('F88379'), # CoralPink
                'Periventricular': hex_to_rgb('0000FF'), # Blue
                'Infratentorial': hex_to_rgb('00FFFF'), # Aqua
                'False Positive': hex_to_rgb('808080')  # Gray
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

@app.post("/api/process-scans/{run_id}")
async def start_processing(run_id: str, background_tasks: BackgroundTasks):
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
        patient_dirs = [item for item in os.listdir(dicoms_dir) 
                       if item.startswith("4031-") and 
                       os.path.isdir(os.path.join(dicoms_dir, item))]
        
        if not patient_dirs:
            return JSONResponse({
                'error': "No patient directories found"
            }, status_code=400)
        
        print(f"Found {len(patient_dirs)} patient directories: {patient_dirs}")
        
        # Initialize processing status
        processing_status[run_id] = {
            'total_patients': len(patient_dirs),
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
        
        # Add to background tasks
        background_tasks.add_task(process_all_patients, run_id, dicoms_dir, patient_dirs)
        
        return JSONResponse({
            'message': f"Processing started for {len(patient_dirs)} patients",
'total_patients': len(patient_dirs),
            'patients': patient_dirs
        })
        
    except Exception as e:
        print(f"Error starting processing: {str(e)}")
        traceback.print_exc()
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

def process_all_patients(run_id: str, base_dir: str, patient_dirs: list):
    """Process all patients sequentially with progress updates"""
    try:
        print(f"\nStarting processing for run {run_id}...")
        global processing_status

        for i, patient_dir in enumerate(patient_dirs):
            try:
                status = processing_status[run_id]['patients'][patient_dir]
                status['status'] = 'processing'
                
                print(f"\n[{i+1}/{len(patient_dirs)}] Processing patient: {patient_dir}")
                
                # Create thread pool for CPU-intensive tasks
                with ThreadPoolExecutor(max_workers=1) as executor:
                    # Process each step in the thread pool
                    patient_path = os.path.join(base_dir, patient_dir)
                    patient_output_dir = os.path.join(PROCESSED_FOLDER, run_id, patient_dir)
                    os.makedirs(patient_output_dir, exist_ok=True)

                    # Find FLAIR and T1 directories
                    flair_dir, t1_dir = executor.submit(
                        find_input_directories, patient_path
                    ).result()

                    # Preprocessing step
                    status['steps']['preprocessing'] = 'processing'
                    msxplain = MSXplainReport(
                        flair_dir=flair_dir,
                        t1_dir=t1_dir,
                        output_dir=patient_output_dir
                    )
                    
                    nifti_files = executor.submit(
                        msxplain.convert_dicoms_to_nifti
                    ).result()
                    
                    preprocessed_files = executor.submit(
                        msxplain.preprocess_images, nifti_files
                    ).result()
                    
                    status['steps']['preprocessing'] = 'completed'

                    # MSXplain step
                    status['steps']['msxplain'] = 'processing'
                    prediction_file = executor.submit(
                        msxplain.run_msxplain, preprocessed_files
                    ).result()
                    
                    status['steps']['msxplain'] = 'completed'

                    # Report generation step
                    status['steps']['report'] = 'processing'
                    report_df = executor.submit(
                        msxplain.generate_report, prediction_file
                    ).result()
                    
                    report_path = os.path.join(patient_output_dir, f"report_{patient_dir}.xlsx")
                    report_df.to_excel(report_path, index=False)
                    
                    status['steps']['report'] = 'completed'
                    status['status'] = 'completed'

            except Exception as e:
                print(f"Error processing patient {patient_dir}: {str(e)}")
                traceback.print_exc()
                status['status'] = 'error'
                for step in status['steps']:
                    if status['steps'][step] == 'processing':
                        status['steps'][step] = 'error'

        print(f"\nAll processing completed for run {run_id}")
        
    except Exception as e:
        print(f"Error in process_all_patients: {str(e)}")
        traceback.print_exc()

def find_input_directories(patient_path):
    """Helper function to find FLAIR and T1 directories"""
    flair_dir = None
    t1_dir = None
    
    for root, dirs, files in os.walk(patient_path):
        dir_name = os.path.basename(root).lower()
        if 'flair' in dir_name and not flair_dir:
            flair_dir = root
        elif 't1' in dir_name and not t1_dir:
            t1_dir = root
        if flair_dir and t1_dir:
            break
            
    if not flair_dir or not t1_dir:
        raise ValueError(f"Could not find FLAIR and T1 directories in {patient_path}")
        
    return flair_dir, t1_dir

@app.get("/api/process-status/{run_id}")
async def get_process_status(run_id: str):
    try:
        print(f"Getting status for run: {run_id}")
        
        # Check if any processing is active
        if not processing_status:
            return JSONResponse({
                'message': 'No active processing',
                'status': 'inactive',
                'total_patients': 0,
                'patients': {}
            })
            
        # First check if run exists in processing_status
        if run_id in processing_status:
            return processing_status[run_id]
            
        # If not in processing_status, check if run exists in processed folder
        run_dir = os.path.join(PROCESSED_FOLDER, run_id)
        if os.path.exists(run_dir):
            # Create a status object for completed runs
            all_patients = [
                patient_dir for patient_dir in os.listdir(run_dir)
                if os.path.isdir(os.path.join(run_dir, patient_dir))
            ]
            
            return {
                'status': 'completed',
                'total_patients': len(all_patients),
                'patients': {
                    patient_dir: {
                        'status': 'completed',
                        'steps': {
                            'preprocessing': 'completed',
                            'msxplain': 'completed',
                            'report': 'completed'
                        }
                    }
                    for patient_dir in all_patients
                }
            }
        
        # If run is not found anywhere, return inactive status
        return JSONResponse({
            'message': f'Run {run_id} not found',
            'status': 'inactive',
            'total_patients': 0,
            'patients': {}
        })

    except Exception as e:
        print(f"Error getting process status: {str(e)}")
        traceback.print_exc()
        return JSONResponse({
            'error': str(e),
            'status': 'error'
        }, status_code=500)

@app.get("/api/processed-runs")
async def get_processed_runs():
    try:
        if not os.path.exists(PROCESSED_FOLDER):
            return []
            
        runs = []
        for run_id in os.listdir(PROCESSED_FOLDER):
            run_dir = os.path.join(PROCESSED_FOLDER, run_id)
            if os.path.isdir(run_dir):
                # Get all patient directories first
                all_patients = [
                    patient_dir for patient_dir in os.listdir(run_dir)
                    if os.path.isdir(os.path.join(run_dir, patient_dir))
                ]
                
                # Create patient entries
                patients = []
                for patient_dir in all_patients:
                    patient_path = os.path.join(run_dir, patient_dir)
                    report_path = os.path.join(patient_path, f"report_{patient_dir}.xlsx")
                    
                    # Check if patient is in processing status
                    run_status = processing_status.get(run_id, {}).get('patients', {}).get(patient_dir, {})
                    if run_status and any(step == 'processing' for step in run_status.get('steps', {}).values()):
                        status = "Processing"
                    else:
                        status = "Complete" if os.path.exists(report_path) else "Processing"
                    
                    patients.append({
                        "id": patient_dir,
                        "status": status
                    })
                
                # Get total patients from processing status or fallback to directory count
                total_patients = (processing_status.get(run_id, {}).get('total_patients') 
                                or len(all_patients))
                
                runs.append({
                    "id": run_id,
                    "date": datetime.fromtimestamp(os.path.getctime(run_dir)).strftime('%Y-%m-%d %H:%M:%S'),
                    "patients": patients,
                    "total_patients": total_patients
                })
        
        # Sort runs by date, most recent first
        runs.sort(key=lambda x: x['date'], reverse=True)
        return runs
        
    except Exception as e:
        print(f"Error getting processed runs: {str(e)}")
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
