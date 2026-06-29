import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import Brain3DViewer from './Brain3DViewer';
import CertaintyGaussian from './CertaintyGaussian';
import './ReportPage.css';

// Lesion-type metadata: canonical order, the report.csv count key, and a
// readable plot colour (aligned with the 3D viewer's lesion palette).
const LESION_TYPES = [
  { key: 'Periventricular',   countKey: 'periventricular', color: '#8b0000' },
  { key: 'Juxtacortical',     countKey: 'juxtacortical',   color: '#ff6666' },
  { key: 'Infratentorial',    countKey: 'infratentorial',  color: '#00008b' },
  { key: 'Deep White Matter', countKey: 'wm',              color: '#5a9bd4' },
];

const num = (v) => Number(v) || 0;

// Small hover/focus info bubble used on the certainty plots.
const InfoTip = ({ text }) => (
  <span className="info-tip" tabIndex={0} aria-label={text}>
    <span className="info-tip-icon">i</span>
    <span className="info-tip-bubble">{text}</span>
  </span>
);

const PATIENT_PLOT_INFO =
  'Reference distribution of patient-level certainty across the model’s test ' +
  'population. The bell is that population; the marker shows where this patient falls. ' +
  'Q1–Q3 split the population into four equal-sized quartiles; the bracket spans the ' +
  'central 95% of patients.';

const LESION_PLOT_INFO =
  'Reference distribution of lesion-level certainty across all lesions in the model’s ' +
  'test population. Each coloured marker is the mean certainty for that lesion type, placed ' +
  'by its percentile. Q1–Q3 split the population into four equal-sized quartiles; the ' +
  'bracket spans the central 95% of lesions.';

