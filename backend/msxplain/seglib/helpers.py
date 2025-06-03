import logging
from pathlib import Path

import SimpleITK as sitk
import numpy as np
import pandas as pd
import tempfile
import shutil
from dcmrtstruct2nii import dcmrtstruct2nii


class DcmRtstruct2NiiWrapper():

    def __init__(self, p_rtstruct, p_dicom_img, p_tmp=None):
        self.p_rtstruct  = p_rtstruct
        self.p_dicom_img = p_dicom_img
        self.roi_dict = {}
        if p_tmp is None:
            p_tmp = tempfile.mkdtemp()
        self.p_tmp = Path(p_tmp)
        self.p_tmp.mkdir(exist_ok=True, parents=True)

    def convert(self):
        dcmrtstruct2nii(self.p_rtstruct, self.p_dicom_img, self.p_tmp)
        p_nii_ref = self.p_tmp.joinpath('image.nii.gz')
        # Scan available labels
        roi_id_counter = 0
        for p in self.p_tmp.glob('*.nii.gz'):
            if not p.name.startswith('image'):
                roi_id_counter += 1
                p_mask_name_split = p.name.split('_')
                roi_name = "_".join(p_mask_name_split[1:])
                roi_name = roi_name[:roi_name.find('.nii')] # only keep part before .nii as name
                self.roi_dict[roi_id_counter] = (roi_name, p)

    def get_roi_ids(self):
        return list(self.roi_dict.keys())

    def get_roi_mask_by_id(self, roi_id):
        if roi_id in self.roi_dict.keys():
            roi_name, p = self.roi_dict[roi_id]
            roi_mask_sitk = sitk.ReadImage(p.as_posix())
            roi_mask_nii = sitk.GetArrayFromImage(roi_mask_sitk)
            roi_mask_bool = (roi_mask_nii == roi_id)
            return roi_mask_bool
        else:
            logging.warning(f"ROI id {roi_id} does not exist")
    def get_roi_mask_sitk_by_id(self, roi_id):
        if roi_id in self.roi_dict.keys():
            roi_name, p = self.roi_dict[roi_id]
            roi_mask_sitk = sitk.ReadImage(p.as_posix())
            return roi_mask_sitk
        else:
            logging.warning(f"ROI id {roi_id} does not exist")
    def get_roi_name_by_id(self, roi_id):
        if roi_id in self.roi_dict.keys():
            roi_name, p = self.roi_dict[roi_id]
            return roi_name
        else:
            logging.warning(f"ROI id {roi_id} does not exist")

    def remove_tmp(self):
        shutil.rmtree(self.p_tmp)



def get_segment(roi_id: int, label: str, description: str, color):
    return {
        # Make sure we are using a simple int (not a NumPy type)
        "labelID": int(roi_id),
        "SegmentDescription": description,
        "SegmentLabel": label,
        "SegmentAlgorithmType": "AUTOMATIC",
        "SegmentAlgorithmName": "Automatic",
        # Snomed Coding for Tissue
        "SegmentedPropertyCategoryCodeSequence": {
            "CodeValue": "85756007",
            "CodingSchemeDesignator": "SCT",
            "CodeMeaning": "Tissue",
        },
        # Snomed Coding for Organ
        "SegmentedPropertyTypeCodeSequence": {
            "CodeValue": "113343008",
            "CodingSchemeDesignator": "SCT",
            "CodeMeaning": "Organ",
        },
        # Color to display
        "recommendedDisplayRGBValue": color,
    }


def match_orientation(sitk_img_ref: sitk.Image, sitk_img_sec: sitk.Image, verbose=True):
    orientation_filter = sitk.DICOMOrientImageFilter()
    direction_ref = sitk_img_ref.GetDirection()
    orientation_ref = orientation_filter.GetOrientationFromDirectionCosines(direction_ref)
    direction_sec = sitk_img_sec.GetDirection()
    orientation_sec = orientation_filter.GetOrientationFromDirectionCosines(direction_sec)
    if verbose:
        logging.info(f"Reference image has direction '{direction_ref}', orientation '{orientation_ref}'")
        logging.info(f"Second image has direction '{direction_sec}', orientation '{orientation_sec}'")
    if orientation_ref != orientation_sec:
        if verbose:
            logging.info(f"Converting orientation of second image: '{orientation_sec}' --> '{orientation_ref}'")
        orientation_filter.SetDesiredCoordinateOrientation(orientation_ref)
        img_sec_reoriented = orientation_filter.Execute(sitk_img_sec)
        orientation_sec_reoriented = orientation_filter.GetOrientationFromDirectionCosines(img_sec_reoriented.GetDirection())
        return img_sec_reoriented
    else:
        return sitk_img_sec


