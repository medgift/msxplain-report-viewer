import React, { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import Brain3DViewer from './Brain3DViewer';
import './ReportPage.css';

const ReportPage = () => {
  const { run_id, patient_name, session } = useParams(); // Add session to URL parameters
  const [patientName, setPatientName] = useState(patient_name || ''); // Initialize state with patient_name from URL or empty string
  const [reportData, setReportData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (run_id && patient_name && session) {  // Add session check
      setLoading(true);
      setError(null); // Clear previous error
      fetch(`/api/report/${run_id}/${patient_name}/${session}`)  // Add session to API call
        .then((response) => {
          if (!response.ok) {
            throw new Error('Report not found');
          }
          return response.json();
        })
        .then((data) => {
          if (data.error) {
            setError(data.error); // Handle error from backend
          } else {
            console.log('Report data received:', data);
            console.log('StudyInstanceUID:', data.study_instance_uid);
            setReportData(data); // Set the summary data
          }
          setLoading(false); // Set loading to false after data is fetched
        })
        .catch((err) => {
          setError('Error loading report: ' + err.message); // Handle network errors
          setLoading(false);
        });
    }
  }, [run_id, patient_name, session]);  // Add session to dependency array

  const openMcDonaldCriteria = () => {
    window.open('https://www.thelancet.com/article/S1474-4422(25)00270-4/fulltext#', '_blank', 'noopener,noreferrer');
  };

  const openOHIFViewer = () => {
    // Use the current protocol and hostname (works on any server/IP)
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    const OHIF_URL = `${protocol}//${hostname}:8042/ohif/`;
    
    // Check if we have the StudyInstanceUID from the report data
    if (reportData && reportData.study_instance_uid) {
      const viewerUrl = `${OHIF_URL}viewer?StudyInstanceUIDs=${reportData.study_instance_uid}`;
      window.open(viewerUrl, '_blank', 'noopener,noreferrer');
    } else {
      // Fallback to OHIF home page if no StudyInstanceUID is available
      window.open(OHIF_URL, '_blank', 'noopener,noreferrer');
      console.warn('No StudyInstanceUID available, opening OHIF home page');
    }
  };

  const handleLoadReport = () => {
    if (run_id && session) {  // Add session check
      navigate(`/report/${run_id}/${patientName}/${session}`);  // Add session to navigation
    }
  };

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
          <button onClick={openOHIFViewer} className="action-button">
            View Images
          </button>
          <button onClick={openMcDonaldCriteria} className="action-button">
            McDonald Criteria
          </button>
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
          <div className="content-container">

            <section className="report-section">
              <div className="patient-info">
                <p><strong>Patient Name:</strong> {reportData.patient_name}</p>
                <p><strong>Patient ID:</strong> {reportData.patient_id}</p>
                <p><strong>Session Date:</strong> {session}</p>  {/* Add session date display */}
                <p><strong>Birth Date:</strong> {reportData.patient_birth_date}</p>
                <p><strong>Sex:</strong> {reportData.patient_sex}</p>
              </div>

              {/* ── 3D Brain Visualisation ── */}
              <div className="report-section brain3d-section">
                <h3>3D Brain Visualisation</h3>
                <Brain3DViewer
                  run_id={run_id}
                  patient_name={patient_name}
                  session={session}
                  lesionCount={
                    (Number(reportData.lesions.periventricular) || 0) +
                    (Number(reportData.lesions.juxtacortical) || 0) +
                    (Number(reportData.lesions.infratentorial) || 0) +
                    (Number(reportData.lesions.wm) || 0)
                  }
                />
              </div>
              
              {/* Certainty Section */}
              {reportData.certainty && reportData.certainty.patient_certainty !== null && (
                <div className="certainty-section">
                  <h3>Prediction Certainty</h3>
                  <div className="certainty-container-2col">
                    {/* Left Column: Certainty Values */}
                    <div className="certainty-left-column">
                      <div className="certainty-main">
                        <div className="certainty-value-card">
                          <span className="certainty-label">Patient-Level Certainty </span>
                          <span className="certainty-value">
                            {(reportData.certainty.patient_certainty * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                      
                      {/* Lesion Type Certainties */}
                      {Object.keys(reportData.certainty.lesion_type_certainties).some(
                        key => reportData.certainty.lesion_type_certainties[key] !== null
                      ) && (
                        <div className="certainty-details">
                          <h4>Average Certainty by Lesion Type</h4>
                          <div className="certainty-lesion-types">
                            {reportData.certainty.lesion_type_certainties['Periventricular'] !== null && (
                              <div className="certainty-type-item">
                                <span className="type-label">Periventricular:</span>
                                <span className="type-value">
                                  {(reportData.certainty.lesion_type_certainties['Periventricular'] * 100).toFixed(1)}%
                                </span>
                              </div>
                            )}
                            {reportData.certainty.lesion_type_certainties['Juxtacortical'] !== null && (
                              <div className="certainty-type-item">
                                <span className="type-label">Juxtacortical:</span>
                                <span className="type-value">
                                  {(reportData.certainty.lesion_type_certainties['Juxtacortical'] * 100).toFixed(1)}%
                                </span>
                              </div>
                            )}
                            {reportData.certainty.lesion_type_certainties['Infratentorial'] !== null && (
                              <div className="certainty-type-item">
                                <span className="type-label">Infratentorial:</span>
                                <span className="type-value">
                                  {(reportData.certainty.lesion_type_certainties['Infratentorial'] * 100).toFixed(1)}%
                                </span>
                              </div>
                            )}
                            {reportData.certainty.lesion_type_certainties['Deep White Matter'] !== null && (
                              <div className="certainty-type-item">
                                <span className="type-label">Deep White Matter:</span>
                                <span className="type-value">
                                  {(reportData.certainty.lesion_type_certainties['Deep White Matter'] * 100).toFixed(1)}%
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Right Column: Certainty Distribution Histogram */}
                    <div className="certainty-right-column">
                      <div className="histogram-container">
                        <img
                          src={`/api/certainty-histogram/${run_id}/${patient_name}/${session}`}
                          alt="Patient Certainty Distribution"
                          className="histogram-image"
                          onError={(e) => {
                            e.target.style.display = 'none';
                            e.target.nextSibling.style.display = 'flex';
                          }}
                        />
                        <div className="histogram-fallback" style={{ display: 'none' }}>
                          <div className="histogram-icon">📊</div>
                          <p>Certainty Distribution Histogram</p>
                          <span className="placeholder-text">Not available</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              
              <h2>Automated Analysis</h2>
              
              <div className="subsection">
                <h3>Technique</h3>
                <p>
                  T1 MPRAGE and FLAIR
                  {reportData.scanner &&
                    (
                      [
                        reportData.scanner.manufacturer,
                        reportData.scanner.model,
                        reportData.scanner.field_strength,
                      ].filter(Boolean).length > 0 ||
                      reportData.scanner.institution
                    ) && (
                    <>
                      {' — '}
                      {[reportData.scanner.manufacturer, reportData.scanner.model, reportData.scanner.field_strength]
                        .filter(Boolean)
                        .join(' ')}
                      {reportData.scanner.institution && (
                        <span style={{ color: '#888' }}>{` (${reportData.scanner.institution})`}</span>
                      )}
                    </>
                  )}
                </p>
              </div>

              <div className="subsection findings-section">
                <h3>Findings</h3>

                <div className="lesion-stats">
                  <div className="stat-card">
                    <h4>Periventricular</h4>
                    <span className="stat-value">{reportData.lesions.periventricular}</span>
                  </div>
                  <div className="stat-card">
                    <h4>Juxtacortical</h4>
                    <span className="stat-value">{reportData.lesions.juxtacortical}</span>
                  </div>
                  <div className="stat-card">
                    <h4>Infratentorial</h4>
                    <span className="stat-value">{reportData.lesions.infratentorial}</span>
                  </div>
                  <div className="stat-card">
                    <h4>Deep White Matter</h4>
                    <span className="stat-value">{reportData.lesions.wm}</span>
                  </div>
                </div>

                <div className="volume-info">
                  <p>Total volume affected by lesions: <span className="highlight">{reportData.lesion_volume} mL</span></p>
                </div>
              </div>

              <div className="subsection criteria-section">
                <h4>McDonald Criteria</h4>
                <div className="criteria-cards">
                  <div className="criteria-card">
                    <h5>Dissemination in Space (DIS)*</h5>
                    <p>{reportData.dissemination_space}</p>
                  </div>
                  <div className="criteria-card">
                    <h5>Dissemination in Time (DIT)</h5>
                    {/* <p>{reportData.dissemination_time}</p> */}
                    <p>Not available</p>
                  </div>
                </div>
                <p className="highlight">*Intracortical, spinal cord, and optic nerve lesions are not assessed. If the criterion is not fulfilled, only white matter lesions are taken into account.</p>
              </div>

              <div className="subsection">
                <h4>Atrophy</h4>
                <p>Visually age-appropriate.</p>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
