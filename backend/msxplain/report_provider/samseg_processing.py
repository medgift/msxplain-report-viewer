import os
import subprocess
import traceback


def run_samseg_processing(patient_dir, t1_path, pred_path):
    """Run WMH-SynthSeg processing pipeline (replaces SAMSEG with WMH-SynthSeg)
    
    Args:
        patient_dir (str): Path to patient directory
        t1_path (str): Path to T1 image
        pred_path (str): Path to prediction mask
    """

    try:
        samseg_dir = os.path.join(patient_dir, "SYNTHSEG")
        os.makedirs(samseg_dir, exist_ok=True)
        
        # Detect GPU availability
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"WMH-SynthSeg will use device: {device}")
        except ImportError:
            device = "cpu"
            print("PyTorch not available, using CPU")
        
        # Run WMH-SynthSeg segmentation
        print("Running WMH-SynthSeg segmentation...")
        print(f"Input T1 path: {t1_path}")
        seg_output = os.path.join(samseg_dir, "seg.nii.gz")
        
        # Convert to absolute paths
        abs_t1_path = os.path.abspath(t1_path)
        abs_seg_output = os.path.abspath(seg_output)
        abs_csv_path = os.path.abspath(os.path.join(samseg_dir, "vols.csv"))
        
        print(f"Absolute T1 path: {abs_t1_path}")
        print(f"Absolute output path: {abs_seg_output}")
        
        result = subprocess.run([
            "python",
            "/app/wmh_synthseg/WMHSynthSeg/inference.py",
            "--i", abs_t1_path,
            "--o", abs_seg_output,
            "--csv_vols", abs_csv_path,
            "--device", device
        ],
                       capture_output=True,
                       text=True,
                       check=False)
        
        print(f"WMH-SynthSeg stdout:\n{result.stdout}")
        if result.stderr:
            print(f"WMH-SynthSeg stderr:\n{result.stderr}")
        print(f"Return code: {result.returncode}")
        
        if result.returncode == -9:
            raise RuntimeError("WMH-SynthSeg was killed (likely out of memory). Consider increasing Docker memory limit or using a smaller image.")
        elif result.returncode != 0:
            raise RuntimeError(f"WMH-SynthSeg failed with return code {result.returncode}")
        
        # Verify output file was created
        if not os.path.exists(seg_output):
            print(f"Contents of SYNTHSEG directory: {os.listdir(samseg_dir) if os.path.exists(samseg_dir) else 'Directory does not exist'}")
            raise FileNotFoundError(f"WMH-SynthSeg did not create output file: {seg_output}")
        
        print(f"Segmentation file created successfully: {seg_output}")
        
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