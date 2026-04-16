import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Niivue, SLICE_TYPE } from '@niivue/niivue';
import './Brain3DViewer.css';

/**
 * Orthanc DCM-SEG colour scheme for lesion types.
 * Used to build both the NiiVue LUT and the UI legend.
 */
const LESION_COLORS = [
  // idx 0 = background → transparent (not listed)
  { label: 'Periventricular',   r: 139, g:   0, b:   0 }, // 1
  { label: 'Juxtacortical',     r: 255, g: 102, b: 102 }, // 2
  { label: 'Infratentorial',    r:   0, g:   0, b: 139 }, // 3
  { label: 'Deep White Matter', r: 173, g: 216, b: 230 }, // 4
];

/**
 * Build a 256-entry RGBA look-up table for the 4 lesion-type codes.
 *
 * With cal_min = 0 and cal_max = 4 NiiVue linearly maps:
 *   value 0 → LUT[0],  value 1 → LUT[64],
 *   value 2 → LUT[128], value 3 → LUT[192], value 4 → LUT[255].
 *
 * We paint constant-colour bands around those anchor points so every
 * integer value gets the correct colour without interpolation artefacts.
 */
const buildLesionColormap = () => {
  const R = new Array(256).fill(0);
  const G = new Array(256).fill(0);
  const B = new Array(256).fill(0);
  const A = new Array(256).fill(0);

  // Band boundaries (inclusive):  [lo, hi]
  const bands = [
    [32,  95],  // value 1 – Periventricular
    [96,  159], // value 2 – Juxtacortical
    [160, 223], // value 3 – Infratentorial
    [224, 255], // value 4 – Deep White Matter
  ];

  bands.forEach(([lo, hi], i) => {
    const c = LESION_COLORS[i];
    for (let j = lo; j <= hi; j++) {
      R[j] = c.r;
      G[j] = c.g;
      B[j] = c.b;
      A[j] = 255;
    }
  });

  return { R, G, B, A };
};

/**
 * Brain3DViewer
 * Renders an interactive 3D brain volume with lesion overlay using NiiVue (WebGL2).
 *
 * Props:
 *   run_id       {string} – pipeline run identifier
 *   patient_name {string} – patient folder name
 *   session      {string} – session date folder name
 *   lesionCount  {number} – total non-FP lesion count (used to decide whether to show overlay)
 */
