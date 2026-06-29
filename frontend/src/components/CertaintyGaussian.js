import React from 'react';
import './CertaintyGaussian.css';

/**
 * CertaintyGaussian
 * Renders a fixed decorative standard-normal bell curve and places one or more
 * markers on it by *percentile* (population rank), not by raw value. The bell
 * shape is always identical; only the marker positions change.
 *
 * Each marker is positioned at x = Φ⁻¹(percentile / 100) (the standard-normal
 * quantile), so the 50th percentile sits at the peak, 95th to the right, etc.
 * The value (e.g. 0.91) is shown as the label; the percentile drives placement.
 *
 * Props:
 *   markers         {Array<{ value:number, percentile:number|null, color:string, label?:string }>}
 *   accent          {string}  – fill/stroke colour for the bell (default app blue)
 *   showValueLabels {boolean} – draw the value above each marker (default true).
 *                               Disable when several markers crowd together and
 *                               the values are already listed elsewhere (chips).
 */

// ── Standard-normal quantile (probit) — Acklam's rational approximation ──
const probit = (p) => {
  if (p <= 0) return -3.2;
  if (p >= 1) return 3.2;
  const a = [-39.6968302866538, 220.946098424521, -275.928510446969,
             138.357751867269, -30.6647980661472, 2.50662827745924];
  const b = [-54.4760987982241, 161.585836858041, -155.698979859887,
             66.8013118877197, -13.2806815528857];
  const c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184,
             -2.54973253934373, 4.37466414146497, 2.93816398269878];
  const d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742];
  const pLow = 0.02425;
  const pHigh = 1 - pLow;
  let q, r, x;
  if (p < pLow) {
    q = Math.sqrt(-2 * Math.log(p));
    x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  } else if (p <= pHigh) {
    q = p - 0.5;
    r = q * q;
    x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  } else {
    q = Math.sqrt(-2 * Math.log(1 - p));
    x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
         ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  return Math.max(-3.2, Math.min(3.2, x));
};

const pdf = (z) => Math.exp(-(z * z) / 2); // unnormalised: peak = 1 at z = 0

