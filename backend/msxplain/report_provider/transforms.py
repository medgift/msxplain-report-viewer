from monai.transforms import Compose, CopyItemsd, Lambdad, EnsureChannelFirstd, Identityd, LoadImaged, NormalizeIntensityd, \
    ConcatItemsd, DeleteItemsd, ToTensord, RandCropByPosNegLabeld, RandSpatialCropd, RandCropByLabelClassesd, \
    RandShiftIntensityd, RandScaleIntensityd, RandFlipd, RandRotate90d, RandAffined
from scipy import ndimage
import numpy as np
import torch

def get_cc_mask(binary_mask):
    """Generate connected component mask from binary mask"""
    if binary_mask.ndim != 3:
        raise ValueError(f"Mask must have 3 dimensions, got {binary_mask.ndim}.")
    struct_el = ndimage.generate_binary_structure(rank=3, connectivity=2)
    labeled_mask, _ = ndimage.label(binary_mask, structure=struct_el)
    return labeled_mask.astype('float32')


def process_probs(prob_map, threshold, l_min):
    """Process probability map: apply threshold and remove small connected components"""
    # Apply threshold
    binary_mask = binarize_mask(prob_map, threshold)
    # Remove small connected components
    processed_mask = remove_connected_components(binary_mask, l_min)
    return processed_mask

def remove_connected_components(segmentation, l_min=3):
    """Remove small lesions leq than `l_min` voxels from the binary segmentation mask.
    """
    if segmentation.ndim != 3:
        raise ValueError(f"Mask must have 3 dimensions, got {segmentation.ndim}.")
    struct_el = ndimage.generate_binary_structure(rank=3, connectivity=2)
    labeled_seg, num_labels = ndimage.label(segmentation, structure=struct_el)
    segmentation_tr = np.zeros_like(segmentation)
    for label in range(1, num_labels + 1):
        if np.sum(labeled_seg == label) > l_min:
            segmentation_tr[labeled_seg == label] = 1
    return segmentation_tr


def binarize_mask(prob_map, threshold):
    """Apply threshold to probability mask """
    if isinstance(prob_map, np.ndarray):
        binary_mask = prob_map.copy()
        binary_mask[binary_mask >= threshold] = 1.0
        binary_mask[binary_mask < threshold] = 0.0
    elif isinstance(prob_map, torch.Tensor):
        binary_mask = prob_map.clone()
        binary_mask[binary_mask >= threshold] = 1.0
        binary_mask[binary_mask < threshold] = 0.0
    else:
        raise TypeError(f"Type {type(binarize_mask)} is not supported.")
    return binary_mask


def get_valnotarget_transforms(input_keys: list, binarize_keys: list = None, generate_instance_mask: bool = False):
    """
    Validation transforms without target labels (for inference)
    :param input_keys: mri contrast keys
    :param binarize_keys: keys of multi label masks to be binarized
    :param generate_instance_mask: if True, will generate instance segmentation targets mask
    :return: monai.transforms.Compose instance
    """
    all_keys = input_keys
    all_tr_keys = ["inputs"]
    geninstm_transform = Identityd(keys=all_keys)
    if binarize_keys is not None:
        all_keys += binarize_keys
        all_tr_keys += binarize_keys
        bin_transform = Lambdad(keys=binarize_keys, func=lambda x: (x > 0).astype(x.dtype))
    else:
        bin_transform = Identityd(keys=all_keys)
    return Compose(
        [
            LoadImaged(keys=all_keys),
            geninstm_transform,
            EnsureChannelFirstd(keys=all_keys), bin_transform,
            NormalizeIntensityd(keys=input_keys, nonzero=True),
            ConcatItemsd(keys=input_keys, name="inputs"), DeleteItemsd(keys=input_keys),
            ToTensord(keys=all_tr_keys)
        ]
    )
