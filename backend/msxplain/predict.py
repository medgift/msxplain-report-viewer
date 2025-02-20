################
#written by Federico Spagnolo
#usage: python predict.py --model_checkpoint model_epoch_31.pth --input_val_paths batch_data batch_data --input_prefixes flair_3d_sbr.nii.gz t1n_3d_sb.nii.gz --num_workers 0 --cache_rate 0.01 --threshold 0.3
################
# Import torch
import torch
import torchvision
#import packages for model description
from torchvision import models
import scipy.ndimage as ndimage
from monai.data import DataLoader
from monai.inferers import SlidingWindowInferer
from monai.networks.nets import UNet
from monai.transforms import (Activations, AddChanneld, Compose, ConcatItemsd,
                              LoadImaged, NormalizeIntensityd, RandAffined,
                              RandCropByPosNegLabeld, RandFlipd, RandRotate90d,
                              RandShiftIntensityd, RandSpatialCropd, Spacingd, SelectItemsd,
                              ToTensord)
from monai.networks.nets import UNet
from monai.visualize import GradCAMpp
from msxplain.datasets import NiftinotargetDataset
from msxplain.transforms import remove_connected_components, get_valnotarget_transforms, binarize_mask
from msxplain.losses import *
from msxplain.lesion_extraction import get_lesion_types_masks
import numpy as np
import nibabel as nib
from pathlib import Path
import argparse
import logging
import os
import sys
import matplotlib.pyplot as plt
import numpy.ma as ma
from tqdm import tqdm
import pandas as pd
import gc
import time
import psutil
import time
import traceback
start_time = time.time()


def dp(path1: str, path2: str) -> str:
    return os.path.join(path1, path2)

def form_cluster(data_array:np.array, struct:np.array=np.ones([3, 3, 3])):
    """Get individual clusters

    Args:
        data_array (numpy array): The image, where to find clusters
        struct (numpy array or scipy struct array, optional): The connectivity. Defaults to np.ones([3, 3, 3]) for all-direction connectivity.

    Returns:
        label_map [numpy array]: The image having labeled clusters.
        unique_label [numpy array]: The array containing unique cluster indices.
        label_counts [numpy array]: The correpsonding voxel numbers.
    """
    label_map, _ = ndimage.label(data_array, structure=struct)
    unique_label, label_counts = np.unique(label_map, return_counts=True)
    return label_map, unique_label[1:], label_counts[1:]    
    
# # current folder
# script_folder = os.path.dirname(os.path.realpath(__file__))
# # set output folder
# output_dir = "SAMSEG"

# parser = argparse.ArgumentParser(
# description='''Saliency map generation.
#                         If no arguments are given, all the default values will be used.''', add_help=True, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
# parser.add_argument('--data', metavar='-d', dest='data_path', default=script_folder, help="Path where the data is")
# parser.add_argument('--model_checkpoint', metavar='-ckpt', dest='model_checkpoint', default="model_epoch_1.pth", help="Path to he best checkpoint of the model")
# parser.add_argument('--input_val_paths', type=str, nargs='+', required=True)
# parser.add_argument('--input_prefixes', type=str, nargs='+', required=True)
# # data handling
# parser.add_argument('--num_workers', type=int, default=0,
#                         help='number of jobs used to load the data, DataLoader parameter')
# parser.add_argument('--cache_rate', type=float, default=0.1, help='cache dataset parameter')
# parser.add_argument('--threshold', type=float, default=0.5, help='lesion threshold')
# args = parser.parse_args()        

# data_path = args.data_path
# model_checkpoint = args.model_checkpoint
# args.input_modalities = ['flair', 'mprage']
# args.n_classes = 2
# seed = 1

# ''' Get default device '''
# logging.basicConfig(level = logging.INFO)
# print("total devices", torch.cuda.device_count())
# device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
# logging.info(f"Using device: {device}")
# torch.multiprocessing.set_sharing_strategy('file_system')

