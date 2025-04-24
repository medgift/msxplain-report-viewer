import SimpleITK as sitk

patient_dir = '/home/lluis/msxplain/msxplain_report_viewer/backend/files/processed/run_20250423_140141/4031-5905/20211126'
shwow_dir = f'{patient_dir}/SHOWING'

# === Define paths to the images ===
fixed_image_path = f'{shwow_dir}/flair_n4.nii.gz'
moving_image_path = f'{shwow_dir}/lesion_map.nii.gz'
moving_image_t1_path = f'{shwow_dir}/t1_n4.nii.gz'

# === Read transform parameters from file ===
param_file = f'{patient_dir}/registration/TransformParameters.0.txt'

def parse_transform_params(filename):
    with open(filename, 'r') as f:
        lines = f.readlines()
        for line in lines:
            if 'TransformParameters' in line:
                print(line)
                params = [float(x) for x in line.split('(TransformParameters ')[1].strip(')\n').split()]
                rotation_angles = params[0:3]
                translation = params[3:6]
                print(rotation_angles)
                print(translation)
            elif 'CenterOfRotationPoint' in line:
                print(line)
                center_of_rotation = [float(x) for x in line.split('(CenterOfRotationPoint ')[1].strip(')\n').split()]
                print(center_of_rotation)
    
    return rotation_angles, translation, center_of_rotation

# === Get transform parameters from file ===
rotation_angles, translation, center_of_rotation = parse_transform_params(param_file)
print("Rotation angles:", rotation_angles)
print("Translation:", translation)
print("Center of rotation:", center_of_rotation)

# === Load the lesion map and FLAIR image ===
lesion_map = sitk.ReadImage(moving_image_path, sitk.sitkFloat32)
flair_image = sitk.ReadImage(fixed_image_path, sitk.sitkFloat32)

# === Create original Euler transform ===
transform = sitk.Euler3DTransform()
transform.SetCenter(center_of_rotation)
transform.SetRotation(*rotation_angles)
transform.SetTranslation(translation)

# === Invert the transform ===
inverse_transform = transform.GetInverse()

# === Resample lesion map into original FLAIR space ===
# You need to provide a reference image in FLAIR space:


resampled = sitk.Resample(lesion_map,
                          flair_image,  # Target space
                          inverse_transform,
                          sitk.sitkNearestNeighbor,  # Use NN for labels
                          0.0,  # Default pixel value
                          lesion_map.GetPixelID())

# === Resample T1 image into original FLAIR space ===
t1_image = sitk.ReadImage(moving_image_t1_path, sitk.sitkFloat32)
resampled_t1 = sitk.Resample(t1_image,
                              flair_image,  # Target space
                              inverse_transform,
                              sitk.sitkLinear,  # Use linear interpolation for T1
                              0.0,  # Default pixel value
                              t1_image.GetPixelID())

# === Save the result ===
sitk.WriteImage(resampled, f"{shwow_dir}/lesion_map_in_flair_space.nii.gz")
sitk.WriteImage(resampled_t1, f"{shwow_dir}/t1_in_flair_space.nii.gz")
