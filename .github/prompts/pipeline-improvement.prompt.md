# Pipeline Improvement Skill

You are working on the MSXplain MS lesion segmentation pipeline. This is a **medical imaging application** where correctness and reproducibility are critical. Every change must be clinically defensible.

## Architecture You Must Understand

The pipeline lives in `backend/msxplain/` and is orchestrated by the `MSXplainReport` class in `msxplain_report.py`. Processing is triggered from `app.py` via `process_all_patients()` using FastAPI `BackgroundTasks`.

### Two Model Architectures

1. **SwinUNETR Ensemble** (primary, 5 models in `ensemble_models/`):
   - Inference: `ensemble_inference.py` → `pred.npz`
   - Uncertainty: `compute_uncertainty.py` → `voxel_uncs.nii.gz`, `lesion_uncs.nii.gz`, `patient_uncs.csv`, `pred.nii.gz`
   - ROI: [64, 64, 64], overlap 0.5, binarization threshold 0.5
   - Pruning: connected components ≤ 3 voxels removed

2. **MONAI 3D UNet** (fallback, single model in `model/`):
   - Inference: `predict.py` → `pred.nii.gz`
   - ROI: [96, 96, 96], overlap 0.25, threshold 0.3
   - Architecture: channels=[32,64,128,256,512], strides=[2,2,2,2], batch norm

### Preprocessing Chain (order matters)

```
dcm2niix → fslorient (copysform2qform + reorient2std) → N4BiasFieldCorrection → HD-BET (skull strip) → ANTs rigid registration (FLAIR → T1 space)
```

### Post-Processing Chain

```
WMH-SynthSeg (parcellation) → FSL threshold (structure masks) → Lesion classification (connected components + structure overlap) → ANTs inverse transform → DCM-SEG export
```

### Uncertainty Pipeline

- **Voxel-level**: Predictive entropy of ensemble probability maps via `entropy_of_expected()`
- **Lesion-level (LLU)**: `1 − mean IoU` of per-lesion connected components across ensemble members via `lesion_structural_uncertainty()`
- **Patient-level (PSU)**: `1 − mean IoU` between ensemble consensus and individual member predictions
- Parallel processing via `joblib` for lesion-level computation

### Key Modules

| Module | Purpose |
|--------|---------|
| `model.py` | SwinUNETR architecture (Swin Transformer encoder + UNet decoder, 1131 lines) |
| `transforms.py` | `get_cc_mask()`, `process_probs()`, `remove_connected_components()`, `get_valnotarget_transforms()` |
| `datasets.py` | `NiftiDataset`, `NiftinotargetDataset` (extends MONAI `CacheDataset`) |
| `data_handling.py` | `NpzDataset` — loads compressed ensemble predictions from NPZ |
| `lesion_extraction.py` | `get_lesion_types_masks()` — TPL/FPL/USL/FNL classification via IoU |
| `lesion_information.py` | `generate_lesion_report()` — produces `report.csv` + `lesion_map.nii.gz` |
| `parcellation_processing.py` | `run_parcellation()` — WMH-SynthSeg + FSL thresholding for structure masks |
| `seglib/` | `Segmentation` class for NIfTI ↔ DCM-SEG conversion |

## Strict Rules

1. **Never modify model checkpoint files** or change the ensemble size (5 models).
2. **Preserve the preprocessing chain order** — each step depends on the previous output.
3. **Pin all external tool versions** in the Dockerfile by git commit SHA.
4. **Preserve spatial metadata**: Use `CopyInformation()` (SimpleITK) or copy headers (nibabel) for all NIfTI operations.
5. **Pruning thresholds** (≤3 voxels ensemble, <4 voxels report) are clinically validated — document any change.
6. **GPU memory**: Use `torch.no_grad()` during inference, `torch.cuda.empty_cache()` after.
7. **Logging**: `logger.info()` for step transitions with timing, `logger.debug()` for per-item details.
8. **New transforms**: Add to `transforms.py`, follow MONAI dict-based transform conventions.
9. **New datasets**: Extend `CacheDataset` in `datasets.py`, support `cache_rate` and `num_workers`.
10. **Testing**: Use synthetic NIfTI volumes (32³ or similar). NEVER commit real patient data.

## Output Requirements

- Type hints on all function signatures.
- Google-style docstrings on all public functions.
- Integration point in `msxplain_report.py` if adding a new pipeline step.
- Updated `processing_status` steps in `app.py` `process_all_patients()` if adding user-visible steps.
- If changing thresholds: clinical rationale in a code comment.