def intersection_bin_mask(mask1: np.ndarray, mask2:np.ndarray, rel_to=1):
    intersection = np.logical_and(mask1, mask2)
    n_intersection = intersection.sum()
    if rel_to==1:
        n_ref = mask1.sum()
    elif rel_to==2:
        n_ref = mask2.sum()
    else:
        logging.warning(f"'rel_to' can take values '1' or '2', not {rel_to}. Using '1' as reference")
        n_ref = mask1.sum()
    rel_intersection = n_intersection/n_ref
    result = {'n_intersection' : n_intersection,
              'n_ref' : n_ref,
              'rel_intersection' : rel_intersection,
              'rel_to' : rel_to}
    return result


def get_boolean_masks_from_seg(seg_sitk: sitk.Image, roi_ids=None, background=0):
    seg_nii = sitk.GetArrayFromImage(seg_sitk)
    roi_ids_in_img = np.unique(seg_nii).tolist()
    roi_ids_in_img.remove(background)
    logging.debug(f"Segmentation image contains {len(roi_ids_in_img)} labels")
    seg_meta = get_metadata_from_seg(seg_sitk)
    if roi_ids is None:
        roi_ids = roi_ids_in_img
    bool_masks = {}
    for roi_id in roi_ids:
            bool_masks[roi_id] = (seg_nii==roi_id)
    result = {'meta_data': seg_meta, 'binary_masks': bool_masks}
    return result


def get_metadata_from_seg(seg_sitk: sitk.Image):
    seg_meta = {}
    dim_x = seg_sitk.GetDepth()
    dim_y = seg_sitk.GetHeight()
    dim_z = seg_sitk.GetWidth()
    seg_meta['origin'] = seg_sitk.GetOrigin()
    seg_meta['spacing'] = seg_sitk.GetSpacing()
    seg_meta['direction'] = seg_sitk.GetDirection()
    seg_meta['shape'] = tuple((dim_x, dim_y, dim_z))
    return seg_meta


def read_image_files(path: Path):
    if path.is_dir():
        reader = sitk.ImageSeriesReader()
        dicom_names = reader.GetGDCMSeriesFileNames(path.as_posix())
        reader.SetFileNames(dicom_names)
        image = reader.Execute()
    else:
        image = sitk.ReadImage(path.as_posix())
    return image

def capfirst(s):
    return s[:1].upper() + s[1:]

def make_string_BIDS_value_compliant(s: str):
    split_1 = s.split('-')
    split_2 = [s.split('_') for s in split_1]
    flat_list = [num for sublist in split_2 for num in sublist]
    flat_list_cap = [capfirst(s.strip()) for s in flat_list]
    return "".join(flat_list_cap)


def match_size(sitk_img_ref, sitk_img_sec, interpolator=sitk.sitkNearestNeighbor):
    size_ref = sitk_img_ref.GetSize()
    size_sec = sitk_img_sec.GetSize()
    logging.debug(f"Reference image has size '{size_ref}'")
    logging.debug(f"Second image has size    '{size_sec}'")
    if not np.all(size_ref == size_sec):
        logging.debug(f"Resampling second image: '{size_sec}' --> '{size_ref}'")
        resample = sitk.ResampleImageFilter()
        resample.SetReferenceImage(sitk_img_ref)
        resample.SetInterpolator(interpolator)
        sitk_img_sec_resampled = resample.Execute(sitk_img_sec)
        return sitk_img_sec_resampled
    else:
        return sitk_img_sec

