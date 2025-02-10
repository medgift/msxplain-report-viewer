import traceback
import os
from datetime import datetime
from fastapi import FastAPI, Response
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

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        false_positives = lesion_counts.get('False positive', 0)
        periventricular_lesions = lesion_counts.get('periventricular', 0)
        juxtacortical_lesions = lesion_counts.get('juxtacortical', 0)
        infratentorial_lesions = lesion_counts.get('infratentorial', 0)
        wm_lesions = lesion_counts.get('WM', 0)
        
        # Load DICOM file and extract metadata
        dicom_base_folder = f"files/DICOMS/4031-{patient_name}/"
        dicom_date_folder = next((f for f in os.listdir(dicom_base_folder) if os.path.isdir(os.path.join(dicom_base_folder, f))), None)
        dicom_flair_folder = next((f for f in os.listdir(os.path.join(dicom_base_folder, dicom_date_folder)) if 'flair' in f.lower()), None)
        print(dicom_date_folder, dicom_flair_folder)
        if dicom_date_folder and dicom_flair_folder:
            dicom_folder = os.path.join(dicom_base_folder, dicom_date_folder, dicom_flair_folder)
            print(dicom_folder)
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
            
        print(patient_name, patient_id, patient_birth_date)
        print(str(patient_birth_date))


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
        false_positives = len(report_df[report_df['Lesion Type'] == 'False positive'])
        
        # Get true lesions count (all lesions except false positives)
        true_lesions = len(report_df[report_df['Lesion Type'] != 'False positive'])
        
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
            'WM': (255, 0, 0),              # Red
            'juxtacortical': (0, 255, 0),   # Green
            'periventricular': (0, 0, 255), # Blue
            'infratentorial': (255, 255, 0), # Yellow
            'False positive': (128, 128, 128) # Gray - match Excel naming
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
                    is_false_positive = lesion_type == 'False positive'
                    
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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