const Brain3DViewer = ({ run_id, patient_name, session, lesionCount = 0 }) => {
  const canvasRef = useRef(null);
  const nvRef = useRef(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [viewMode, setViewMode] = useState('3d'); // '3d' | 'multi'
  const [brainOpacity, setBrainOpacity] = useState(30); // 0–100 %
  const [lesionOpacity, setLesionOpacity] = useState(90); // 0–100 %
  const [volumesLoaded, setVolumesLoaded] = useState(false);

  // Build API URLs for the two NIfTI files
  const brainUrl = `/api/nifti/${run_id}/${patient_name}/${session}/flair_brain.nii.gz`;
  const lesionUrl = `/api/nifti-lesion-types/${run_id}/${patient_name}/${session}`;

  // ── Initialise NiiVue once ────────────────────────────────────────────────
  useEffect(() => {
    if (!canvasRef.current) return;

    const nv = new Niivue({
      backColor: [0.08, 0.08, 0.12, 1],   // dark background
      show3Dcrosshair: false,
      isHighResolutionCapable: false,      // avoid 2×/4× pixel cost on HiDPI
      multiplanarForceRender: false,
      isColorbar: false,
      renderDrawAmbientOcclusion: 0,       // disable AO for faster 3D rotation
    });

    nvRef.current = nv;
    nv.attachToCanvas(canvasRef.current);

    // Register the custom lesion-type colour map (Orthanc DCM-SEG palette)
    nv.addColormap('lesion_types', buildLesionColormap());

    // Start in 3-D render mode
    nv.setSliceType(SLICE_TYPE.RENDER);

    const volumes = [
      {
        url: brainUrl,
        name: 'flair_brain.nii.gz',   // explicit name so NiiVue knows the file type
        colormap: 'gray',
        opacity: brainOpacity / 100,
        cal_min: 0,
        cal_max: 0,      // 0 → NiiVue auto-scales
      },
    ];

    if (lesionCount > 0) {
      volumes.push({
        url: lesionUrl,
        name: 'lesion_types.nii.gz',  // explicit name — URL has no extension
        colormap: 'lesion_types',
        opacity: lesionOpacity / 100,
        cal_min: 0,       // value 0 → LUT[0] (transparent)
        cal_max: 4,       // value 4 → LUT[255] (Deep White Matter)
      });
    }

    let cancelled = false;

    nv.loadVolumes(volumes)
      .then(() => {
        if (cancelled) return;
        // ── Centre the 3-D rendering on the brain tissue ──────────────
        // NiiVue by default centres on the volume bounding-box, but the
        // brain may sit asymmetrically inside the FOV.  We compute the
        // centre-of-mass of non-zero voxels (stride-sampled for speed),
        // convert to mm, and override setPivot3D so every frame pivots
        // around the brain instead of the bounding-box centre.
        const vol = nv.volumes[0];
        if (vol && vol.img && vol.hdr) {
          const nx = vol.hdr.dims[1];
          const ny = vol.hdr.dims[2];
          const nz = vol.hdr.dims[3];
          const data = vol.img;
          const step = 4;                         // sample every 4th voxel
          let sx = 0, sy = 0, sz = 0, cnt = 0;
          for (let z = 0; z < nz; z += step) {
            const zOff = z * nx * ny;
            for (let y = 0; y < ny; y += step) {
              const yzOff = zOff + y * nx;
              for (let x = 0; x < nx; x += step) {
                if (data[yzOff + x] > 0) { sx += x; sy += y; sz += z; cnt++; }
              }
            }
          }
          if (cnt > 0) {
            const fracX = (sx / cnt) / (nx - 1);
            const fracY = (sy / cnt) / (ny - 1);
            const fracZ = (sz / cnt) / (nz - 1);
            const centerMM = nv.frac2mm([fracX, fracY, fracZ]);

            // Patch setPivot3D to use the brain centroid as pivot
            const origSetPivot = nv.setPivot3D.bind(nv);
            nv.setPivot3D = function () {
              origSetPivot();                     // compute extents & furthestFromPivot
              this.pivot3D = [centerMM[0], centerMM[1], centerMM[2]];
            };
          }
        }

        // Set default 3-D viewing angle: 45° between sagittal and frontal
        nv.setRenderAzimuthElevation(135, 15);
        // Zoom in so the brain fills the canvas
        nv.volScaleMultiplier = 1.5;
        nv.updateGLVolume();
        setVolumesLoaded(true);
        setIsLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('NiiVue failed to load volumes:', err);
        setLoadError('Could not load the NIfTI files for 3D rendering.');
        setIsLoading(false);
      });

    return () => {
      cancelled = true;
      // NiiVue doesn't expose a destroy() – just clear the ref
      nvRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run_id, patient_name, session]);

  // ── Sync view mode ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!nvRef.current || !volumesLoaded) return;
    nvRef.current.setSliceType(
      viewMode === '3d' ? SLICE_TYPE.RENDER : SLICE_TYPE.MULTIPLANAR
    );
  }, [viewMode, volumesLoaded]);

  // ── Sync brain opacity ────────────────────────────────────────────────────
  useEffect(() => {
    if (!nvRef.current || !volumesLoaded) return;
    if (!nvRef.current.volumes || !nvRef.current.volumes[0]) return;
    nvRef.current.setOpacity(0, brainOpacity / 100);
  }, [brainOpacity, volumesLoaded]);

  // ── Sync lesion opacity ───────────────────────────────────────────────────
  useEffect(() => {
    if (!nvRef.current || !volumesLoaded || lesionCount === 0) return;
    if (!nvRef.current.volumes || !nvRef.current.volumes[1]) return;
    nvRef.current.setOpacity(1, lesionOpacity / 100);
  }, [lesionOpacity, volumesLoaded, lesionCount]);

  // ── Helpers ───────────────────────────────────────────────────────────────
  const resetView = useCallback(() => {
    if (!nvRef.current) return;
    nvRef.current.setRenderAzimuthElevation(135, 15);
    nvRef.current.volScaleMultiplier = 1.5;
    nvRef.current.updateGLVolume();
  }, []);

  if (loadError) {
    return (
      <div className="brain3d-error">
        <span className="brain3d-error-icon">⚠</span>
        <p>{loadError}</p>
      </div>
    );
  }

  return (
    <div className="brain3d-wrapper">
      {/* ── Toolbar ── */}
      <div className="brain3d-toolbar">
        {/* View mode toggle */}
        <div className="brain3d-toggle-group">
          <button
            className={`brain3d-toggle-btn ${viewMode === '3d' ? 'active' : ''}`}
            onClick={() => setViewMode('3d')}
            title="3D volume rendering"
          >
            3D
          </button>
          <button
            className={`brain3d-toggle-btn ${viewMode === 'multi' ? 'active' : ''}`}
            onClick={() => setViewMode('multi')}
            title="Axial / Coronal / Sagittal"
          >
            MPR
          </button>
        </div>

        {/* Brain opacity */}
        <label className="brain3d-slider-label">
          Brain
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={brainOpacity}
            onChange={(e) => setBrainOpacity(Number(e.target.value))}
            className="brain3d-slider"
            title={`Brain opacity: ${brainOpacity}%`}
          />
          <span className="brain3d-slider-val">{brainOpacity}%</span>
        </label>

        {/* Lesion opacity (only if there are lesions) */}
        {lesionCount > 0 && (
          <label className="brain3d-slider-label">
            Lesions
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={lesionOpacity}
              onChange={(e) => setLesionOpacity(Number(e.target.value))}
              className="brain3d-slider brain3d-slider--lesion"
              title={`Lesion opacity: ${lesionOpacity}%`}
            />
            <span className="brain3d-slider-val">{lesionOpacity}%</span>
          </label>
        )}

        <button className="brain3d-reset-btn" onClick={resetView} title="Reset camera">
          ↺ Reset
        </button>
      </div>

      {/* ── Lesion colour legend ── */}
      {lesionCount > 0 && (
        <div className="brain3d-legend">
          {LESION_COLORS.map(({ label, r, g, b }) => (
            <span key={label} className="brain3d-legend-item">
              <span
                className="brain3d-legend-swatch"
                style={{ background: `rgb(${r},${g},${b})` }}
              />
              {label}
            </span>
          ))}
        </div>
      )}

      {/* ── Canvas ── */}
      <div className="brain3d-canvas-container">
        {isLoading && (
          <div className="brain3d-loading">
            <div className="brain3d-spinner" />
            <p>Loading 3D brain…</p>
          </div>
        )}
        <canvas
          ref={canvasRef}
          className="brain3d-canvas"
          style={{ opacity: isLoading ? 0 : 1 }}
        />
      </div>

      {/* ── Caption ── */}
      <p className="brain3d-caption">
        {viewMode === '3d'
          ? 'Drag to rotate · Scroll to zoom · Right-drag to pan'
          : 'Scroll over each plane to navigate slices'}
        {lesionCount > 0 && (
          <span className="brain3d-caption-lesion"> · Lesions colour-coded by type</span>
        )}
      </p>
    </div>
  );
};

export default Brain3DViewer;