def resample_by_spacing(img_in, new_spacing=[1., 1., 1.], interpolator=sitk.sitkLinear):
    resample = sitk.ResampleImageFilter()
    resample.SetInterpolator(interpolator)
    resample.SetOutputDirection(img_in.GetDirection())
    resample.SetOutputOrigin(img_in.GetOrigin())
    resample.SetOutputSpacing(new_spacing)
    orig_size = np.array(img_in.GetSize(), dtype=np.int32)
    orig_spacing = img_in.GetSpacing()
    new_size = orig_size * (np.array(orig_spacing) / np.array(new_spacing))
    new_size = np.ceil(new_size).astype(int)  # Image dimensions are in integers
    new_size = [int(s) for s in new_size]
    resample.SetSize(new_size)
    img_res = resample.Execute(img_in)
    return img_res


def compute_intersection(seg_1, seg_2):
    seg_intersection = seg_1 * seg_2
    lsf_intersection = sitk.LabelShapeStatisticsImageFilter()
    lsf_intersection.Execute(seg_intersection)
    if 1 in lsf_intersection.GetLabels():
        n_vox_intersection = lsf_intersection.GetNumberOfPixels(1)
    else:
        n_vox_intersection = 0
    return n_vox_intersection

def compute_overlap(seg_1, seg_2):
    overlap_measures_filter = sitk.LabelOverlapMeasuresImageFilter()
    overlap_measures_filter.Execute(seg_1, seg_2)
    jaccard = overlap_measures_filter.GetJaccardCoefficient()
    dice = overlap_measures_filter.GetDiceCoefficient()
    res = {'jaccard_index' : jaccard,
           'dice_index' : dice
           }
    return res

def compare(image_1, image_2, rel_to=2, mode='same-id'):
    if mode in ['same-id', 'all-vs-all']:

        lsf_1 = sitk.LabelShapeStatisticsImageFilter()
        lsf_1.Execute(image_1)
        lsf_2 = sitk.LabelShapeStatisticsImageFilter()
        lsf_2.Execute(image_2)
        df = pd.DataFrame()
        i = 0
        logging.debug(f"ROIs in image 1: '{lsf_1.GetLabels()}'")
        logging.debug(f"ROIs in image 2: '{lsf_2.GetLabels()}'")

        # create label pairs in function of 'mode'
        label_pairs_list = []
        for label_id_1 in lsf_1.GetLabels():
            for label_id_2 in lsf_2.GetLabels():
                if (mode == 'same-id') & (label_id_1 == label_id_2):
                    label_pairs_list.append((label_id_1, label_id_2))
                elif (mode == 'all-vs-all'):
                    label_pairs_list.append((label_id_1, label_id_2))

        # for each pair, compute stats
        results_list = []
        for label_id_1, label_id_2 in label_pairs_list:
            n_vox_1 = lsf_1.GetNumberOfPixels(label_id_1)
            seg_1 = (image_1 == label_id_1)
            n_vox_2 = lsf_2.GetNumberOfPixels(label_id_2)
            seg_2 = (image_2 == label_id_2)
            logging.debug(f"Image 1 - ROI-{label_id_1}: {n_vox_1} || Image 2 - ROI-{label_id_2}: {n_vox_2}")

            results = {'img_1_roi': label_id_1,
                       'img_2_roi': label_id_2,
                       'n_vox_roi_1': n_vox_1,
                       'n_vox_roi_2': n_vox_2}

            # -- intersection
            n_vox_intersection = compute_intersection(seg_1, seg_2)
            res_intersection = {'n_vox_intersection': n_vox_intersection
                                }
            results.update(res_intersection)

            # -- DICE / Jaccard
            res_overlap = compute_overlap(seg_1, seg_2)
            results.update(res_overlap)

            results_list.append(pd.Series(results))
        df = pd.concat(results_list, axis=1).T

        if len(df) > 0:
            if rel_to == 2:
                ref_col = df['n_vox_roi_2']
            elif rel_to == 1:
                ref_col = df['n_vox_roi_1']
            else:
                logging.warning(f"'rel_to' can take values '1' or '2', not {rel_to}. Using '1' as reference")
                ref_col = df['n_vox_roi_1']
            df.loc[:, 'rel_intersection'] = df['n_vox_intersection'] / ref_col
            for col_name in ['img_1_roi', 'img_2_roi', 'n_vox_roi_1', 'n_vox_roi_2', 'n_vox_intersection']:
                df.loc[:, col_name] = df[col_name].astype(int)
        else:
            logging.info("Not found any ROIs to intersect")
            df = None
    else:
        logging.fatal(f"Mode '{mode}' not defined")
        df = None

    return df
