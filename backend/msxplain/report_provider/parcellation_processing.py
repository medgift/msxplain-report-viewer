import os
import subprocess
import traceback
import logging

logger = logging.getLogger(__name__)

def run_parcellation(t1_path, pred_path, parcellation_dir, device="cpu"):
    """Run parcellation processing to create structure masks
    
    Args:
        t1_path (str): Path to T1 image
        pred_path (str): Path to prediction mask
        parcellation_dir (str): Path to parcellation directory
        device (str): Device to use for computation ('cpu' or 'cuda'). Defaults to 'cpu'.
    """
    
    # Validate input file paths early to provide clear error messages
    if not os.path.exists(t1_path):
        raise FileNotFoundError(f"T1 image not found at path: {t1_path}")
    if not os.path.exists(pred_path):
        raise FileNotFoundError(f"Prediction mask not found at path: {pred_path}")

    try:
        
        # Use CPU to avoid GPU OOM errors and dimension mismatches from --crop flag
        # The --crop flag (needed for GPU) creates smaller output images that don't 
        # match dimensions with pred.nii.gz, causing fslmaths multiplication errors

        seg_path = run_wmh_synthseg(t1_path, parcellation_dir, device=device)
        
        # Create individual structure masks
        logger.info("Creating structure masks...")
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
        
        for name, (lower, upper) in structures.items():
            subprocess.run([
                "fslmaths",
                seg_path,
                "-thr", str(lower),
                "-uthr", str(upper),
                os.path.join(parcellation_dir, f"{name}.nii.gz")
            ], 
                           stdout=subprocess.DEVNULL,
                           check=True)
        
        # Create WM mask
        logger.info("Creating WM mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "LeftWM.nii.gz"),
            "-add",
            os.path.join(parcellation_dir, "RightWM.nii.gz"),
            os.path.join(parcellation_dir, "WM_Mask.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "WM_Mask.nii.gz"),
            "-bin",
            os.path.join(parcellation_dir, "WM_Mask.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Create Cortex mask
        logger.info("Creating Cortex mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "LeftCerebralCortex.nii.gz"),
            "-add",
            os.path.join(parcellation_dir, "RightCerebralCortex.nii.gz"),
            os.path.join(parcellation_dir, "CerebralCortex.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "CerebralCortex.nii.gz"),
            "-bin",
            os.path.join(parcellation_dir, "CerebralCortex.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "CerebralCortex.nii.gz"),
            "-mul",
            pred_path,
            os.path.join(parcellation_dir, "common.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "CerebralCortex.nii.gz"),
            "-sub",
            os.path.join(parcellation_dir, "common.nii.gz"),
            os.path.join(parcellation_dir, "Cortex.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Create Ventricles mask
        logger.info("Creating Ventricles mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "LeftLateralVentricle.nii.gz"),
            "-add",
            os.path.join(parcellation_dir, "RightLateralVentricle.nii.gz"),
            os.path.join(parcellation_dir, "LateralVentricles.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "LateralVentricles.nii.gz"),
            "-bin",
            os.path.join(parcellation_dir, "LateralVentricles.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "LateralVentricles.nii.gz"),
            "-mul",
            pred_path,
            os.path.join(parcellation_dir, "common2.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "LateralVentricles.nii.gz"),
            "-sub",
            os.path.join(parcellation_dir, "common2.nii.gz"),
            os.path.join(parcellation_dir, "Ventricles.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Create Infratentorial mask
        logger.info("Creating Infratentorial mask...")
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "Brainstem.nii.gz"),
            "-add",
            os.path.join(parcellation_dir, "LeftCerebellumWM.nii.gz"),
            "-add",
            os.path.join(parcellation_dir, "RightCerebellumWM.nii.gz"),
            os.path.join(parcellation_dir, "Infratentorial.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        subprocess.run([
            "fslmaths",
            os.path.join(parcellation_dir, "Infratentorial.nii.gz"),
            "-bin",
            os.path.join(parcellation_dir, "Infratentorial.nii.gz")
        ], 
                       stdout=subprocess.DEVNULL,
                       check=True)
        
        # Clean up temporary files
        os.remove(os.path.join(parcellation_dir, "common.nii.gz"))
        os.remove(os.path.join(parcellation_dir, "common2.nii.gz"))
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in Parcellation processing: {str(e)}")
        traceback.print_exc()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Parcellation processing: {str(e)}")
        traceback.print_exc()
        raise 
    
def run_wmh_synthseg(t1_path, parcellation_dir, device="cpu"):
    """Run WMH-SynthSeg processing pipeline
    
    Args:
        t1_path (str): Path to T1 image before bias correction and skull stripping
        parcellation_dir (str): Path to parcellation directory
    """
    try:
        # Use CPU to avoid GPU OOM errors and dimension mismatches from --crop flag
        # The --crop flag (needed for GPU) creates smaller output images that don't 
        # match dimensions with pred.nii.gz, causing fslmaths multiplication errors
        
        logger.info("Running WMH-SynthSeg segmentation...")
        
        # Output segmentation path 
        seg_path = os.path.join(parcellation_dir, "seg.nii.gz")
        
        # Run WMH-SynthSeg segmentation
        subprocess.run([
            "python",
            "/app/wmh_synthseg/WMHSynthSeg/inference.py",
            "--i", t1_path,
            "--o", seg_path,
            "--csv_vols", os.path.join(parcellation_dir, "vols.csv"),
            "--device", device,
            "--threads", "5"
        ],
                        capture_output=True,
                        text=True,
                        check=True)
        
        # Verify output file was created
        if not os.path.exists(seg_path):
            raise FileNotFoundError(f"WMH-SynthSeg failed to create output file: {seg_path}")
        
        logger.info(f"Segmentation file created successfully: {seg_path}")
        
        return seg_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in WMH-SynthSeg processing: {str(e)}")
        traceback.print_exc()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in WMH-SynthSeg processing: {str(e)}")
        traceback.print_exc()
        raise

def run_samseg(t1_path, parcellation_dir, device="cpu"):
    """Run SAMSEG processing pipeline
    
    Args:
        t1_path (str): Path to T1 image before bias correction and skull stripping
        parcellation_dir (str): Path to parcellation directory
    """
    try:
        
        # Run SAMSEG segmentation
        logger.info("Running SAMSEG segmentation...")
        
        # Output segmentation path 
        seg_path = os.path.join(parcellation_dir, "seg.nii.gz")
        
        subprocess.run([
            "run_samseg.sh",
            "--i", t1_path,
            "--o", seg_path,
            "--threads", "5"
        ],
                        capture_output=True,
                        text=True,
                        check=True)
        
        # Verify output file was created
        if not os.path.exists(seg_path):
            raise FileNotFoundError(f"SAMSEG failed to create output file: {seg_path}")

        logger.info(f"Segmentation file created successfully: {seg_path}")
        
        return seg_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error in SAMSEG processing: {str(e)}")
        traceback.print_exc()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in SAMSEG processing: {str(e)}")
        traceback.print_exc()
        raise