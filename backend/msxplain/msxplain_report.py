import os
import glob
import subprocess
import traceback
from pathlib import Path
import time
import pydicom
import SimpleITK as sitk
import torch
import pandas as pd
import logging
from contextlib import contextmanager
from .report_provider.predict import predict_msxplain
from .report_provider.parcellation_processing import run_parcellation
from .report_provider.lesion_information import generate_lesion_report
from .report_provider.ensemble_inference import run_ensemble_inference
from .report_provider.compute_uncertainty import compute_uncertainties
from .utils.utils import transform_registration_params
from .seglib.segmentation import Segmentation

logger = logging.getLogger(__name__)


@contextmanager
def suppress_logging(level=logging.CRITICAL):
    """Context manager to temporarily suppress logging"""
    previous_level = logging.root.level
    logging.root.setLevel(level)
    try:
        yield
    finally:
        logging.root.setLevel(previous_level)


# def load_config():
#     config_path = Path(__file__).parent.parent / 'config.yml'
#     with open(config_path, 'r') as f:
#         return yaml.safe_load(f)

# # Load configuration
# config = load_config()

# # Set FSLDIR and FREESURFER and ANTs PATH
# # Use environment variables if available (for Docker), otherwise use config
# fsl_dir = os.environ.get("FSLDIR", config['paths']['fsl_dir'])
# # For Docker, check if FSL is in the expected Docker locations
# if os.path.exists("/usr/share/fsl/6.0/bin/fslorient"):
#     fsl_dir = "/usr/share/fsl/6.0"
# elif os.path.exists("/usr/share/fsl/bin/fslorient"):
#     fsl_dir = "/usr/share/fsl"
# os.environ["FSLDIR"] = fsl_dir
# os.environ["PATH"] += os.pathsep + os.path.join(fsl_dir, "bin")
# os.environ['FSLOUTPUTTYPE'] = 'NIFTI_GZ'
# print(f"FSL configured: FSLDIR={fsl_dir}")
# print(f"PATH includes: {os.environ['PATH']}")

# Debug: Check if fslorient is actually available
# import subprocess
# try:
#     result = subprocess.run(['which', 'fslorient'], capture_output=True, text=True, env=os.environ.copy())
#     if result.returncode == 0:
#         print(f"fslorient found at: {result.stdout.strip()}")
#     else:
#         print("fslorient not found in PATH")
#         # Let's check common locations
#         potential_paths = [
#             "/usr/share/fsl/6.0/bin/fslorient",
#             "/usr/share/fsl/bin/fslorient",
#             "/usr/share/fsl/share/fsl/bin/fslorient"
#         ]
#         for path in potential_paths:
#             if os.path.exists(path):
#                 print(f"Found fslorient at: {path}")
# except Exception as e:
#     print(f"Error checking fslorient: {e}")

# freesurfer_home = os.environ.get("FREESURFER_HOME", config['paths']['freesurfer_home'])
# os.environ["FREESURFER_HOME"] = freesurfer_home
# os.environ["PATH"] += os.pathsep + os.path.join(freesurfer_home, "bin")
# print(f"FreeSurfer configured: FREESURFER_HOME={freesurfer_home}")

# ants_path = os.environ.get("ANTSPATH", config['paths']['ants_dir'])
# # Handle both cases where ants_dir might include /install or not
# if not ants_path.endswith('/install') and not ants_path.endswith('/bin'):
#     if os.path.exists(os.path.join(ants_path, 'install')):
#         ants_dir = os.path.join(ants_path, "install")
#     else:
#         ants_dir = ants_path
# else:
#     ants_dir = ants_path
# os.environ["ANTsDIR"] = ants_dir
# os.environ["PATH"] += os.pathsep + os.path.join(ants_dir, "bin")
# print(f"ANTs configured: ANTsDIR={ants_dir}")
# print(f"PATH includes: {os.environ['PATH']}")