# # Init your model
# if torch.cuda.is_available():
#     print("======= IN CUDA ======")
#     model = UNet(spatial_dims=3, in_channels=len(args.input_modalities), out_channels=args.n_classes,
#                         channels=(32, 64, 128, 256, 512), strides=(2, 2, 2, 2), norm='batch', num_res_units=0).cuda()
# else:
#     print("======= IN CPU ======")
#     model = UNet(spatial_dims=3, in_channels=len(args.input_modalities), out_channels=args.n_classes,
#                      channels=(32, 64, 128, 256, 512), strides=(2, 2, 2, 2), norm='batch', num_res_units=0)
    
# # Weights intialization
# for layer in model.model.modules():
#         if type(layer) == torch.nn.Conv3d:
#                 torch.nn.init.xavier_normal_(layer.weight, gain=1.0)

# # Load best model weights
# model_path = dp(script_folder, model_checkpoint)
# #print(model_path)
# if torch.cuda.is_available():
#     print("======= IN CUDA======")
#     model = torch.nn.DataParallel(model).cuda()
#     model.load_state_dict(torch.load(args.model_checkpoint, map_location='cuda'))
# else:
#     print("======= IN CPU ======")
#     model = torch.nn.DataParallel(model)
#     model.load_state_dict(torch.load(args.model_checkpoint, map_location='cpu'))

# model.eval()
# activation = torch.nn.Softmax(dim=1)

# ''' Define validation actors '''
# inferer = SlidingWindowInferer(roi_size=(96, 96, 96),
#                                    sw_batch_size=1, mode='gaussian', overlap=0.25)

# logging.info(f"Best model save file loaded from: {model_path}")

# # Load Dataset
# val_transforms = get_valnotarget_transforms(input_keys=args.input_modalities).set_random_state(seed=seed)
# val_dataset = NiftinotargetDataset(input_paths=args.input_val_paths, input_prefixes=args.input_prefixes,
#                                    input_names=args.input_modalities, 
#                                    transforms=val_transforms, num_workers=args.num_workers,
#                                    cache_rate=args.cache_rate)                                   
                                   
# val_dataloader = DataLoader(val_dataset, shuffle=False, batch_size=1, num_workers=args.num_workers)

# loss_function = NormalisedDiceFocalLoss(include_background=False, to_onehot_y=True, other_act=activation,
#                                                 lambda_ndscl=0.5, lambda_focal=1.0)

# i = 0
# threshold = args.threshold

# logging.info(f"Initializing the dataset. Number of subjects {len(val_dataloader)}")

# # Batch Loading

# for data in val_dataloader:

#     filename = data['flair_meta_dict']['filename_or_obj'][0]
#     logging.info(f"Evaluate gradients in batch {filename}")
    
#     if torch.cuda.is_available():
#         print("======= IN CUDA ======")
#         inputs = data["inputs"].cuda() # 0 is flair, 1 is mprage
#     else:
#         print("======= IN CPU ======")
#         inputs = data["inputs"] # 0 is flair, 1 is mprage
    
#     input_affine = nib.load(filename).affine

#     inputs.requires_grad_()
     
#     #outputs = model(inputs)
#     outputs = inferer(inputs=inputs, network=model)  # [1, 2, H, W, D]
#     outputs = activation(outputs)  # [1, 2, H, W, D]
#     output_mask = outputs[0,1].detach().cpu().numpy()
#     output_mask[output_mask > threshold] = 1
#     output_mask[output_mask < threshold] = 0
    
#     # Save predicted output
#     pred = nib.Nifti1Image(output_mask, input_affine)
#     outputpath = Path(args.input_val_paths[0])
    
#     Path.mkdir(outputpath / output_dir, parents=True, exist_ok=True)
    
#     nib.save(pred, outputpath / output_dir / "pred.nii.gz")
#     i+=1
 

# end_time = time.time()
# elapsed_time = end_time - start_time

