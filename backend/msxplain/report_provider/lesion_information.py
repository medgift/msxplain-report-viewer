# %%
'''
For lesion information
Usage: python lesion_information.py <name for the output excel> <Subject1's ID> <Path to subject1's image> <Path to subject1's label mask> <Subject2's ID> <Path to subject2's image> <Path to subject2's label mask>

Example: python lesion_information.py report ID SMSC/PRLectrims/4031-5900/2021-1224/flair_3d_sbr.nii.gz SMSC/PRLectrims/4031-5900/2021-1224/lesion_mask_final.nii.gz SAMSEG

python lesion_information.py report ID SMSC/PRLectrims/4031-5900/2021-1224/flair_3d_sbr.nii.gz SAMSEG/pred.nii.gz SAMSEG

'''
import logging
import os
import nibabel as nib
import numpy as np
import pandas as pd
from scipy import ndimage
from pathlib import Path
import scipy.ndimage as ndimage
from .lesion_extraction import get_lesion_types_masks
import traceback

logger = logging.getLogger(__name__)

def check_image_existence(file_path):
    if not os.path.isfile(file_path):
        logger.debug(file_path)
        raise FileNotFoundError(f"The {os.path.basename(file_path)} does not exist")


def generate_lesion_report(patient_id, flair_path, pred_path, parcellation_path):
    """Generate lesion information report for a specific patient
    
    Args:
        patient_id (str): Patient identifier
        flair_path (str): Path to FLAIR image
        pred_path (str): Path to prediction mask
        parcellation_path (str): Path to parcellation directory
        save_each_subject (bool): Whether to save individual subject reports
    """
    try:
        logger.info(f"Generating report for subject {patient_id}...")
        
        # Check files exist
        check_image_existence(flair_path)
        check_image_existence(pred_path)
        
        # Load images
        img_proxy = nib.load(flair_path)
        img_affine = img_proxy.affine
        img_data = img_proxy.get_fdata()
        mask_proxy = nib.load(pred_path)
        mask_data = mask_proxy.get_fdata()
        image_path = Path(flair_path)

        # Calculate unit volume
        unit_volume = np.asarray(mask_proxy.header['pixdim'][1:4]).prod()

        # Create DataFrame
        df = pd.DataFrame(columns=[
            'ID', 'Lesion Count', 'Lesion Type', 'Lesion Index',
            'Lesion Center', 'Lesion Voxels', 'Lesion Volume', 'Note'
        ])

        # Get lesion map and prune small lesions
        label_map = get_lesion_types_masks(mask_data, mask_data, 'non_zero', n_jobs=1)['TPL']
        
        label = 1
        while label <= np.max(label_map):
            patch_vector = np.where(label_map==label)
            if len(patch_vector[0])<4:
                label_map[label_map==label] = 0
                label_map[label_map>label] = label_map[label_map>label] - 1
            else:
                label = label + 1

        n_labels = np.max(label_map)
        unique_label = [element for element in range(1, n_labels+1)]
        
        # Save lesion map
        lesion_map = nib.Nifti1Image(label_map, img_affine)
        nib.save(lesion_map, image_path.parent / "lesion_map.nii.gz")

        # Load segmentation masks
        seg_cortex_undil = nib.load(os.path.join(parcellation_path, 'Cortex.nii.gz')).get_fdata()
        seg_infratentorial_undil = nib.load(os.path.join(parcellation_path, 'Infratentorial.nii.gz')).get_fdata()
        seg_ventricles_undil = nib.load(os.path.join(parcellation_path, 'Ventricles.nii.gz')).get_fdata()
        seg_wm_undil = nib.load(os.path.join(parcellation_path, 'WM_Mask.nii.gz')).get_fdata()

        # Define dilation structure
        struct1 = ndimage.generate_binary_structure(3, 1)

        # Process segmentation masks
        seg_cortex = ndimage.binary_dilation(seg_cortex_undil, structure=struct1, iterations=1)
        seg_infratentorial = ndimage.binary_dilation(seg_infratentorial_undil, structure=struct1, iterations=1).astype(int)
        seg_ventricles = ndimage.binary_dilation(seg_ventricles_undil, structure=struct1, iterations=1).astype(int)
        seg_wm = ndimage.binary_dilation(seg_wm_undil, structure=struct1, iterations=2).astype(int)

        # Process each lesion
        for n, label_idx_in_label_map in enumerate(unique_label):
            the_cluster = label_map == label_idx_in_label_map
            masked_cluster = img_data[the_cluster]
            lesion_seg = the_cluster.astype(int)
            com = ndimage.center_of_mass(lesion_seg)
            com = (int(com[0]), int(com[1]), int(com[2]))

            # Determine lesion type
            cortex = bool(np.sum(lesion_seg & seg_cortex))
            infratentorial = bool(np.sum(lesion_seg & seg_infratentorial))
            periventricular = bool(np.sum(lesion_seg & seg_ventricles))
            wm = bool(np.sum(lesion_seg & seg_wm))

            if infratentorial:
                lesion_type = 'Infratentorial'
            elif periventricular:
                lesion_type = 'Periventricular'
            elif cortex:
                lesion_type = 'Juxtacortical'
            elif wm:
                lesion_type = 'Deep White Matter'
            else:
                lesion_type = 'False Positive'

            # Calculate lesion properties
            num_voxel = len(masked_cluster)
            cluster_in_mask_data = np.unique(mask_data[the_cluster])
            note = ''
            if len(cluster_in_mask_data) > 1:
                note = ''.join(str(element) for element in cluster_in_mask_data[1:])
                cluster_in_mask_data = cluster_in_mask_data[0]

            lesion_number = np.max(unique_label) if n==0 else None

            # Add to DataFrame
            df.loc[n] = [
                patient_id, lesion_number, lesion_type, label_idx_in_label_map,
                com, num_voxel, num_voxel*unit_volume, note
            ]

        # Sort and save results
        df = df.sort_values(by=['Lesion Index'])
            
        return df
        
    except Exception as e:
        logger.error(f"Error generating lesion report: {str(e)}")
        traceback.print_exc()
        raise
