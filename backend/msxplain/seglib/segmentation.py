from pathlib import Path
import logging
import SimpleITK as sitk
import numpy as np
import re
import pandas as pd
import itertools
from pydicom import dcmread
import pydicom_seg
import pydicom
from .helpers import get_segment, intersection_bin_mask, get_boolean_masks_from_seg, get_metadata_from_seg, \
    read_image_files, match_size, DcmRtstruct2NiiWrapper
from .labels import Labels

logger = logging.getLogger(__name__)



def get_union(bool_array_list):
    return np.logical_or.reduce(bool_array_list)

def get_intersection(bool_array_list):
    return np.logical_and.reduce(bool_array_list)

def get_difference(ref_arrays, arrays_to_remove):
        reference_union = get_union(ref_arrays)
        union_to_remove = get_union(arrays_to_remove)
        result_diff_int = reference_union.astype(int) - union_to_remove.astype(int)
        result_diff_bool = (result_diff_int>0)
        return result_diff_bool


class Segmentation():
    def __init__(self, p_seg: Path, p_labels=None, mask_glob='*desc-*', from_ref_img=False, p_dcm_ref=None,
                 regex='desc-\w+', warn_only=False, precision=5, rtstruct_converter='rt_utils', force_inconsistent_masks=False, p_seg_ref=None):
        if not isinstance(p_seg, Path):
            p_seg = Path(p_seg)
        # init labels
        self.labels = Labels(p=p_labels)
        # init masks/seg
        self.meta_data = {}
        self.binary_masks = {}
        self.precision = precision
        if p_seg.is_file() and not from_ref_img:
            file_ext_dcm = ".".join(p_seg.name.split('.')[-1:])
            file_ext_nii = ".".join(p_seg.name.split('.')[-2:])
            if (file_ext_dcm == 'dcm'):
                dcm_mod = self._get_val_from_dcm_header(p_seg, 'Modality')
                if (dcm_mod == 'RTSTRUCT') and (p_dcm_ref is not None):
                    self.init_type = 'from_dcm_RTSTRUCT'
                    if rtstruct_converter=='rt_utils':
                        self._init_dcm_rtstruct(p_seg, p_dcm_ref, warn_only=warn_only)
                    elif rtstruct_converter=='dcmrtstruct2nii':
                        self._init_dcm_rtstruct_2(p_seg, p_dcm_ref)
                else:
                    self.init_type = 'from_dcm_SEG'
                    self._init_dcm_seg(p_seg)
            else:
                self.init_type = 'from_bin_seg_file'
                self._init_bin_seg_file(p_seg)
        elif (p_seg.is_file() or p_seg.is_dir()) and from_ref_img:
            self.init_type = 'from_reference_image'
            self._init_ref_image(p_seg)
        elif p_seg.is_dir() and not from_ref_img:
            self.init_type = 'from_folder'
            self._init_mask_folder(p_seg, mask_glob, regex, force_inconsistent_masks=force_inconsistent_masks, p_seg_ref=p_seg_ref)
        else:
            logger.warning(f"Unexpected input '{p_seg}'; expect path to segmentation files or folder")
        # align labels / seg
        self._align_labels_with_seg()



    @staticmethod
    def _get_val_from_dcm_header(p, field_name):
        ds = dcmread(p.as_posix())
        if field_name in ds:
            val = ds[field_name].value
            return val
        else:
            logger.fatal(f"Field '{field_name}' not present in DCM header '{p}'")

    def _align_labels_with_seg(self):
        rois_in_seg     = self.get_roi_ids()
        rois_in_labels  = self.labels.get_roi_ids()
        rois_in_seg_not_labels = [roi for roi in rois_in_seg if not roi in rois_in_labels]
        rois_in_labels_not_seg = [roi for roi in rois_in_labels if not roi in rois_in_seg]
        if len(rois_in_seg_not_labels)>0:
            logger.warning(f"ROIs {rois_in_seg_not_labels} are not present in label file. Will assign 'ROI-<ID>' as name")
            for roi in rois_in_seg_not_labels:
                name = f"roi-{roi}"
                self.labels.add_roi(name=name, roi_id=roi, abbreviation=name)
        if len(rois_in_labels_not_seg)>0:
            logger.warning(f"ROIs {rois_in_labels_not_seg} in label file are not present in segmentations. Will remove from labels")
            for roi in rois_in_labels_not_seg:
                self.labels.remove_roi_id(roi)

    def set_target_orientation_from_file(self, p: Path, use_p_dcm_ref=True):
        orientation = None

        if (p is None) and use_p_dcm_ref and hasattr(self, 'p_dcm_ref'):
            p = self.p_dcm_ref
            logger.debug(f"Using 'p_dcm_ref' {p} as reference file for output orientation")

        if p is not None:
            p = Path(p)
            if p.exists():
                sitk_img = read_image_files(p)
                self.set_target_orientation(sitk_img.GetDirection())
            else:
                logger.warning(f"Reference file {p} does not exist")
        logger.debug(f"No reference file for target orientation")
        return orientation

    def set_target_orientation(self, direction):
        if  direction is not None:
            orientation_filter = sitk.DICOMOrientImageFilter()
            target_orientation = orientation_filter.GetOrientationFromDirectionCosines(direction)
            logger.info(f"Setting target orientation to '{target_orientation}'")
            self.target_orientation = target_orientation

    def _has_labels(self):
        return hasattr(self, 'labels')

    def get_roi_ids(self):
        roi_ids = list(self.binary_masks.keys())
        roi_ids.sort()
        return roi_ids

    def get_n_roi_ids(self):
        return len(self.get_roi_ids())

    def get_max_roi_id(self):
        if len(self.get_roi_ids()) == 0:
            max_id = None
        else:
            max_id = max(self.get_roi_ids())
        return max_id

    def _init_dcm_seg(self, p_dcm_seg):
        """
        Uses pydicom-seg [https://github.com/razorx89/pydicom-seg] to read DCM-SEG file and initialize segmentation.
        The function uses the pydicom-seg SegmentReader (instead of MultiClassReader) to extract individual binary masks
        and metadata. It should thus be compatible with DCM-SEG files that contain overlapping masks, however, this has
        not been tested!
        :param p_dcm_seg: path to DCM-SEG file
        :return: None
        """
        logger.info(f"Initialization from DCM SEG file: {p_dcm_seg}")
        # read DCM-SEG
        dcm_ds = pydicom.dcmread(p_dcm_seg.as_posix())
        # get sitk labelmap
        reader = pydicom_seg.SegmentReader() # don't need MultiClassReader since no need to extract combined segmentations
        result = reader.read(dcm_ds)
        roi_ids = list(result.available_segments)
        if len(roi_ids) > 0:
            # get one mask as reference for metadata
            seg_sitk_ref = result.segment_image(roi_ids[0])
            self.meta_data = get_metadata_from_seg(seg_sitk_ref)
            for roi_id in roi_ids:
                # get label metadata
                segment_infos = result.segment_infos[roi_id]
                roi_id_meta, abbr, name = self._get_metadata_from_dcm_seg_segment(segment_infos) # roi_id and roi_id_meta are identical
                # get mask image
                mask_sitk = result.segment_image(roi_id)
                self.add_roi(mask_sitk, roi=roi_id, name=name, abbreviation=abbr)
        else:
            logger.warning(f"No ROIs found in DCM SEG file {p_dcm_seg}")

    @staticmethod
    def _get_metadata_from_dcm_seg_segment(segment):
        if 'SegmentNumber' in segment:
            roi_id = segment['SegmentNumber'].value
        else:
            roi_id = None
        if 'SegmentLabel' in segment:
            abbr = segment['SegmentLabel'].value
        else:
            abbr = None
        if 'SegmentDescription' in segment:
            name = segment['SegmentDescription'].value
        else:
            name = None
        return roi_id, abbr, name

    def _init_dcm_rtstruct_2(self, p_dcm_rtstruct, p_dcm_ref):
        """
        This function uses dcmrtstruct2nii
        :param p_dcm_rtstruct: path to RTSTRUCT file
        :param p_dcm_ref: path to folder with reference DICOM image files (required bz rt-utils)
        :return: None
        """
        logger.info(f"Initialization from DCM RTSTRUCT file: {p_dcm_rtstruct}")
        # read RTSTRUCT
        wrapper = DcmRtstruct2NiiWrapper(p_rtstruct=p_dcm_rtstruct, p_dicom_img=p_dcm_ref, p_tmp=None)
        wrapper.convert()
        roi_ids = wrapper.get_roi_ids()
        # use dcm_ref as reference for metadata
        sitk_img_dcm_ref = read_image_files(p_dcm_ref)
        self.meta_data = get_metadata_from_seg(sitk_img_dcm_ref)
        self.p_dcm_ref = p_dcm_ref
        # add ROIs
        for roi_id in roi_ids:
            mask_sitk = wrapper.get_roi_mask_sitk_by_id(roi_id)
            roi_name  = wrapper.get_roi_name_by_id(roi_id)
            self.add_roi(mask_sitk, name=roi_name)

    def _init_bin_seg_file(self, p_segmentation_file):
        logger.info(f"Initialization from (multi-label) segmentation file: {p_segmentation_file}")
        seg_sitk = read_image_files(p_segmentation_file)
        if not seg_sitk.GetPixelIDValue() == 1:
            logger.warning(f"PixelType is {seg_sitk.GetPixelIDTypeAsString()} \n trying to convert to UnsignedInt")
            seg_sitk = sitk.Cast(seg_sitk, sitk.sitkUInt8)
        results  = get_boolean_masks_from_seg(seg_sitk, roi_ids=None, background=0)
        self.meta_data = results['meta_data']
        self.binary_masks = results['binary_masks']

    def _init_ref_image(self, p_reference_image):
        logger.info(f"Initialization of empty segmentation from reference image: {p_reference_image}")
        ref_sitk = read_image_files(p_reference_image)
        meta_data = get_metadata_from_seg(ref_sitk)
        self.meta_data = meta_data
        self.binary_masks = {}

    def _find_highest_res_mask_file(self, path_list):
        n_spacing_list = []
        for path in path_list:
            seg_sitk = sitk.ReadImage(path.as_posix())
            n_spacing_list.append(np.sum(seg_sitk.GetSpacing()))
            min = np.argmin(n_spacing_list)
            if isinstance(min, list):
                if len(min)>0:
                    return path_list[min[0]]
                else:
                    return None
            else:
                return path_list[min]

    def _init_mask_folder(self, p_segmentation_folder, mask_glob='*desc-*', regex='desc-\w+', force_inconsistent_masks=False, p_seg_ref=None):
        logger.info(f"Initialization from folder of binary masks: {p_segmentation_folder}")
        mask_files = list(p_segmentation_folder.glob(mask_glob))
        logger.debug(f"Found {len(mask_files)} masks in {p_segmentation_folder}")
        if len(mask_files)>0:
            if p_seg_ref is not None:
                p_ref = Path(p_seg_ref)
            else:
                p_ref = Path(self._find_highest_res_mask_file(mask_files))
            seg_sitk_ref = sitk.ReadImage(p_ref.as_posix())
            self.meta_data = get_metadata_from_seg(seg_sitk_ref)
            if force_inconsistent_masks:
                self.p_mask_ref = p_seg_ref
                orientation_filter = sitk.DICOMOrientImageFilter()
                target_orientation = orientation_filter.GetOrientationFromDirectionCosines(seg_sitk_ref.GetDirection())
                self.mask_orientation = target_orientation
            for mask_file in mask_files:
                seg_sitk = sitk.ReadImage(mask_file.as_posix())
                roi = self._decode_mask_name(mask_file.name, regex=regex)
                self.add_roi(seg_sitk, roi=roi, overwrite=False, force=force_inconsistent_masks) # also checks metadata for consistency
        else:
            logger.warning(f"No mask files found in '{p_segmentation_folder}' using mask_glob='{mask_glob}'")

    def select_rois(self, roi_list: list, query_by='id'):
        if (roi_list is None) or (len(roi_list) == 0):
            roi_list = self.get_roi_ids()
        if query_by == 'id':
            roi_list = roi_list
        elif query_by == 'name':
            roi_list = [ self.labels.get_roi_id_from_name(name) for name in roi_list ]
        roi_id_list = [roi_id for roi_id in roi_list if not roi_id is None]
        rois_not_selected = [roi_id for roi_id in self.get_roi_ids() if not roi_id in roi_id_list]
        self.remove_rois_by_id(rois=rois_not_selected)

    def select_rois_by_id(self, rois=None):
        self.select_rois(roi_list=rois, query_by='id')

    def rename_rois(self, query_rename_map={}, query_in='name_abbreviation', case_sensitive=False, is_regexp=False, select=False):
        rois_renamed = self.labels.rename_rois(query_rename_map, query_in, case_sensitive=case_sensitive, is_regexp=is_regexp)
        if select is True:
            self.select_rois(roi_list=rois_renamed, query_by='id')

    def get_rois(self, roi_list, query_by='id'):
        if query_by=='id':
            rois = [ self.get_roi(roi_id) for roi_id in roi_list ]
        elif query_by=='name':
            rois = [ self.get_roi(self.labels.get_roi_id_from_name(name)) for name in roi_list ]
        else:
            rois = []
            logger.fatal(f"'query_by only accepts values 'id' or 'name'")
        return rois

    def add_roi_union(self, roi_list: list, roi_new_name='merged', query_by='id', remove_original=False):
        old_rois = self.get_rois(roi_list, query_by=query_by)
        new_roi  = get_union(old_rois)
        self.add_roi(new_roi, name=roi_new_name)
        if remove_original:
            self.remove_rois_by_id(rois=roi_list)

    def add_roi_intersection(self, roi_list: list, roi_new_name='intersected', query_by='id', remove_original=False):
        old_rois = self.get_rois(roi_list, query_by=query_by)
        new_roi  = get_intersection(old_rois)
        self.add_roi(new_roi, name=roi_new_name)
        if remove_original:
            self.remove_rois_by_id(rois=roi_list)

    def add_roi_difference(self, roi_list_reference: list, roi_list_to_remove: list, roi_new_name='difference', query_by='id',  remove_original=False):
        rois_ref = self.get_rois(roi_list_reference, query_by=query_by)
        rois_to_remove = self.get_rois(roi_list_to_remove, query_by=query_by)
        new_roi  = get_difference(rois_ref, rois_to_remove)
        self.add_roi(new_roi, name=roi_new_name)
        if remove_original:
            self.remove_rois_by_id(rois=rois_ref)
            self.remove_rois_by_id(rois=rois_to_remove)

    def remove_rois_by_id(self, rois=None):
        if rois is None:
            rois = []
        for roi in rois:
            self.remove_roi_by_id(roi)

    def remove_roi_by_id(self, roi=None):
        if roi is None:
            logger.warning(f"No ROI specified")
        elif not self.has_roi(roi):
            logger.warning(f"ROI does not exist")
        else:
            logger.info(f"Removing ROI {roi}")
            self.binary_masks.pop(roi)
            if self._has_labels():
                self.labels.remove_roi_id(roi)

    def get_roi(self, roi_id):
        if roi_id in self.get_roi_ids():
            return self.binary_masks[roi_id]
        else:
            logger.warning(f"ROI ID {roi_id} does not exist")

    def add_roi(self, mask, roi=None, name=None, abbreviation=None, overwrite=False, force=True):
        # check ROI IDs
        if roi is None:
            if (name is not None) and self._has_labels(): # try to get roi_id from labels -> None if labels is empty
                roi = self.labels.get_roi_id_from_abbreviation(name)
                overwrite = True # if roi_id inferred from loaded labelmap -> replace existing self.labels entry

            if roi is None:
                if self.get_max_roi_id() is not None:
                    roi = self.get_max_roi_id() + 1
                    logger.warning(f"No ROI specified, using next free ROI ID {roi}")
                else: # happens if there is no other roi in segmentation
                    roi = 1

        elif (roi in self.get_roi_ids()) and not overwrite:
            logger.fatal(f"ROI ID {roi} already used. Remove existing ROI or change ID")
            roi = None
        elif (roi in self.get_roi_ids()) and overwrite:
            logger.info(f"ROI ID {roi} already used. Will overwrite")
        else:
            logger.info(f"Adding mask as ROI ID {roi}.")
        # check masks
        check_ok, boolean_mask  = self._check_mask(mask, force=force)

        if (roi is not None) and check_ok:
            self.binary_masks[roi] = boolean_mask
            if self._has_labels() and (name is not None):
                self.labels.add_roi(name, roi_id=roi, abbreviation=abbreviation, overwrite=overwrite)
        else:
            logger.fatal("Cannot add mask")

    def _check_mask(self, mask, force=False):
        check_ok = False
        bin_mask = None
        if isinstance(mask, sitk.Image):
            logger.debug("Got mask as sitk image")
            if self._check_mask_sitk_meta(mask):
                results = get_boolean_masks_from_seg(mask)
                if len(results['binary_masks'])==1:
                    bin_mask = list(results['binary_masks'].values())[0]
                    check_ok = True
                else:
                    logger.fatal(f"Found {len(results['binary_masks'])} masks. Only one mask is expected")
            else:
                if force:
                    logger.warning(f"Mask metadata different than expected; forcing inclusion via resampling")
                    if hasattr(self, 'mask_orientation'):
                        mask = self.match_orientation(mask, self.mask_orientation)
                    if hasattr(self, 'p_mask_ref'):
                        mask = self.match_size(mask, self.p_mask_ref)
                    results = get_boolean_masks_from_seg(mask)
                    if len(results['binary_masks']) == 1:
                        bin_mask = list(results['binary_masks'].values())[0]
                        check_ok = True
                    else:
                        logger.fatal(f"Found {len(results['binary_masks'])} masks. Only one mask is expected")

        elif isinstance(mask, np.ndarray):
            logger.debug("Got mask as numpy array")
            if self._check_mask_np_array_meta(mask):
                roi_ids_in_mask = np.unique(mask).tolist()
                roi_ids_in_mask.remove(0)
                if len(roi_ids_in_mask)==1:
                    bin_mask = mask.astype(bool)
                    check_ok = True
                else:
                    logger.fatal(f"Found {len(roi_ids_in_mask)} masks. Only one mask is expected")
        else:
            logger.fatal(f"Expect mask of type 'np.ndarray' or 'sitk.Image'; got '{type(mask)}'")
        return check_ok, bin_mask

    def _check_mask_np_array_meta(self, mask):
        shape = mask.shape
        if shape==self.meta_data['shape']:
            return True
        else:
            logger.fatal(f"Shape of new mask ({shape}) does not agree with reference ({self.meta_data['shape']})")
            return False

    def _check_mask_sitk_meta(self, mask):
        mask_meta = get_metadata_from_seg(mask)
        tests = []
        for key in mask_meta.keys():
            meta_mask = tuple(np.round(mask_meta[key],self.precision))
            meta_ref  = tuple(np.round(self.meta_data[key],self.precision))
            if meta_mask==meta_ref:
                tests.append(True)
            else:
                logger.fatal(f"{key} of new mask ({meta_mask}) does not agree with reference ({meta_ref})")
                tests.append(False)
        if np.all(tests):
            return True
        else:
            return False

    def swap_roi_ids(self, roi_id_old, roi_id_new):
        mask = self.get_roi(roi_id_old).copy()
        if self._has_labels():
            name = self.labels.get_name_from_roi_id(roi_id_old)
            abbreviation = self.labels.get_abbreviation_from_roi_id(roi_id_old)
        else:
            name = 'unknown'
            abbreviation = 'unknown'
        self.remove_roi_by_id(roi_id_old)
        self.add_roi(mask, roi_id_new)
        if self._has_labels():
            self.labels.add_roi(name=name, roi_id=roi_id_new, abbreviation=abbreviation)

    def has_roi(self, roi=None):
        if roi is not None:
            return (roi in self.get_roi_ids())


    def write_seg(self, p: Path, base_name=None, mode='masks', label_name='labels.tsv', no_overlap='enforce', p_ref=None):
        if p_ref is not None:
            if p_ref.exists():
                self.p_out_ref = p_ref
        if base_name is None:
            base_name = 'segmentation'
        if mode == 'masks':
            self.write_seg_as_boolean_masks(p=p, base_name=base_name, p_ref=p_ref)
        elif mode == 'labelmap':
            self.write_seg_as_labelmap(p=p, base_name=base_name, p_ref=p_ref, no_overlap=no_overlap)
        elif mode == 'rtstruct':
            self.write_seg_as_dcm_rtstruct(p=p, base_name=base_name, p_ref=p_ref)
        elif mode == 'dcmseg':
            self.write_seg_as_dcm_seg_multiclass(p=p, base_name=base_name, p_ref=p_ref)
        else:
            logger.fatal(f"Mode {mode} undefined. Choose from modes 'masks' or 'labelmap'")


    def write_seg_as_boolean_masks(self, p: Path, base_name: str, p_ref=None):
        self.labels.generate_abbreviations_from_names()
        p.mkdir(exist_ok=True, parents=True)
        # setting target orientation if requested
        self.set_target_orientation_from_file(p_ref)
        for roi in self.get_roi_ids():
            sitk_mask = self.get_mask_as_sitk(roi)
            mask_name = self._create_mask_name(base_name, roi)
            p_out = p.joinpath(mask_name)
            logger.debug(f"Writing ROI {roi} to {p_out}")
            logger.debug(f"TYPE {type(sitk_mask)}")
            sitk.WriteImage(sitk_mask, p_out.as_posix())

    def has_target_orientation(self):
        return hasattr(self, 'target_orientation')

    def write_seg_as_labelmap(self, p: Path, base_name: str, no_overlap='enforce', p_ref=None):
        p.mkdir(exist_ok=True, parents=True)
        # setting target orientation if requested
        self.set_target_orientation_from_file(p_ref)
        # get sitk file
        labelmap_sitk = self.get_labelmap_as_sitk(no_overlap)
        if not labelmap_sitk is None:
            labelmap_name = self._create_labelmap_name(base_name)
            p_out = p.joinpath(labelmap_name)
            logger.debug(f"Writing labelmap to {p_out}")
            sitk.WriteImage(labelmap_sitk, p_out.as_posix())


    def write_seg_as_dcm_rtstruct(self, p: Path, base_name: str, p_ref=None):
        p.mkdir(exist_ok=True, parents=True)
        # setting target orientation if requested
        self.set_target_orientation_from_file(p_ref)
        # get rt struct file
        labelmap_rtstruct = self.get_labelmap_as_dcm_rtstruct(p_ref)
        if not labelmap_rtstruct is None:
            rtstruct_name = self._create_rtstruct_name(base_name)
            p_out = p.joinpath(rtstruct_name)
            logger.debug(f"Writing RTSTRUCT to {p_out}")
            labelmap_rtstruct.save(p_out.as_posix())

    def write_seg_as_dcm_seg_multiclass(self, p: Path, base_name: str, p_ref=None):
        p.mkdir(exist_ok=True, parents=True)
        # setting target orientation if requested
        self.set_target_orientation_from_file(p_ref)
        # get dcm-seg file
        labelmap_dcm_seg = self.get_labelmap_as_dcm_seg(p_ref, base_name)
        if not labelmap_dcm_seg is None:
            dcm_seg_name = self._create_dcm_seg_name(base_name)
            
            p_out = p.joinpath(dcm_seg_name)
            logger.debug(f"Writing DCM-SEG to {p_out}")
            labelmap_dcm_seg.save_as(p_out.as_posix())

    @staticmethod
    def match_orientation(sitk_img, target_orientation):
        orientation_filter = sitk.DICOMOrientImageFilter()
        orientation_filter.SetDesiredCoordinateOrientation(target_orientation)
        logger.info(f"Orientation: {sitk_img.GetDirection()} -> Target Orientation: {target_orientation}")
        sitk_mask = orientation_filter.Execute(sitk_img)
        logger.info(f"   ... adjusted Orientation: {sitk_mask.GetDirection()}")
        return sitk_mask


    def match_size(self, sitk_img, p_ref_img):
        sitk_img_ref = read_image_files(p_ref_img)
        sitk_img_out = match_size(sitk_img_ref, sitk_img, interpolator=sitk.sitkNearestNeighbor)
        return sitk_img_out

    def get_mask_as_sitk(self, roi):
        bin_mask = self.get_roi(roi)
        sitk_mask = self._convert_nparray_to_sitk(bin_mask)
        if self.has_target_orientation():
            sitk_mask = self.match_orientation(sitk_mask, self.target_orientation)
        if hasattr(self, 'p_out_ref'):
            sitk_mask = self.match_size(sitk_mask, self.p_out_ref)
        return sitk_mask


    def get_labelmap_as_sitk(self, no_overlap='enforce'):
        if self._check_rois_no_overlap(no_overlap):
            mask_ref = self.get_roi(self.get_max_roi_id())
            labelmap_np = np.zeros(mask_ref.shape, np.uint8)
            for roi in self.get_roi_ids():
                logger.debug(f"Adding mask of ROI {roi} to labelmap")
                mask = self.get_roi(roi)
                labelmap_np[mask] = int(roi)
                logger.debug(f"ROI {roi}, {mask.sum()} true values")
            logger.debug(f"Final segmentation labelmap contains {len(np.unique(labelmap_np))-1} unique labels")
            labelmap_sitk = self._convert_nparray_to_sitk(labelmap_np)
            if self.has_target_orientation():
                labelmap_sitk = self.match_orientation(labelmap_sitk, self.target_orientation)
            if hasattr(self, 'p_out_ref'):
                labelmap_sitk = self.match_size(labelmap_sitk, self.p_out_ref)
        else:
            logger.fatal("Cannot merge ROIs into single labelmap due to overlap")
            labelmap_sitk = None
        return labelmap_sitk


    def get_labelmap_as_dcm_seg(self, p_dcm_ref=None, base_name=None):
        """
        Uses pydicom-seg [https://github.com/razorx89/pydicom-seg] to generate DCM-SEG file from segmentation.
        It relies on the pydicom-seg's MultiClassWriter which enables simultaneous processing of multiple labels via
        a labelmap (rather than individual binary masks). Consequently, overlapping labels would not be correctly
        encoded by the resulting DCM-SEG file. To avoid accidental merging of overlapping files, this function relies
        on the 'no_overlap' attribute of self.get_labelmap_as_sitk.
        Construction of DCM-SEG files directly from binary masks should be possible and would be preferable.
        However, this scenario is not documented by pydicom-seg ... to be done.
        :param p_dcm_ref: path to reference dcm image files (required by MultiClassWriter)
        :return: pydicom_seg.MultiClassWriter.write() instance
        """

        if (p_dcm_ref is None):
            if hasattr(self, 'p_dcm_ref'):
                logger.info(f"Using '{self.p_dcm_ref}' as reference DCM image for DCM-SEG")
                p_dcm_ref = self.p_dcm_ref

        if p_dcm_ref is not None:
            # get DCM ref source files
            reader = sitk.ImageSeriesReader()
            dcm_ref_files = reader.GetGDCMSeriesFileNames(p_dcm_ref.as_posix())
            # get labelmap (for MultiClass writer)
            labelmap_sitk = self.get_labelmap_as_sitk(no_overlap='enforce')
            # Generate template JSON file based on the ROI dict
            dcm_seg_metadata = self._generate_metadata_for_dcm_seg(base_name)
            # create/define MultiClassWriter
            writer = pydicom_seg.MultiClassWriter(
                template=dcm_seg_metadata,
                inplane_cropping=False,     # Crop image slices to the minimum bounding box on x and y axes
                skip_empty_slices=False,    # Don't encode slices with only zeros
                skip_missing_segment=False, #
            )
            
            dcm_seg = writer.write(labelmap_sitk, dcm_ref_files)
        else:
            logger.fatal(f"No DCM reference series specified. Needed for DCM'SEG construction")
            dcm_seg = None
        return dcm_seg
    
    

    def _generate_metadata_for_dcm_seg(self, base_name):
        # Create segments
        segments = []
        # Define label-to-CIELab mappings
        label_to_rgb = {
            "Periventricular": [139, 0, 0],         # Dark Red
            "Juxtacortical": [255, 102, 102],     # Light Red
            "Infratentorial": [0, 0, 139],         # Dark Blue
            "Deep White Matter": [173, 216, 230],     # Light Blue
            "Default": [255, 255, 255],           # White for default
        }
        
        label_names = ["Periventricular", "Juxtacortical", "Infratentorial", "Deep White Matter"]
        for i, roi in enumerate(self.get_roi_ids()):
            abbr = self.labels.get_abbreviation_from_roi_id(roi)
            name = self.labels.get_name_from_roi_id(roi)
            
            # Extract base name (without uncertainty suffix) for color matching
            base_name_for_color = name.split(" (")[0] if " (" in name else name
            
            if base_name_for_color in label_names:
                if base_name_for_color == label_names[0]:
                    color = label_to_rgb["Periventricular"]
                elif base_name_for_color == label_names[1]:
                    color = label_to_rgb["Juxtacortical"]
                elif base_name_for_color == label_names[2]:
                    color = label_to_rgb["Infratentorial"]
                elif base_name_for_color == label_names[3]:
                    color = label_to_rgb["Deep White Matter"]
            
            else:    
                color = label_to_rgb["Default"]
                logger.warning(f"Label '{name}' not found in label_to_rgb mapping. Using default color.")
            
            segments.append(get_segment(roi, abbr, name, color))

        series_description=f"{base_name}_segmentation"
        
        basic_info = {
            "ContentCreatorName": "XXX via pydicom-seg",
            "ClinicalTrialSeriesID": "Session1",
            "ClinicalTrialTimePointID": "1",
            "SeriesDescription": series_description,
            "SeriesNumber": "300",
            "InstanceNumber": "1",
            "segmentAttributes": [segments],
            "ContentLabel": "DCM_SEG",
            "ContentDescription": "Image segmentation",
            "ClinicalTrialCoordinatingCenterName": "dcmqi",
            "BodyPartExamined": "",
        }
        
        template = pydicom_seg.template.from_dcmqi_metainfo(basic_info)
        return template


    def _convert_nparray_to_sitk(self, np_array):
        np_array_int = np_array.copy().astype(int)
        sitk_mask = sitk.Cast(sitk.GetImageFromArray(np_array_int), sitk.sitkUInt8)
        sitk_mask.SetSpacing(self.meta_data['spacing'])
        sitk_mask.SetOrigin(self.meta_data['origin'])
        sitk_mask.SetDirection(self.meta_data['direction'])
        return sitk_mask

    def compute_roi_intersection(self):
        roi_combinations = list(itertools.combinations(self.get_roi_ids(), 2))
        intersection_list = []
        for roi_1, roi_2 in roi_combinations:
            mask_1 = self.get_roi(roi_1)
            mask_2 = self.get_roi(roi_2)
            result = intersection_bin_mask(mask_1, mask_2, rel_to=1)
            result['mask_1'] = roi_1
            result['mask_2'] = roi_2
            intersection_list.append(pd.Series(result))
        if len(intersection_list) == 0:
            df_intersection = pd.DataFrame()
        else:
            df_intersection = pd.concat(intersection_list, axis=1).T
        return df_intersection

    def _check_rois_no_overlap(self, mode):
        df_intersection = self.compute_roi_intersection()
        if df_intersection.empty: # only single roi
            df_sel = pd.DataFrame()
        else:
            df_sel = df_intersection[df_intersection.n_intersection > 0]
            for idx, row in df_sel.iterrows():
                logger.warning(f"Overlap between masks {row['mask_1']} & {row['mask_2']}")
            df_sel2 = df_intersection[df_intersection.rel_intersection==1]
            for idx, row in df_sel2.iterrows():
                logger.warning(f"Masks {row['mask_1']} & {row['mask_2']} appear to be identical")

        if (len(df_sel) > 0):
            if mode=='ignore':
                logger.warning(f"Found overlaps between masks but ignore -- ROIs in resulting labelmap will differ from individual masks")
                test_ok = True
            elif mode=='enforce':
                logger.fatal(f"Found overlaps between masks -- cannot produce lablemap ")
                test_ok = False
            else:
                logger.fatal(f"Mode '{mode}' not defined ")
                test_ok = False
        else:
            test_ok = True
        return test_ok

    def _create_mask_name(self, base_name, roi):
        roi_name  = self.labels.get_abbreviation_from_roi_id(roi)
        mask_name = f"{base_name}_desc-{roi_name}.nii.gz"
        return mask_name

    def _decode_mask_name(self, mask_name, regex=r'desc-\w+'):
        if isinstance(mask_name, Path):
            mask_name = mask_name.name
        # pattern = r'mask-\d+'
        masks = re.findall(regex, mask_name)
        if len(masks) == 1:
            roi_name_abbr = masks[0].split('-')[-1]
            roi = self.labels.get_roi_id_from_abbreviation(roi_name_abbr)
        else:
            logger.fatal(f"Did not find ROI ids in mask name '{mask_name}'")
            roi = None
        return roi

    @staticmethod
    def _create_labelmap_name(base_name):
        labelmap_name = f"{base_name}_labelmap.nii.gz"
        return labelmap_name

    @staticmethod
    def _create_rtstruct_name(base_name):
        rtstruct_name = f"{base_name}_rtstruct.dcm"
        return rtstruct_name

    @staticmethod
    def _create_dcm_seg_name(base_name):
        dcm_seg_name = f"{base_name}_dcmseg.dcm"
        return dcm_seg_name