# # Convert elapsed time to hours, minutes, and seconds
# hours, remainder = divmod(elapsed_time, 3600)
# minutes, seconds = divmod(remainder, 60)   
# print(f"======= Elapsed time: {int(hours)} hours, {int(minutes)} minutes, {seconds:.2f} seconds")

# def get_transforms(input_keys):
#     """Get transforms for data preprocessing"""
#     return Compose([
#         LoadImaged(keys=input_keys),
#         AddChanneld(keys=input_keys),
#         NormalizeIntensityd(keys=input_keys),
#         ConcatItemsd(keys=input_keys, name="inputs"),
#         SelectItemsd(keys=["inputs"]),
#         ToTensord(keys=["inputs"])
#     ])

# def get_valnotarget_transforms(input_keys, seed=1):
#     """Get validation transforms for data without target masks"""
#     transforms = Compose([
#         LoadImaged(keys=input_keys),
#         AddChanneld(keys=input_keys),
#         NormalizeIntensityd(keys=input_keys),
#         ConcatItemsd(keys=input_keys, name="inputs"),
#         SelectItemsd(keys=["inputs"]),
#         ToTensord(keys=["inputs"])
#     ])
#     transforms.set_random_state(seed=seed)
#     return transforms

def predict_msxplain(input_val_paths, input_prefixes, model_checkpoint, num_workers=0, cache_rate=0.1, threshold=0.3, force_cuda=True):
    """Run MSXplain prediction
    
    Args:
        input_val_paths (list): List of paths to input directories
        input_prefixes (list): List of input file prefixes
        model_checkpoint (str): Path to model weights
        num_workers (int): Number of workers for data loading
        cache_rate (float): Cache rate for data loading
        threshold (float): Threshold for binary prediction
        force_cuda (bool): Force CUDA availability
    """
    try:
        start_time = time.time()
        
        # Override CUDA availability if requested
        if force_cuda:
            print("======= IN CUDA ======")
            torch.cuda.is_available = lambda : True
        else:
            print("======= IN CPU ======")
            torch.cuda.is_available = lambda : False
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        print("total devices", torch.cuda.device_count())
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logging.info(f"Using device: {device}")
        torch.multiprocessing.set_sharing_strategy('file_system')
        
        # Model parameters
        input_modalities = ['flair', 'mprage']
        n_classes = 2
        seed = 1
        
        # Initialize model
        print("Initializing model...")
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
        print(f"Loading model weights from {model_checkpoint}")
        if torch.cuda.is_available():
            model = torch.nn.DataParallel(model)
            model.load_state_dict(torch.load(model_checkpoint, map_location='cuda'))
        else:
            model = torch.nn.DataParallel(model)
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
        print("Preparing dataset...")
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
        
        logging.info(f"Initializing the dataset. Number of subjects {len(val_loader)}")
        
        # Process each batch
        for i, data in enumerate(val_loader):
            print("Available keys in data:", data.keys())  # Debug print
            
            # Use the first input file for affine information
            input_file = os.path.join(input_val_paths[0], input_prefixes[0])
            input_affine = nib.load(input_file).affine
            logging.info(f"Processing input file: {input_file}")
            
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
            output_path = Path(input_val_paths[0])
            samseg_dir = output_path / "SAMSEG"
            samseg_dir.mkdir(parents=True, exist_ok=True)
            
            pred_path = samseg_dir / "pred.nii.gz"
            nib.save(pred, pred_path)
            print(f"Prediction saved to {pred_path}")
        
        # Report timing
        end_time = time.time()
        elapsed_time = end_time - start_time
        hours, remainder = divmod(elapsed_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        print(f"======= Elapsed time: {int(hours)} hours, {int(minutes)} minutes, {seconds:.2f} seconds")
        
        return str(pred_path)
        
    except Exception as e:
        print(f"Error in prediction: {str(e)}")
        traceback.print_exc()
        raise

# Keep the original script functionality for command line usage
if __name__ == "__main__":
    print("This script should now be imported as a module and used via the predict_msxplain function")
