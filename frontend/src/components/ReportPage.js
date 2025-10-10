import React, { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
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
      fetch(`http://127.0.0.1:5000/api/report/${run_id}/${patient_name}/${session}`)  // Add session to API call
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
    window.open('/files/2017-McDonald-Criteria-PDF.pdf', '_blank');
  };

  const openOHIFViewer = () => {
    // Check if we have the StudyInstanceUID from the report data
    if (reportData && reportData.study_instance_uid) {
      // Use the server's IP or hostname instead of localhost
      const OHIF_URL = 'http://10.130.2.34:8042/ohif/';
      const viewerUrl = `${OHIF_URL}viewer?StudyInstanceUIDs=${reportData.study_instance_uid}`;
      // Open in new tab with security attributes
      window.open(viewerUrl, '_blank', 'noopener,noreferrer');
    } else {
      // Fallback to OHIF home page if no StudyInstanceUID is available
      const OHIF_URL = 'http://10.130.2.34:8042/ohif/';
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
              
              <h2>Automated Analysis</h2>
              
              <div className="subsection">
                <h3>Technique</h3>
                <p>T1 Mprage and FLAIR</p>
              </div>

              <div className="subsection findings-section">
                <h3>Findings</h3>
                {/* <p className="highlight">False positives of MSXplain: {reportData.lesions.false_positive}</p> */}
                
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
                    <h5>Dissemination in Space (DIS)</h5>
                    <p>{reportData.dissemination_space}</p>
                  </div>
                  <div className="criteria-card">
                    <h5>Dissemination in Time (DIT)</h5>
                    {/* <p>{reportData.dissemination_time}</p> */}
                    <p>Not available</p>
                  </div>
                </div>
              </div>

              <div className="subsection">
                <h4>Atrophy</h4>
                <p>Visually age-appropriate.</p>
              </div>

              <div className="subsection">
                <h4>Other abnormalities</h4>
                <p>None</p>
              </div>
            </section>

            <section className="report-section">
              <h3>Assessment</h3>
              <ul className="assessment-list">
                <li>The number and distribution of lesions are consistent with an inflammatory CNS disease.</li>
                <li>Spatial dissemination according to McDonald criteria 2017 is fulfilled.</li>
                <li>Temporal dissemination according to McDonald criteria 2017 is fulfilled.</li>
              </ul>
            </section>

            <section className="report-section">
              <h2>Follow-up</h2>
              
              <div className="subsection">
                <h3>Technique</h3>
                <p>Siemens Avanto FIT 1.5T.</p>
                <p>Previous images described.</p>
              </div>

              <div className="subsection">
                <h3>Findings</h3>
                <p>There are no previous examinations available for comparison.</p>
              </div>

              <div className="subsection">
                <h3>Assessment</h3>
                <ul className="assessment-list">
                  <li>Known MS with moderate lesion load.</li>
                  <li>Stable progression compared to the last follow-up, with no new T2 lesions.</li>
                  <li>No contrast-enhancing lesions.</li>
                </ul>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