class MSXplainReport:
    def __init__(self, flair_dir: str, t1_dir: str, output_dir: str):
        """Initialize MSXplain Report Generator

        Args:
            flair_dir (str): Directory containing FLAIR DICOM series
            t1_dir (str): Directory containing T1 DICOM series
            output_dir (str): Directory where to save results
        """
        self.flair_dir = flair_dir
        self.t1_dir = t1_dir
        
        # Get patient ID from DICOM metadata
        self.patient_id = self.get_patient_id()
        
        # Don't append patient_id here since output_dir already includes it
        self.output_dir = output_dir
        self.parcellation_dir = os.path.join(self.output_dir, "SYNTHSEG")
        
        # Create output directories
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.parcellation_dir, exist_ok=True)
        
        # Path to MSXplain resources
        self.msxplain_dir = Path(__file__).parent.absolute()
        self.model_checkpoint = str(self.msxplain_dir / "model" / "model_epoch_61.pth")
        self.registration_params = str(self.msxplain_dir / "configs/Parameters_Rigid.txt")
        
        # Validate model file exists
        if not os.path.exists(self.model_checkpoint):
            raise FileNotFoundError(f"Model file not found at: {self.model_checkpoint}")

    def get_patient_id(self):
        """Extract patient ID from DICOM metadata"""
        try:
            # Look for DICOM files in FLAIR directory
            dicom_files = glob.glob(os.path.join(self.flair_dir, '*'))
            
            if not dicom_files:
                raise FileNotFoundError(f"No DICOM files found in {self.flair_dir}")
            
            # Read first DICOM file
            ds = pydicom.dcmread(dicom_files[0])
            
            # Try to get Patient ID
            if hasattr(ds, 'PatientID') and ds.PatientID:
                patient_id = ds.PatientID
            # Fallback to other identifiers if PatientID is not available
            elif hasattr(ds, 'PatientName') and ds.PatientName:
                patient_id = str(ds.PatientName).replace('^', '_')
            else:
                # Generate timestamp-based ID if no identifier is found
                patient_id = f"PATIENT_{time.strftime('%Y%m%d_%H%M%S')}"
            
            # Clean the ID to be filesystem-friendly
            patient_id = ''.join(c for c in patient_id if c.isalnum() or c in '_-')
            
            logger.info(f"Using Patient ID: {patient_id}")
            return patient_id
            
        except Exception as e:
            logger.error(f"Error getting patient ID: {str(e)}")
            traceback.print_exc()
            # Fallback to timestamp if there's an error
            return f"PATIENT_{time.strftime('%Y%m%d_%H%M%S')}"

    def run_command(self, command):
        """Run a shell command and handle errors"""
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                env=os.environ.copy()  # Pass current environment variables
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"Command failed: {stderr}")
                
            return stdout
        except Exception as e:
            logger.error(f"Error running command {' '.join(command)}: {str(e)}")
            traceback.print_exc()
            raise

    def convert_dicoms_to_nifti(self):
        """Convert DICOM series to NIFTI format"""
        logger.info("Converting DICOM series to NIFTI...")
        
        # Convert FLAIR
        flair_command = [
            "dcm2niix",
            "-z", "y",  # compress output
            "-f", "flair",  # output filename
            "-o", self.output_dir,  # output directory
            self.flair_dir  # input DICOM directory
        ]
        self.run_command(flair_command)
        
        # Convert T1
        t1_command = [
            "dcm2niix",
            "-z", "y",
            "-f", "t1",
            "-o", self.output_dir,
            self.t1_dir
        ]
        self.run_command(t1_command)
        
        # Return paths to generated NIFTI files
        return {
            'flair': os.path.join(self.output_dir, "flair.nii.gz"),
            't1': os.path.join(self.output_dir, "t1.nii.gz")
        }

    def preprocess_images(self, nifti_files):
        """Run preprocessing steps on NIFTI files"""
        logger.info("Running FSL orientation...")
        
        # FSL orientation steps
        for img_path in [nifti_files['flair'], nifti_files['t1']]:
            self.run_command(["fslorient", "-copysform2qform", img_path])
            self.run_command(["fslreorient2std", img_path])
        
        # N4 Bias field correction
        logger.info("Running N4 Bias field correction...")
        
        for img_type in ['flair', 't1']:
            input_path = nifti_files[img_type]
            output_path = os.path.join(self.output_dir, f"{img_type}_n4.nii.gz")
            self.run_command([
                "N4BiasFieldCorrection",
                "-i", input_path,
                "-o", output_path
            ])
            nifti_files[f"{img_type}_n4"] = output_path
            
        
        # Brain extraction
        logger.info("Running Brain extraction...")
        
        device = "0" if torch.cuda.is_available() else "cpu"
        logger.info(f"HD-BET will use device: {device}")
        
        for img_type in ['flair', 't1']:
            input_path = nifti_files[f"{img_type}_n4"]
            output_path = os.path.join(self.output_dir, f"{img_type}_brain.nii.gz")
            self.run_command([
                "hd-bet",
                "-i", input_path,
                "-o", output_path,
                "-device", device,
                "-mode", "fast",
                "-tta", "0"
            ])
            nifti_files[f"{img_type}_brain"] = output_path

        # ANTs registration as alternative/verification
        logger.info("Running ANTs registration...")
        reg_dir = os.path.join(self.output_dir, "registration")
        os.makedirs(reg_dir, exist_ok=True)
        
        ants_output_prefix = os.path.join(reg_dir, "ants_")
        self.run_command([
            "antsRegistration",
            "--dimensionality", "3",
            "--float", "0",
            "--output", f"[{ants_output_prefix},{ants_output_prefix}registration.nii.gz]",
            "--winsorize-image-intensities", "[0.005,0.995]",
            "--use-histogram-matching", "0",
            "--initial-moving-transform", f"[{nifti_files['t1_brain']},{nifti_files['flair_brain']},1]",
            "--transform", "Rigid[0.1]",
            "--metric", f"Mattes[{nifti_files['t1_brain']},{nifti_files['flair_brain']},1,32,Regular,0.25]",
            "--convergence", "[1000x500x250x100,1e-6,10]",
            "--shrink-factors", "8x4x2x1",
            "--smoothing-sigmas", "3x2x1x0vox"
        ])
        
        # Move registered FLAIR
        registered_flair = os.path.join(reg_dir, "ants_registration.nii.gz")
        final_flair = os.path.join(self.output_dir, "flair_registered.nii.gz")
        os.rename(registered_flair, final_flair)
        nifti_files['flair_registered'] = final_flair
        
        return nifti_files
    
    def register_lesion_map_to_flair_ants(self):
        """Inverse ANTs rigid transform lesion_map (in T1 space) back to original FLAIR space using ANTs."""
        try:
            reg_dir = os.path.join(self.output_dir, "registration")
            flair_brain = os.path.join(self.output_dir, "flair_brain.nii.gz")
            lesion_map = os.path.join(self.output_dir, "lesion_map.nii.gz")

            forward_mat = os.path.join(reg_dir, "ants_0GenericAffine.mat")
            if not os.path.exists(forward_mat):
                raise FileNotFoundError(f"Forward ANTs affine not found: {forward_mat}")
            if not os.path.exists(lesion_map):
                raise FileNotFoundError(f"Lesion map not found: {lesion_map}")

            # Apply inverse transform to lesion map using antsApplyTransforms
            # Using [transform, 1] applies the inverse of the transform
            output_path = os.path.join(self.output_dir, "lesion_map_flair_space_ants.nii.gz")
            
            logger.info("Applying inverse ANTs transform to lesion map...")
            self.run_command([
                "antsApplyTransforms",
                "-d", "3",
                "-i", lesion_map,
                "-r", flair_brain,
                "-t", f"[{forward_mat},1]",  # [transform, 1] means apply inverse
                "-n", "NearestNeighbor",
                "-o", output_path
            ])

            return output_path
        except Exception as e:
            logger.error(f"Error inverse transforming lesion map with ANTs: {e}")
            traceback.print_exc()
            return None
    
    def register_lesion_map_to_flair(self):
        """Transform lesion map to the original space"""
        
        try:

            fixed_image_path = f'{self.output_dir}/flair_brain.nii.gz'
            moving_image_path = f'{self.output_dir}/lesion_map.nii.gz'

            # Read transform parameters from file
            param_file = f'{self.output_dir}/registration/TransformParameters.0.txt'


            # Get transform parameters from file
            rotation_angles, translation, center_of_rotation = transform_registration_params(param_file)

            # Load the lesion map and FLAIR image
            lesion_map = sitk.ReadImage(moving_image_path, sitk.sitkFloat32)
            flair_image = sitk.ReadImage(fixed_image_path, sitk.sitkFloat32)

            # Create original Euler transform
            transform = sitk.Euler3DTransform()
            transform.SetCenter(center_of_rotation)
            transform.SetRotation(*rotation_angles)
            transform.SetTranslation(translation)

            # Invert the transform
            inverse_transform = transform.GetInverse()

            # Resample lesion map into original FLAIR space
            lesion_map_flair_space = sitk.Resample(lesion_map,
                                                flair_image,
                                                inverse_transform,
                                                sitk.sitkNearestNeighbor,  # Use NN for labels
                                                0.0,  # Default pixel value
                                                lesion_map.GetPixelID())

            sitk.WriteImage(lesion_map_flair_space, f"{self.output_dir}/lesion_map_flair_space.nii.gz")
            
            return True
        
        except Exception as e:
            logger.error(f"Error in registering lesion map: {str(e)}")
            traceback.print_exc()
            return None

    def run_msxplain(self, nifti_files):
        """Run MSXplain ensemble prediction, uncertainty computation, and processing"""
        
        # Check if we have ensemble models for uncertainty computation
        ensemble_model_dir = self.msxplain_dir / "ensemble_models"
        ckpt_files = list(ensemble_model_dir.glob("*.ckpt")) if ensemble_model_dir.exists() else []
        
        if len(ckpt_files) > 0:
            # Use ensemble inference + uncertainty computation
            logger.info(f"Found {len(ckpt_files)} ensemble models, running ensemble inference with uncertainty...")
            
            # Run ensemble inference to generate NPZ file
            run_ensemble_inference(
                flair_path=os.path.join(self.output_dir, "flair_registered.nii.gz"),
                mprage_path=os.path.join(self.output_dir, "t1_brain.nii.gz"),
                output_path=self.output_dir,
                models_path=str(ensemble_model_dir)
            )
        
            # Compute uncertainties
            logger.info("Computing uncertainties...")
            
            try:
                compute_uncertainties(
                    output_dir=str(self.output_dir),
                    n_samples=len(ckpt_files),
                    proba_threshold=0.5,
                    n_jobs=4,
                    l_min=2
                )
                logger.info("Uncertainty computation completed")
            except Exception as e:
                logger.warning(f"Uncertainty computation failed: {e}")
                traceback.print_exc()
                
            # Use the pred.nii.gz file generated by uncertainty computation
            prediction_file = os.path.join(self.output_dir, "pred.nii.gz")
                
        else:
            # Fallback to standard prediction
            logger.info("No ensemble models found, using standard prediction")
            prediction_file = self._run_standard_prediction(nifti_files)
        
        # Run Parcellation processing
        run_parcellation(
            t1_path=os.path.join(self.output_dir, "t1.nii.gz"),
            pred_path=prediction_file,
            parcellation_dir=self.parcellation_dir
        )
        
        with torch.no_grad():
            torch.cuda.empty_cache()

        return prediction_file
    
    def _run_standard_prediction(self, nifti_files):
        """Fallback method for standard (non-ensemble) prediction"""
        logger.info("Running standard MSXplain prediction...")
        
        prediction_file = predict_msxplain(
            input_val_paths=[self.output_dir, self.output_dir],
            input_prefixes=["flair_registered.nii.gz", "t1_brain.nii.gz"],
            model_checkpoint=self.model_checkpoint,
            parcellation_dir=self.parcellation_dir,
            num_workers=0,
            cache_rate=0.1,
            threshold=0.3,
            force_cuda=True
        )
        
        return prediction_file

    def generate_report(self, prediction_file):
        """Generate the final report"""
        
        report_df = generate_lesion_report(
            patient_id=self.patient_id,
            flair_path=os.path.join(self.output_dir, "flair_registered.nii.gz"),
            pred_path=prediction_file,
            parcellation_path=self.parcellation_dir
        )
        
        report_path = os.path.join(self.output_dir, f"report.csv")
        report_df.to_csv(report_path, index=False)
        
        return report_df
    
    def compute_labels(self, report_df):
        
        # Get labels from report_df, excluding False Positive lesions
        # Format: Lesion Type (lesion uncertainty) if LLU is available
        if 'LLU' in report_df.columns:
            roi_names = report_df.apply(
                lambda row: f"{row['Lesion Type']} ({row['LLU']:.3f})" if pd.notna(row['LLU']) else row['Lesion Type'],
                axis=1
            )
        else:
            roi_names = report_df['Lesion Type']
        
        labels_df = pd.DataFrame({
            'roi_id': report_df['Lesion Index'],
            'roi_name': roi_names
        })
        
        # Filter out False Positive labels for DCM-SEG conversion
        # Use .str.startswith to handle both "False Positive" and "False Positive (uncertainty)"
        labels_df = labels_df[~labels_df['roi_name'].astype(str).str.startswith('False Positive')]
        
        labels_path = os.path.join(self.output_dir, "labels.csv")
        labels_df.to_csv(labels_path, index=False, header=False)
        
        return Path(labels_path)
    
    def create_filtered_lesion_map(self, lesion_map_path, report_df, suffix="_dcmseg"):
        """Create a filtered lesion map without False Positive lesions for DCM-SEG conversion
        
        Args:
            lesion_map_path: Path to the original lesion map NIFTI file
            report_df: DataFrame containing lesion information
            suffix: Suffix to add to the output filename (default: "_dcmseg")
            
        Returns:
            Tuple of (Path to the lesion map, bool indicating if filtering was performed)
            If no False Positives: returns (original_path, False)
            If False Positives filtered: returns (filtered_path, True)
        """
        # Get False Positive lesion indices
        false_positive_indices = report_df[report_df['Lesion Type'] == 'False Positive']['Lesion Index'].tolist()
        
        if not false_positive_indices:
            logger.info("No False Positive lesions found, using original lesion map")
            return Path(lesion_map_path), False
        
        logger.info(f"Filtering out {len(false_positive_indices)} False Positive lesions: {false_positive_indices}")
        
        # Load the lesion map
        lesion_img = sitk.ReadImage(str(lesion_map_path))
        lesion_data = sitk.GetArrayFromImage(lesion_img)
        
        # Create a copy for filtering
        filtered_data = lesion_data.copy()
        
        # Remove False Positive lesions by setting their voxels to 0
        for fp_index in false_positive_indices:
            filtered_data[lesion_data == fp_index] = 0
        
        # Create output path
        base_name = os.path.splitext(os.path.splitext(os.path.basename(lesion_map_path))[0])[0]
        output_path = os.path.join(self.output_dir, f"{base_name}{suffix}.nii.gz")
        
        # Create new image with filtered data
        filtered_img = sitk.GetImageFromArray(filtered_data)
        filtered_img.CopyInformation(lesion_img)
        
        # Save filtered lesion map
        sitk.WriteImage(filtered_img, output_path)
        
        return Path(output_path), True

    def nifti_to_dcmseg(self, lesion_map, labels_path, dcm_ref, out_basename):
        """Convert NIFTI to DCM-SEG"""
        
        # Convert NIFTI to DCM-SEG
        myseg = Segmentation(p_seg=lesion_map,
                         p_labels=labels_path,
                         p_dcm_ref=dcm_ref,
                         mask_glob='*desc-*',
                         regex='desc-\w+',
                         rtstruct_converter='dcmrtstruct2nii',
                         precision=5,)
        
        logger.info("Writing DCM-SEG file...")
        with suppress_logging():
            myseg.write_seg(p=Path(self.output_dir),
                            base_name=out_basename,
                            mode='dcmseg',
                            no_overlap = 'enforce',
                            p_ref=dcm_ref
                            )
