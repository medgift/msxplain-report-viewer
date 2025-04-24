docker run --rm \
    -v "/home/lluis/msxplain/msxplain_report_viewer/backend/files":"/repo" \
    seglib:latest \
    micromamba run -n base python -m bin.segmentation_converter \
    --p_seg_in="/repo/processed/run_20250424_113805/4031-5791/2021-09-03/SAMSEG/WM_Mask.nii.gz" \
    --p_dcm_ref="/repo/DICOMS/4031-5791/2021-09-03/t1n_3d" \
    --p_seg_out_dir="/repo/output/labelmap-to-DCMSEG_atlas/" \
    --out_basename="atlas_wm_mask" \
    --output_format="dcmseg" \
    --loglevel='debug'