const CertaintyGaussian = ({ markers = [], accent = '#2196f3', showValueLabels = true }) => {
  // SVG coordinate system
  const W = 600;
  const H = 215;
  const padX = 30;
  const baseline = H - 58;     // y of the curve baseline (room for axis annotations)
  const topPad = showValueLabels ? 26 : 12; // room above the peak for value labels
  const peakH = baseline - topPad;
  const zMin = -3.2;
  const zMax = 3.2;

  const xOf = (z) => padX + ((z - zMin) / (zMax - zMin)) * (W - 2 * padX);
  const yOf = (z) => baseline - pdf(z) * peakH;

  // Bell curve path
  const steps = 120;
  let d = `M ${xOf(zMin).toFixed(1)} ${baseline.toFixed(1)}`;
  for (let i = 0; i <= steps; i++) {
    const z = zMin + (i / steps) * (zMax - zMin);
    d += ` L ${xOf(z).toFixed(1)} ${yOf(z).toFixed(1)}`;
  }
  d += ` L ${xOf(zMax).toFixed(1)} ${baseline.toFixed(1)} Z`;

  // Quartile lines of the standard normal: Q1 (25th), Q2/median (50th), Q3 (75th).
  // These split the test-set population into four equal-sized groups, so a marker
  // landing between Q2 and Q3 sits in the 3rd quartile of the population.
  const quartiles = [
    { z: -0.6744898, label: 'Q1', pct: '25%' },
    { z: 0,          label: 'Q2', pct: '50%' },
    { z: 0.6744898,  label: 'Q3', pct: '75%' },
  ];

  // Central 95% interval of the population: bounds at the 2.5th / 97.5th
  // percentiles (±1.96σ). Drawn as a labelled dimension bracket below the axis.
  const z95 = 1.959964;
  const xL = xOf(-z95);
  const xR = xOf(z95);
  const bracketY = baseline + 42;
  const cx = (xL + xR) / 2;

  // Placeable markers (need a percentile to locate on the bell)
  const placed = markers
    .filter((m) => m.percentile != null && m.value != null)
    .map((m) => {
      const z = probit(m.percentile / 100);
      return { ...m, z, x: xOf(z), y: yOf(z) };
    })
    .sort((a, b) => a.x - b.x);

  // Alternate value-label height when markers crowd together horizontally
  const labelY = (idx, x) => {
    const prev = placed[idx - 1];
    const crowded = prev && x - prev.x < 70;
    return crowded ? -26 : -12;
  };

  // Markers were provided but none could be placed (e.g. reference CSVs missing,
  // so percentiles came back null). Show an explicit notice instead of an empty bell.
  const noPlaceable = markers.length > 0 && placed.length === 0;

  return (
    <svg
      className="certainty-gaussian"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
    >
      {/* baseline */}
      <line x1={padX} y1={baseline} x2={W - padX} y2={baseline}
            stroke="#d0d0d0" strokeWidth="1" />

      {/* 95%-interval bound lines (2.5% / 97.5%) — lighter, behind the bell */}
      {[-z95, z95].map((z) => (
        <line key={z} x1={xOf(z)} y1={yOf(z)} x2={xOf(z)} y2={baseline}
              stroke="#d4d4d4" strokeWidth="1" strokeDasharray="2 3" />
      ))}

      {/* quartile gridlines (stronger, from baseline up to the curve) */}
      {quartiles.map((q) => (
        <line key={q.label} x1={xOf(q.z)} y1={yOf(q.z)} x2={xOf(q.z)} y2={baseline}
              stroke="#9aa0a6" strokeWidth="1.5" strokeDasharray="2 3" />
      ))}

      {/* bell */}
      <path d={d} fill={accent} fillOpacity="0.10"
            stroke={accent} strokeWidth="2.5" strokeOpacity="0.55" />

      {/* quartile labels + percentile under the axis */}
      {quartiles.map((q) => (
        <g key={q.label}>
          <text x={xOf(q.z)} y={baseline + 16} textAnchor="middle"
                className="cg-q-label">{q.label}</text>
          <text x={xOf(q.z)} y={baseline + 29} textAnchor="middle"
                className="cg-pct-label">{q.pct}</text>
        </g>
      ))}

      {/* 95%-interval dimension bracket */}
      <line x1={xL} y1={bracketY} x2={cx - 22} y2={bracketY} stroke="#bdbdbd" strokeWidth="1" />
      <line x1={cx + 22} y1={bracketY} x2={xR} y2={bracketY} stroke="#bdbdbd" strokeWidth="1" />
      <line x1={xL} y1={bracketY - 4} x2={xL} y2={bracketY + 4} stroke="#bdbdbd" strokeWidth="1" />
      <line x1={xR} y1={bracketY - 4} x2={xR} y2={bracketY + 4} stroke="#bdbdbd" strokeWidth="1" />
      <text x={cx} y={bracketY + 4} textAnchor="middle" className="cg-interval-label">95%</text>

      {/* markers */}
      {placed.map((m, idx) => {
        const ly = labelY(idx, m.x);
        return (
          <g key={idx}>
            <line x1={m.x} y1={baseline} x2={m.x} y2={m.y}
                  stroke={m.color} strokeWidth="2" strokeDasharray="4 3" />
            <circle cx={m.x} cy={m.y} r="6" fill={m.color}
                    stroke="#ffffff" strokeWidth="2" />
            {showValueLabels && (
              <text x={m.x} y={m.y + ly} textAnchor="middle"
                    className="cg-value-label" fill={m.color}>
                {m.value.toFixed(2)}
              </text>
            )}
          </g>
        );
      })}

      {/* fallback when markers exist but no percentile could be placed */}
      {noPlaceable && (
        <text x={W / 2} y={baseline / 2} textAnchor="middle"
              className="cg-empty-label">
          Reference distribution unavailable
        </text>
      )}
    </svg>
  );
};

export default CertaintyGaussian;
