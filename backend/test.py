import nibabel as nib
import numpy as np
from io import BytesIO
from PIL import Image
   
# Load the NIfTI file (replace with your file path)
nii_file_path = "files/lesion_map.nii.gz"
img = nib.load(nii_file_path)
data = img.get_fdata()

# Get the requested slice (slice_num) from the 3D array
# Make sure to select the correct axis (for example, axis=2 for slices in z direction)
slice_data = data[:, :, 20]

# Convert the slice data to a PIL image to return as a PNG
slice_img = Image.fromarray(np.uint8(slice_data * 255))  # Adjust scaling as needed
byte_io = BytesIO()
slice_img.save(byte_io, 'PNG')
byte_io.seek(0)
print(slice_img)
slice_img.show()