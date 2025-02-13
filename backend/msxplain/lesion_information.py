# %%
'''
For lesion information
Usage: python lesion_information.py <name for the output excel> <Subject1's ID> <Path to subject1's image> <Path to subject1's label mask> <Subject2's ID> <Path to subject2's image> <Path to subject2's label mask>

Example: python lesion_information.py report ID SMSC/PRLectrims/4031-5900/2021-1224/flair_3d_sbr.nii.gz SMSC/PRLectrims/4031-5900/2021-1224/lesion_mask_final.nii.gz SAMSEG

python lesion_information.py report ID SMSC/PRLectrims/4031-5900/2021-1224/flair_3d_sbr.nii.gz SAMSEG/pred.nii.gz SAMSEG

'''
import os
import nibabel as nib
import numpy as np
import pandas as pd
from scipy import ndimage
from pathlib import Path
import scipy.ndimage as ndimage
from msxplain.lesion_extraction import get_lesion_types_masks
import traceback

# project_directory = os.getcwd()
# df_name = '{0}.xlsx'.format(sys.argv[1])  # * Output file name

# save_each_subject = True  # * For each subject, save a table
# param_list = sys.argv[2:4]  # * ID, image and label
# path_samseg = sys.argv[4]

# save_labelmap = False


def dp(path1, path2):
    return os.path.join(path1, path2)


def form_cluster(label_data, struct=np.ones([3, 3, 3]), only_labelmap=False):
    if len(label_data.shape)==2:
        # print("A 2D image is given. Structural elements changes")
        struct = np.ones([3,3])
    label_map, _ = ndimage.label(label_data, structure=struct)
    if only_labelmap:
        return label_map
    unique_label, count_label = np.unique(label_map, return_counts=True)
    bg_ind = np.argwhere(unique_label == 0)
    unique_label = np.delete(unique_label, bg_ind)
    count_label = np.delete(count_label, bg_ind)
    return label_map, unique_label, count_label


def check_image_existence(file_path):
    if not os.path.isfile(file_path):
        print(file_path)
        raise FileNotFoundError(f"The {os.path.basename(file_path)} does not exist")


# image_name_list = param_list[0::3]
# mask_name_list = param_list[1::3]

# # %%
# for image_name, mask_name in zip(image_name_list, mask_name_list):
#     check_image_existence(image_name)
#     check_image_existence(mask_name)
    
#     print(image_name)
#     ID = (image_name.split("data/", 1)[1]).split("/flair", 1)[0].replace('/', '-')
#     print("Generating report for subject " + ID + "...")
    
#     img_proxy = nib.load(image_name)
#     img_affine = img_proxy.affine
#     img_data = img_proxy.get_fdata()
#     mask_proxy = nib.load(mask_name)
#     mask_data = mask_proxy.get_fdata()
#     image_path = Path(image_name)

#     unit_volume = np.asarray(mask_proxy.header['pixdim'][1:4]).prod()

#     df = pd.DataFrame(columns=['ID', 'Lesion Count', 'Lesion Type', 'Lesion Index', 'Lesion Center',
#                                'Lesion Voxels', 'Lesion Volume', 'Note'])

#     #label_map, unique_label, count_label = form_cluster(mask_data)
#     label_map = get_lesion_types_masks(mask_data, mask_data, 'non_zero', n_jobs = 1)['TPL']
#     #print("unpruned are: ", np.max(label_map))
#     label = 1
#     while label <= np.max(label_map):
#           patch_vector = np.where(label_map==label)
#           if len(patch_vector[0])<4:
#                label_map[label_map==label] = 0
#                label_map[label_map>label] = label_map[label_map>label] - 1
#           else:
#                label = label + 1     

#     n_labels = np.max(label_map)
#     #print("pruned are: ", n_labels)
    
#     unique_label = [element for element in range(1, n_labels)]
#     lesion_map = nib.Nifti1Image(label_map, img_affine)
#     nib.save(lesion_map, image_path.parent / f"lesion_map.nii.gz")

#     seg_cortex_undil = nib.load(path_samseg + '/Cortex.nii.gz').get_fdata()
#     seg_infratentorial_undil = nib.load(path_samseg + '/Infratentorial.nii.gz').get_fdata()
#     seg_ventricles_undil = nib.load(path_samseg + '/Ventricles.nii.gz').get_fdata()
#     seg_wm_undil = nib.load(path_samseg + '/WM_Mask.nii.gz').get_fdata()
    
#     struct1 = ndimage.generate_binary_structure(3, 1) # define shape of dilation
    
#     seg_cortex = ndimage.binary_dilation(seg_cortex_undil, structure=struct1, iterations=1)
#     seg_infratentorial = seg_infratentorial_undil.astype(int)
#     seg_ventricles = ndimage.binary_dilation(seg_ventricles_undil, structure=struct1, iterations=2).astype(int)
#     seg_wm = ndimage.binary_dilation(seg_wm_undil, structure=struct1, iterations=2).astype(int)
    
