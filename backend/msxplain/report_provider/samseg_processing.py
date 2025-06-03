import os
import subprocess
import traceback


def run_samseg_processing(patient_dir, t1_path, pred_path):
    """Run SAMSEG processing pipeline using FreeSurfer and FSL
    
    Args:
        patient_dir (str): Path to patient directory
        t1_path (str): Path to T1 image
        pred_path (str): Path to prediction mask
    """

    try:
        samseg_dir = os.path.join(patient_dir, "SAMSEG")
        
        # Run SAMSEG
        print("Running SAMSEG segmentation...")
        subprocess.run([
            "run_samseg",
            "--input", t1_path,
            "--output", samseg_dir,
            "--threads", "2"
        ],
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Convert MGZ to NIFTI
        subprocess.run([
            "mri_convert",
            os.path.join(samseg_dir, "seg.mgz"),
            os.path.join(samseg_dir, "seg.nii.gz")
        ],
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Create individual structure masks
        print("Creating structure masks...")
        structures = {
            "LeftWM": (1.5, 2.5),
            "LeftCerebralCortex": (2.5, 3.5),
            "LeftLateralVentricle": (3.5, 4.5),
            "LeftCerebellumWM": (6.5, 7.5),
            "LeftCerebellumCortex": (7.5, 8.5),
            "Brainstem": (15.5, 16.5),
            "RightWM": (40.5, 41.5),
            "RightCerebralCortex": (41.5, 42.5),
            "RightLateralVentricle": (42.5, 43.5),
            "RightCerebellumWM": (45.5, 46.5),
            "RightCerebellumCortex": (46.5, 47.5)
        }
        
        seg_path = os.path.join(samseg_dir, "seg.nii.gz")
        for name, (lower, upper) in structures.items():
            subprocess.run([
                "fslmaths",
                seg_path,
                "-thr", str(lower),
                "-uthr", str(upper),
                os.path.join(samseg_dir, f"{name}.nii.gz")
            ], 
                           stdout=subprocess.DEVNULL,
                           check=True)
        
        # Create WM mask
        print("Creating WM mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "LeftWM.nii.gz"),
            "-add",
            os.path.join(samseg_dir, "RightWM.nii.gz"),
            os.path.join(samseg_dir, "WM_Mask.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "WM_Mask.nii.gz"),
            "-bin",
            os.path.join(samseg_dir, "WM_Mask.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Create Cortex mask
        print("Creating Cortex mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "LeftCerebralCortex.nii.gz"),
            "-add",
            os.path.join(samseg_dir, "RightCerebralCortex.nii.gz"),
            os.path.join(samseg_dir, "CerebralCortex.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "CerebralCortex.nii.gz"),
            "-bin",
            os.path.join(samseg_dir, "CerebralCortex.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "CerebralCortex.nii.gz"),
            "-mul",
            pred_path,
            os.path.join(samseg_dir, "common.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "CerebralCortex.nii.gz"),
            "-sub",
            os.path.join(samseg_dir, "common.nii.gz"),
            os.path.join(samseg_dir, "Cortex.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Create Ventricles mask
        print("Creating Ventricles mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "LeftLateralVentricle.nii.gz"),
            "-add",
            os.path.join(samseg_dir, "RightLateralVentricle.nii.gz"),
            os.path.join(samseg_dir, "LateralVentricles.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "LateralVentricles.nii.gz"),
            "-bin",
            os.path.join(samseg_dir, "LateralVentricles.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "LateralVentricles.nii.gz"),
            "-mul",
            pred_path,
            os.path.join(samseg_dir, "common2.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "LateralVentricles.nii.gz"),
            "-sub",
            os.path.join(samseg_dir, "common2.nii.gz"),
            os.path.join(samseg_dir, "Ventricles.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Create Infratentorial mask
        print("Creating Infratentorial mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "Brainstem.nii.gz"),
            "-add",
            os.path.join(samseg_dir, "LeftCerebellumWM.nii.gz"),
            "-add",
            os.path.join(samseg_dir, "RightCerebellumWM.nii.gz"),
            os.path.join(samseg_dir, "Infratentorial.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(samseg_dir, "Infratentorial.nii.gz"),
            "-bin",
            os.path.join(samseg_dir, "Infratentorial.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Clean up temporary files
        os.remove(os.path.join(samseg_dir, "common.nii.gz"))
        os.remove(os.path.join(samseg_dir, "common2.nii.gz"))
        
    except subprocess.CalledProcessError as e:
        print(f"Error in SAMSEG processing: {str(e)}")
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"Unexpected error in SAMSEG processing: {str(e)}")
        traceback.print_exc()
        raise 