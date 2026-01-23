import torch
from monai.data import DataLoader
from monai.inferers import SlidingWindowInferer
from monai.networks.nets import UNet
from monai.networks.nets import UNet
from .datasets import NiftinotargetDataset
from .transforms import get_valnotarget_transforms
from .losses import *
import numpy as np
import nibabel as nib
from pathlib import Path
import logging
import os
import time
import time
import traceback
start_time = time.time()

logger = logging.getLogger(__name__)

def predict_msxplain(input_val_paths, input_prefixes, model_checkpoint, parcellation_dir, num_workers=0, cache_rate=0.1, threshold=0.3, force_cuda=True):
    """Run MSXplain prediction
    
    Args:
        input_val_paths (list): List of paths to input directories
        input_prefixes (list): List of input file prefixes
        model_checkpoint (str): Path to model weights
        parcellation_dir (str): Path to parcellation directory
        num_workers (int): Number of workers for data loading
        cache_rate (float): Cache rate for data loading
        threshold (float): Threshold for binary prediction
        force_cuda (bool): Force CUDA availability
    """
    try:
        start_time = time.time()
        
        # Override CUDA availability if requested
        if force_cuda:
            logger.info("Running MS Lesion Prediction IN CUDA")
            torch.cuda.is_available = lambda : True
        else:
            logger.info("Running MS Lesion Prediction IN CPU")
            torch.cuda.is_available = lambda : False
        
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {device}")
        torch.multiprocessing.set_sharing_strategy('file_system')
        
        # Model parameters
        input_modalities = ['flair', 'mprage']
        n_classes = 2
        seed = 1
        
        # Initialize model
        model = UNet(
            spatial_dims=3,
            in_channels=len(input_modalities),
            out_channels=n_classes,
            channels=(32, 64, 128, 256, 512),
            strides=(2, 2, 2, 2),
            norm='batch',
            num_res_units=0
        ).to(device)
        
        # Initialize weights
        for layer in model.model.modules():
            if isinstance(layer, torch.nn.Conv3d):
                torch.nn.init.xavier_normal_(layer.weight, gain=1.0)
        
        # Load model weights
        logger.info(f"Loading model weights from {model_checkpoint}")
        if torch.cuda.is_available():
            model.load_state_dict(torch.load(model_checkpoint, map_location='cuda'))
        else:
            model.load_state_dict(torch.load(model_checkpoint, map_location='cpu'))
        
        model.eval()
        activation = torch.nn.Softmax(dim=1)
        
        # Setup inference
        inferer = SlidingWindowInferer(
            roi_size=(96, 96, 96),
            sw_batch_size=1,
            mode='gaussian',
            overlap=0.25
        )
        
        # Prepare dataset
        val_transforms = get_valnotarget_transforms(input_keys=input_modalities).set_random_state(seed=seed)
        val_dataset = NiftinotargetDataset(
            input_paths=input_val_paths,
            input_prefixes=input_prefixes,
            input_names=input_modalities,
            transforms=val_transforms,
            num_workers=num_workers,
            cache_rate=cache_rate
        )
        
        val_loader = DataLoader(
            val_dataset,
            shuffle=False,
            batch_size=1,
            num_workers=num_workers
        )
        
        logger.info(f"Initializing the dataset. Number of subjects {len(val_loader)}")
        
        # Process each batch
        for i, data in enumerate(val_loader):
            
            # Use the first input file for affine information
            input_file = os.path.join(input_val_paths[0], input_prefixes[0])
            input_affine = nib.load(input_file).affine
            logger.info(f"Processing input file: {input_file}")
            
            # Move inputs to device
            if torch.cuda.is_available():
                inputs = data["inputs"].cuda()
            else:
                inputs = data["inputs"]
            
            inputs.requires_grad_()
            
            # Run inference
            outputs = inferer(inputs=inputs, network=model)
            outputs = activation(outputs)
            output_mask = outputs[0,1].detach().cpu().numpy()
            output_mask = (output_mask > threshold).astype(np.float32)
            
            # Save prediction
            pred = nib.Nifti1Image(output_mask, input_affine)
            pred_path = os.path.join(str(parcellation_dir), "pred.nii.gz")
            nib.save(pred, pred_path)
            logger.info(f"Prediction saved to {pred_path}")
        
        return str(pred_path)
        
    except Exception as e:
        logger.error(f"Error in prediction: {str(e)}")
        traceback.print_exc()
        raise

# Keep the original script functionality for command line usage
if __name__ == "__main__":
    print("This script should now be imported as a module and used via the predict_msxplain function")