#     #if save_labelmap:
#     #    mask_file_name = os.path.basename(mask_name)
#     #    nib.save(nib.Nifti1Image(label_map, affine=img_proxy.affine, header=img_proxy.header), image_path.parent / f"lesion_map_{mask_file_name}")
#     for n, label_idx_in_label_map in enumerate(unique_label):

#         the_cluster = label_map == label_idx_in_label_map
#         masked_cluster = img_data[the_cluster]
#         lesion_seg = the_cluster.astype(int)
#         com = ndimage.center_of_mass(lesion_seg)
#         com = (com[0].astype(int), com[1].astype(int), com[2].astype(int))
        
#         cortex = np.sum(lesion_seg & seg_cortex)
#         infratentorial = bool(np.sum(lesion_seg & seg_infratentorial))
#         periventricular = bool(np.sum(lesion_seg & seg_ventricles))
#         wm = bool(np.sum(lesion_seg & seg_wm))      
#         if infratentorial:
#             lesion_type = 'Infratentorial'
#         elif periventricular:
#             lesion_type = 'Periventricular'
#         elif cortex > 5:
#             lesion_type = 'Juxtacortical'    
#         elif wm:
#             lesion_type = 'Deep White Matter'
#         else:
#             lesion_type = 'False Positive'                 
        
#         num_voxel = len(masked_cluster)
#         cluster_in_mask_data = np.unique(mask_data[the_cluster])
#         note = ''
#         if len(cluster_in_mask_data) > 1:
#             note = ''.join(str(element)
#                            for element in cluster_in_mask_data[1:])
#             cluster_in_mask_data = cluster_in_mask_data[0]
#         if n==0:
#             lesion_number = np.max(unique_label)
#         else:
#             lesion_number = None    
#         #mean_value = masked_cluster.mean()
#         #std_value = masked_cluster.std()

#         df.loc[n] = [ID, lesion_number, lesion_type, label_idx_in_label_map, com, num_voxel,
#                      num_voxel*unit_volume, note]
#     df = df.sort_values(by=['Lesion Index'])
#     if save_each_subject:
#         df.to_excel(image_path.parent/ '{}_{}.xlsx'.format(
#             df_name.replace('.xlsx', ''), ID), index=False)
#     if os.path.isfile(dp(project_directory, df_name)):
#         df_old = pd.read_excel(dp(project_directory, df_name))
#         df = pd.concat([df_old, df], sort=False, ignore_index=True)
#     df.to_excel(dp(project_directory, df_name), index=False)

# # %%

def generate_lesion_report(patient_id, flair_path, pred_path, samseg_path, save_each_subject=True):
    """Generate lesion information report for a specific patient
    
    Args:
        patient_id (str): Patient identifier
        flair_path (str): Path to FLAIR image
        pred_path (str): Path to prediction mask
        samseg_path (str): Path to SAMSEG directory
        save_each_subject (bool): Whether to save individual subject reports
    """
    try:
        print(f"Generating report for subject {patient_id}...")
        
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
        seg_cortex_undil = nib.load(os.path.join(samseg_path, 'Cortex.nii.gz')).get_fdata()
        seg_infratentorial_undil = nib.load(os.path.join(samseg_path, 'Infratentorial.nii.gz')).get_fdata()
        seg_ventricles_undil = nib.load(os.path.join(samseg_path, 'Ventricles.nii.gz')).get_fdata()
        seg_wm_undil = nib.load(os.path.join(samseg_path, 'WM_Mask.nii.gz')).get_fdata()

        # Define dilation structure
        struct1 = ndimage.generate_binary_structure(3, 1)

        # Process segmentation masks
        seg_cortex = ndimage.binary_dilation(seg_cortex_undil, structure=struct1, iterations=1)
        seg_infratentorial = seg_infratentorial_undil.astype(int)
        seg_ventricles = ndimage.binary_dilation(seg_ventricles_undil, structure=struct1, iterations=2).astype(int)
        seg_wm = ndimage.binary_dilation(seg_wm_undil, structure=struct1, iterations=2).astype(int)

        # Process each lesion
        for n, label_idx_in_label_map in enumerate(unique_label):
            the_cluster = label_map == label_idx_in_label_map
            masked_cluster = img_data[the_cluster]
            lesion_seg = the_cluster.astype(int)
            com = ndimage.center_of_mass(lesion_seg)
            com = (int(com[0]), int(com[1]), int(com[2]))

            # Determine lesion type
            cortex = np.sum(lesion_seg & seg_cortex)
            infratentorial = bool(np.sum(lesion_seg & seg_infratentorial))
            periventricular = bool(np.sum(lesion_seg & seg_ventricles))
            wm = bool(np.sum(lesion_seg & seg_wm))

            if infratentorial:
                lesion_type = 'Infratentorial'
            elif periventricular:
                lesion_type = 'Periventricular'
            elif cortex > 5:
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
        
        if save_each_subject:
            output_path = image_path.parent / f'report_{patient_id}.xlsx'
            df.to_excel(output_path, index=False)
            print(f"Report saved to {output_path}")
            
        return df
        
    except Exception as e:
        print(f"Error generating lesion report: {str(e)}")
        traceback.print_exc()
        raise
