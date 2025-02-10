import React, { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import './styles.css';

const ReportPage = () => {
  const { patient_name } = useParams(); // Get patient_name from URL parameters
  const [patientName, setPatientName] = useState(patient_name || ''); // Initialize state with patient_name from URL or empty string
  const [reportData, setReportData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (patient_name) {
      setLoading(true);
      setError(null); // Clear previous error
      fetch(`http://127.0.0.1:5000/api/report/${patient_name}`)
        .then((response) => response.json())
        .then((data) => {
          if (data.error) {
            setError(data.error); // Handle error from backend
          } else {
            setReportData(data); // Set the summary data
          }
          setLoading(false); // Set loading to false after data is fetched
        })
        .catch((err) => {
          setError('Error connecting to the server'); // Handle network errors
          setLoading(false);
        });
    }
  }, [patient_name]);

  const openMcDonaldCriteria = () => {
    window.open('/files/2017-McDonald-Criteria-PDF.pdf', '_blank');
  };

  return (
    <div className="report-container">
      <header className="report-header">
        <h1>MSXplain Report</h1>
        <div className="header-actions">
          <Link to={`/viewer/${patient_name}`} className="view-3d-button">
            View 3D Image
          </Link>
          <button 
            onClick={openMcDonaldCriteria} 
            className="action-button criteria-button"
          >
            McDonald Criteria
          </button>
        </div>
      </header>

      <div className="patient-input">
        <textarea
          value={patientName}
          onChange={(e) => setPatientName(e.target.value)}
          placeholder="Enter patient name"
        />
        <button onClick={() => navigate(`/report/${patientName}`)}>Load Report</button>
      </div>

      {loading && (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading report...</p>
        </div>
      )}

      {error && <div className="error-message">{error}</div>}

      {reportData && (
        <div className="report-content">
          <section className="report-section">
            <div className="patient-info">
              <p><strong>Patient Name:</strong> {reportData.patient_name}</p>
              <p><strong>Patient ID:</strong> {reportData.patient_id}</p>
              <p><strong>Birth Date:</strong> {reportData.patient_birth_date}</p>
              <p><strong>Sex:</strong> {reportData.patient_sex}</p>
            </div>
            
            <h2>Diagnosis</h2>
            
            <div className="subsection">
              <h3>Technique</h3>
              <p>T1 Mprage and FLAIR</p>
            </div>

            <div className="subsection findings-section">
              <h3>Findings</h3>
              <p className="highlight">False positives of MSXplain: {reportData.lesions.false_positive}</p>
              
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
                  <h4>White Matter</h4>
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
  );
};

export default ReportPage;