const ReportPage = () => {
  const { run_id, patient_name, session } = useParams();
  const [reportData, setReportData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (run_id && patient_name && session) {
      setLoading(true);
      setError(null);
      fetch(`/api/report/${run_id}/${patient_name}/${session}`)
        .then((response) => {
          if (!response.ok) {
            throw new Error('Report not found');
          }
          return response.json();
        })
        .then((data) => {
          if (data.error) {
            setError(data.error);
          } else {
            setReportData(data);
          }
          setLoading(false);
        })
        .catch((err) => {
          setError('Error loading report: ' + err.message);
          setLoading(false);
        });
    }
  }, [run_id, patient_name, session]);

  const openMcDonaldCriteria = () => {
    window.open('https://www.thelancet.com/article/S1474-4422(25)00270-4/fulltext#', '_blank', 'noopener,noreferrer');
  };

  const openOHIFViewer = () => {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    const OHIF_URL = `${protocol}//${hostname}:8042/ohif/`;
    if (reportData && reportData.study_instance_uid) {
      window.open(`${OHIF_URL}viewer?StudyInstanceUIDs=${reportData.study_instance_uid}`, '_blank', 'noopener,noreferrer');
    } else {
      window.open(OHIF_URL, '_blank', 'noopener,noreferrer');
      console.warn('No StudyInstanceUID available, opening OHIF home page');
    }
  };

  // Derived values (only meaningful once reportData is present)
  const counts = reportData
    ? LESION_TYPES.map((t) => ({ ...t, count: num(reportData.lesions[t.countKey]) }))
    : [];
  const totalLesions = counts.reduce((acc, t) => acc + t.count, 0);

  const certainty = reportData && reportData.certainty;
  const patientMarker = certainty && certainty.patient_certainty != null
    ? [{
        value: certainty.patient_certainty,
        percentile: certainty.patient_percentile,
        color: '#1565c0',
      }]
    : [];

  // All four lesion types (for the chips — show "–" when a type has no lesions).
  const lesionAll = certainty
    ? LESION_TYPES.map((t) => ({
        label: t.key,
        color: t.color,
        value: certainty.lesion_type_certainties?.[t.key] ?? null,
        percentile: certainty.lesion_type_percentiles?.[t.key] ?? null,
      }))
    : [];
  // Only types with a value get a marker on the curve.
  const lesionMarkers = lesionAll.filter((m) => m.value != null);

  return (
    <div className="page-container">
      <nav className="navigation-bar">
        <div className="nav-left">
          <Link to="/processed-runs" className="back-button">← Back to Runs</Link>
        </div>
        <div className="nav-center">
          <h2>MSXplain Report</h2>
        </div>
        <div className="nav-right">
          <button onClick={openOHIFViewer} className="action-button">View Images</button>
          <button onClick={openMcDonaldCriteria} className="action-button">McDonald Criteria</button>
        </div>
      </nav>

      <div className="report-content">
        {error && <div className="error-message">{error}</div>}

        {loading && (
          <div className="loading-container">
            <div className="loading-spinner"></div>
            <p>Loading report...</p>
          </div>
        )}

        {reportData && (
          <div className="dashboard">

            {/* ── Patient info strip ── */}
            <section className="patient-strip">
              <div className="pstrip-item">
                <span className="pstrip-label">Patient ID</span>
                <span className="pstrip-value">{reportData.patient_id}</span>
              </div>
              <div className="pstrip-item">
                <span className="pstrip-label">Patient Name</span>
                <span className="pstrip-value">{reportData.patient_name}</span>
              </div>
              <div className="pstrip-item">
                <span className="pstrip-label">Session</span>
                <span className="pstrip-value">{session}</span>
              </div>
              <div className="pstrip-item">
                <span className="pstrip-label">Birth Date</span>
                <span className="pstrip-value">{reportData.patient_birth_date}</span>
              </div>
              <div className="pstrip-item">
                <span className="pstrip-label">Sex</span>
                <span className="pstrip-value">{reportData.patient_sex}</span>
              </div>
            </section>

            {/* ── Band A: patient-level ── */}
            <section className="band band-2col band-patient">
              <div className="card brain-card">
                <Brain3DViewer
                  run_id={run_id}
                  patient_name={patient_name}
                  session={session}
                  lesionCount={totalLesions}
                />
              </div>

              <div className="card certainty-card">
                <div className="card-head">
                  <h3>Patient-level Certainty</h3>
                  <InfoTip text={PATIENT_PLOT_INFO} />
                </div>
                {patientMarker.length > 0 ? (
                  <>
                    <div className="certainty-headline">
                      <div className="certainty-metric">
                        <span className="metric-value">{certainty.patient_certainty.toFixed(2)}</span>
                        <span className="metric-unit">/ 1.00</span>
                        <span className="metric-caption">Certainty</span>
                      </div>
                    </div>
                    <CertaintyGaussian markers={patientMarker} accent="#2196f3" />
                  </>
                ) : (
                  <p className="muted">Certainty data not available.</p>
                )}
              </div>
            </section>

            {/* ── Band B: lesion-level ── */}
            <section className="band band-2col">
              <div className="card findings-card">
                <h3>Findings</h3>
                <div className="findings-summary">
                  <span className="findings-total">{totalLesions} lesions</span>
                  <span className="findings-volume">
                    Total volume: {num(reportData.lesion_volume).toLocaleString(undefined, { maximumFractionDigits: 1 })} mL
                  </span>
                </div>
                <div className="region-grid">
                  {counts.map((t) => (
                    <div className="region-card" key={t.key}>
                      <span className="region-dot" style={{ background: t.color }} />
                      <span className="region-name">{t.key}</span>
                      <span className="region-count">{t.count}</span>
                      <span className="region-unit">Lesions</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="card certainty-card">
                <div className="card-head">
                  <h3>Lesion-level Certainty</h3>
                  <InfoTip text={LESION_PLOT_INFO} />
                </div>
                {lesionMarkers.length > 0 ? (
                  <>
                    <CertaintyGaussian markers={lesionMarkers} accent="#9e9e9e" showValueLabels={false} />
                    <div className="lesion-chips">
                      {lesionAll.map((m) => (
                        <div className="lesion-chip" key={m.label}>
                          <span className="chip-dot" style={{ background: m.color }} />
                          <span className="chip-label">{m.label}</span>
                          <span className="chip-value">
                            {m.value != null ? m.value.toFixed(2) : '–'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="muted">Lesion-level certainty not available.</p>
                )}
              </div>
            </section>

            {/* ── Band C: automated analysis ── */}
            <section className="band-analysis card">
              <h2>Automated Analysis</h2>

              <div className="criteria-section">
                <h4>McDonald Criteria</h4>
                <div className="criteria-cards">
                  <div className="criteria-card">
                    <h5>Dissemination in Space (DIS)*</h5>
                    <p className={reportData.dissemination_space === 'Fulfilled' ? 'crit-yes' : 'crit-no'}>
                      {reportData.dissemination_space}
                    </p>
                  </div>
                  <div className="criteria-card">
                    <h5>Dissemination in Time (DIT)</h5>
                    <p className="crit-na">Not assessed</p>
                  </div>
                </div>
                <p className="criteria-note">
                  *Intracortical, spinal cord, and optic nerve lesions are not assessed.
                  If the criterion is not fulfilled, only white matter lesions are taken into account.
                </p>
              </div>

              <div className="analysis-grid">
                <div className="analysis-block">
                  <h4>Technique</h4>
                  <p>
                    T1 MPRAGE and FLAIR
                    {reportData.scanner &&
                      (
                        [reportData.scanner.manufacturer, reportData.scanner.model, reportData.scanner.field_strength]
                          .filter(Boolean).length > 0 || reportData.scanner.institution
                      ) && (
                      <>
                        {' — '}
                        {[reportData.scanner.manufacturer, reportData.scanner.model, reportData.scanner.field_strength]
                          .filter(Boolean).join(' ')}
                        {reportData.scanner.institution && (
                          <span className="muted">{` (${reportData.scanner.institution})`}</span>
                        )}
                      </>
                    )}
                  </p>
                </div>

                <div className="analysis-block">
                  <h4>Atrophy</h4>
                  <p>Visually age-appropriate.</p>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
