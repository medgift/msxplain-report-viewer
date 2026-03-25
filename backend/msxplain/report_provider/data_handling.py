"""
Data handling utilities for ensemble predictions and NPZ dataset loading.

This module provides classes for:
- Saving ensemble predictions to NPZ format
- Loading and processing NPZ prediction files
"""

import logging
import os
import numpy as np
from pathlib import Path


logger = logging.getLogger(__name__)


class NpzDataset:
    """Dataset class for loading ensemble predictions from NPZ files.
    
    NPZ files are expected to contain:
    - shape: Original volume shape [H, W, D]
    - output_shape: Ensemble predictions shape [N, H, W, D]
    - brain_location: Indices where brain_mask == 1
    - affine: Affine transformation matrix
    - pred_probs or pred_logits: Predictions within brain mask
    """
    
    def __init__(self, pred_path: str, pred_prefix: str = 'pred.npz'):
        """Initialize NPZ dataset.
        
        Args:
            pred_path (str): Path to directory containing NPZ files
            pred_prefix (str, optional): Suffix for NPZ files. Defaults to 'pred.npz'.
        """
        self.pred_filepaths: list = sorted(list(Path(pred_path).glob(f"*{pred_prefix}")))

    def __len__(self):
        return len(self.pred_filepaths)

    def __getitem__(self, idx):
        """Load and return data from NPZ file.
        
        Args:
            idx (int): Index of the file to load
            
        Returns:
            dict: Dictionary containing:
                - shape: Original volume shape
                - affine: Affine transformation matrix
                - filename: Basename of the NPZ file
                - brain_mask: Binary brain mask [H, W, D]
                - pred_probs or pred_logits: Ensemble predictions [N, H, W, D]
        """
        data: np.lib.npyio.NpzFile = np.load(self.pred_filepaths[idx])
        data_dict = {
            'shape': data['shape'],
            'affine': data['affine'],
            'filename': os.path.basename(self.pred_filepaths[idx])
        }

        # Parse brain mask
        bm = np.zeros(data['shape'])
        bm[data['brain_location'][0], data['brain_location'][1], data['brain_location'][2]] = 1
        data_dict['brain_mask'] = bm

        # Parse outputs (predictions)
        output_name = 'pred_logits' if 'pred_logits' in data.files else 'pred_probs'
        output = np.zeros(shape=data['output_shape'])
        output[np.broadcast_to(bm, data['output_shape']) == 1] = data[output_name]
        data_dict[output_name] = output

        return data_dict
