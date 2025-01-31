from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import math
import nibabel as nib
import numpy as np
from io import BytesIO
from PIL import Image

app = FastAPI()

# Allow cross-origin requests
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

# Route to get data from the Excel file
@app.get("/api/report")          
async def get_report():
    try:
        file_path = "files/report_Patient01-1.xlsx"  # Path to your file
        df = pd.read_excel(file_path)
        
        # Clean data
        sanitized_data = sanitize_data(df.to_dict(orient="records"))
        
        # Initialize variables
        lesion_counts = df['Lesion Type'].value_counts().to_dict()  # Counts by lesion type
        lesion_voxels_sum = df.loc[df['Lesion Type'] != 'False Positive', 'Lesion Voxels'].sum()
        lesion_volume_sum = df.loc[df['Lesion Type'] != 'False Positive', 'Lesion Volume'].sum()
        
        # Convert data to native Python types
        lesion_counts = convert_numpy_types(lesion_counts)
        lesion_voxels_sum = float(lesion_voxels_sum)  # Ensure it is a native float
        lesion_volume_sum = float(lesion_volume_sum)
        
        # Prepare the response
        report_summary = {
            "total_voxels_affected": lesion_voxels_sum,
            "total_lesion_volume": lesion_volume_sum,
            "counts_by_lesion_type": lesion_counts
        }


        # Return as JSON
        return report_summary
    except Exception as e:
        return {"error": str(e)}
    
    
@app.get("/api/slice/{slice_num}")
async def get_slice(slice_num: int):
    try:
        # Load the NIfTI file (replace with your file path)
        nii_file_path = "files/lesion_map.nii.gz"
        img = nib.load(nii_file_path)
        data = img.get_fdata()

        # Get the requested slice (slice_num) from the 3D array
        # Make sure to select the correct axis (for example, axis=2 for slices in z direction)
        slice_data = data[:, :, slice_num]

        # Convert the slice data to a PIL image to return as a PNG
        slice_img = Image.fromarray(np.uint8(slice_data * 255))  # Adjust scaling as needed
        byte_io = BytesIO()
        slice_img.save(byte_io, 'PNG')
        byte_io.seek(0)

        return JSONResponse(content={"slice": byte_io.getvalue().decode('latin1')})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
