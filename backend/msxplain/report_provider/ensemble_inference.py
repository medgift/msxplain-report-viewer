#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ensemble inference script for MS lesion segmentation.

This script runs ensemble prediction using multiple SwinUNETR models and saves
the results to NPZ format for subsequent uncertainty computation.

Author: Po-Jui Lu
Email: p.lu@unibas.ch
Version: 1.0
"""

import os
from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import Dict
from .model import SwinUNETR
import nibabel as nib
import numpy as np
import pytorch_lightning as pl
import scipy.ndimage as ndimage
import torch
import logging
from monai.data import CacheDataset, DataLoader
from monai.inferers import sliding_window_inference
from monai.transforms import (
    AsDiscrete,
    Compose,
    ConcatItemsd,
    CropForeground,
    CropForegroundd,
    LoadImaged,
    MapTransform,
    SelectItemsd,
    NormalizeIntensityd,
    Spacingd,
)
from monai.transforms.utils import allow_missing_keys_mode

logging.getLogger("pytorch_lightning").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


# ============================================================================
# Custom Transforms
# ============================================================================

class EnsureNDd(MapTransform):
    """
    Ensure input images are N-dimensional tensors with channel-first.
    Missing dimensions will be added as singleton axes.
    
    Example target:
        ndim=5  -> output shape (C, D, H, W, T)
        ndim=4  -> output shape (C, H, W, D)
        ndim=3  -> output shape (C, H, W)
    """

    def __init__(self, keys, ndim=5, allow_missing_keys=False):
        super().__init__(keys, allow_missing_keys)
        self.ndim = ndim

    def __call__(self, data):
        d = dict(data)
        for key in self.keys:
            img = torch.as_tensor(d[key])

            # Ensure channel dimension exists
            if img.ndim == self.ndim:
                d[key] = img
                continue

            if img.ndim == self.ndim - 1:
                # Assume missing channel → add channel at front
                img = img.unsqueeze(0)

            elif img.ndim < self.ndim:
                # If fewer dimensions, add channel if missing
                if img.ndim == 3:  # (H, W, D) or (H, W, T)
                    img = img.unsqueeze(0)  # (C=1, H, W, D/T)
                elif img.ndim == 2:  # (H, W)
                    img = img.unsqueeze(0)  # (C=1, H, W)

                # Pad until reaching ndim
                while img.ndim < self.ndim:
                    img = img.unsqueeze(0)

            elif img.ndim > self.ndim:
                raise ValueError(
                    f"Input {key} has {img.ndim} dims, which is more than target {self.ndim}."
                )

            d[key] = img
        return d


class CropForegroundChanged(CropForegroundd):
    """
    Dictionary-based version of CropForeground with margin added to bounding box.
    
    Crop only the foreground object of the expected images.
    The typical usage is to help training and evaluation if the valid part is small 
    in the whole medical image.
    """

    def __call__(self, data: Mapping[Hashable, torch.Tensor], lazy: bool | None = None) -> dict[Hashable, torch.Tensor]:
        d = dict(data)
        self.cropper: CropForeground
        box_start, box_end = self.cropper.compute_bounding_box(img=d[self.source_key])
        box_start -= 8
        box_end += 8
        if self.start_coord_key is not None:
            d[self.start_coord_key] = box_start  # type: ignore
        if self.end_coord_key is not None:
            d[self.end_coord_key] = box_end  # type: ignore

        lazy_ = self.lazy if lazy is None else lazy
        for key, m in self.key_iterator(d, self.mode):
            d[key] = self.cropper.crop_pad(img=d[key], box_start=box_start, box_end=box_end, mode=m, lazy=lazy_)
        return d


# ============================================================================
# Helper Functions
# ============================================================================

def form_cluster(data_array, struct=np.ones([3, 3, 3]), only_labelmap=False):
    """Get individual clusters with connected component labeling.

    Args:
        data_array (numpy array): The image, where to find clusters
        struct (numpy array or scipy struct array, optional): The connectivity. 
            Defaults to np.ones([3, 3, 3]) for all-direction connectivity.
        only_labelmap (bool): If True, only return the label map

    Returns:
        label_map (numpy array): The image having labeled clusters.
        unique_label (numpy array): The array containing unique cluster indices.
        label_counts (numpy array): The corresponding voxel numbers.
    """
    if len(data_array.shape) == 2:
        struct = np.ones([3, 3])
    
    label_map, _ = ndimage.label(data_array, structure=struct)
    
    if only_labelmap:
        return label_map
    
    unique_label, count_label = np.unique(label_map, return_counts=True)
    bg_ind = np.argwhere(unique_label == 0)
    unique_label = np.delete(unique_label, bg_ind)
    count_label = np.delete(count_label, bg_ind)
    
    return label_map, unique_label, count_label


def dp(path1: str, path2: str) -> str:
    """Join two paths."""
    return os.path.join(path1, path2)


# ============================================================================
# Model Definition
# ============================================================================

class Net(pl.LightningModule):
    """PyTorch Lightning wrapper for SwinUNETR model."""
    
    def __init__(self, config_dict: Dict):
        super().__init__()
        self.roi_size = config_dict["roi_size"]
        self.num_class = config_dict["num_class"]

        self._model = SwinUNETR(
            img_size=self.roi_size,
            in_channels=2,
            out_channels=1,
            num_heads=(3, 6, 12, 24),
            feature_size=12,
        )
        
        self.post_pred = torch.sigmoid
        self.post_label = AsDiscrete(to_onehot=None, threshold=0.5)

    def forward(self, x):
        return self._model(x)

    def predict_step(self, batch, batch_idx):
        roi_size = self.roi_size
        sw_batch_size = 10
        outputs = sliding_window_inference(
            batch["image"], roi_size, sw_batch_size, self.forward, overlap=0.5
        )
        outputs = self.post_pred(outputs)
        return outputs


# ============================================================================
# Ensemble Inference Function
# ============================================================================

def run_ensemble_inference(flair_path: str, mprage_path: str, output_path: str, models_path: str):
    """Run ensemble inference and save NPZ files.
    
    Args:
        flair_path (str): Path to FLAIR brain image.
        mprage_path (str): Path to MPRAGE brain image.
        output_path (str): Output directory path.
        models_path (str): Path to trained models directory.
    """
    
    # Setup
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    accelerator = "gpu"
    device = 1
    torch.backends.cudnn.benchmark = True
    
    # Setup paths
    flair_path = Path(flair_path)
    mprage_path = Path(mprage_path)
    output_pred_dir = Path(output_path)
    models_path = Path(models_path)
    
    post_thr = 4  # More than 3 voxels
    
    # Find model checkpoints
    ckpt_files = list(models_path.glob("*.ckpt"))
    
    if len(ckpt_files) == 0:
        raise ValueError(f"No .ckpt files found in {models_path}")
    
    # Prepare data
    val_files = [
        {
            "flair": flair_path.as_posix(),
            "mprage": mprage_path.as_posix(),
        }
    ]
    
    # Model configuration
    config_dict = {
        "roi_size": [64, 64, 64],
        "num_class": 2
    }
    
    # Define preprocessing transforms
    val_transforms = Compose([
        LoadImaged(keys=["flair", "mprage"], dtype=np.float32),
        EnsureNDd(keys=["flair", "mprage"], ndim=4),
        Spacingd(
            keys=["flair", "mprage"],
            pixdim=(1.0, 1.0, 1.0),
            mode=("bilinear", "bilinear"),
            align_corners=True,
            dtype=np.float32
        ),
        CropForegroundChanged(keys=["flair", "mprage"], source_key="flair", allow_smaller=False),
        NormalizeIntensityd(keys=["flair", "mprage"], nonzero=True),
        ConcatItemsd(keys=["flair", "mprage"], name="image", dim=0),
        SelectItemsd(keys=["image"]),
    ])
    
    # Create dataset and dataloader
    val_ds = CacheDataset(
        data=val_files, transform=val_transforms, num_workers=None, cache_num=0
    )
    val_loader = DataLoader(val_ds, batch_size=1, num_workers=1, pin_memory=False)
    
    # Define postprocessing transforms
    post_val_transforms = Compose([
        LoadImaged(keys=["flair"], dtype=np.float32),
        EnsureNDd(keys=["flair"], ndim=4),
        Spacingd(
            keys=["flair"],
            pixdim=(1.0, 1.0, 1.0),
            mode=("bilinear"),
            align_corners=True,
            dtype=np.float32
        ),
        CropForegroundChanged(keys=["flair"], source_key="flair", allow_smaller=False),
    ])
    
    # Run ensemble inference
    ensemble_list = []
    
    for i, ckpt_file in enumerate(ckpt_files):
        logger.info(f"Processing model {i+1}/{len(ckpt_files)}: {ckpt_file.name}")
        
        # Load model
        net = Net(config_dict)
        ckpt = torch.load(ckpt_file, weights_only=True)
        net.load_state_dict(ckpt["state_dict"])
        
        # Create trainer
        trainer = pl.Trainer(
            devices=device,
            accelerator=accelerator,
            fast_dev_run=False,
            enable_model_summary=False,
            logger=False,
            enable_progress_bar=False
        )
        
        # Run prediction
        prediction_outputs = trainer.predict(model=net, dataloaders=val_loader)
        
        # Postprocess prediction
        subj_file_dict = val_files[0]
        transformed_data = post_val_transforms(subj_file_dict)
        label_path = Path(subj_file_dict["flair"])
        label_proxy = nib.load(label_path)
        
        prediction_prob = prediction_outputs[0].clone().detach().cpu().squeeze(0)
        if prediction_prob.affine.ndim == 3:
            prediction_prob.affine = prediction_prob.affine[0, ...]
        
        prediction_prob.applied_operations = transformed_data["flair"].applied_operations
        predict_dict = {"flair": prediction_prob}
        
        with allow_missing_keys_mode(post_val_transforms):
            inverted_pred_dict = post_val_transforms.inverse(predict_dict)
        
        prediction_prob = inverted_pred_dict["flair"].squeeze(0).numpy()
        
        # Binarize and post-process
        prediction_label = (prediction_prob >= 0.5).astype(np.uint8)
        label_map, unique_label, count_label = form_cluster(prediction_label)
        
        # Remove small lesions
        for the_small_label in unique_label[count_label < post_thr]:
            prediction_label[label_map == the_small_label] = 0
        
        # Add to ensemble
        ensemble_list.append(prediction_prob)
    
    # Stack ensemble predictions
    ens_prediction_prob = np.stack(ensemble_list, axis=0)
    logger.info(f"Ensemble prediction shape: {ens_prediction_prob.shape}")
    
    # Load original data for saving
    orig_flair_header = nib.load(flair_path)
    orig_flair_affine = orig_flair_header.affine
    orig_flair = orig_flair_header.get_fdata()
    brain_mask = (orig_flair != 0).astype(np.uint8)
    
    
    # Prepare data to save (space-efficient format)
    to_save = {
        'shape': prediction_label.shape,  # [H, W, D]
        'output_shape': ens_prediction_prob.shape,  # [N, H, W, D]
        'brain_location': np.where(brain_mask == 1),
        'affine': orig_flair_affine,
        'pred_probs': ens_prediction_prob[np.broadcast_to(brain_mask, ens_prediction_prob.shape) == 1]
    }
    
    # Create output directory
    if not os.path.exists(output_pred_dir):
        os.makedirs(output_pred_dir, exist_ok=True)
    
    # Generate filename
    new_filename = 'pred.npz'
    output_filepath = os.path.join(output_pred_dir, new_filename)
    
    # Save NPZ file
    if not os.path.exists(output_filepath):
        np.savez_compressed(output_filepath, **to_save)
    else:
        logger.info(f"File already exists: {output_filepath}")
    
    logger.info("Ensemble inference completed successfully!")
    
    return output_filepath
