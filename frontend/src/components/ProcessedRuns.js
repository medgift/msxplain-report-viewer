import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import './ProcessedRuns.css';

const ProcessedRuns = () => {
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        const response = await axios.get('http://localhost:5000/api/processed-runs');
        setRuns(response.data);
      } catch (error) {
        console.error('Error fetching runs:', error);
        setError('Error loading processed runs');
      }
    };

    fetchRuns();
  }, []);

  const handleViewReport = (runId, patientId) => {
    navigate(`/report/${runId}/${patientId}`);
  };

  const getTotalPatients = (run) => {
    return run.total_patients || run.patients.length;
  };

  const getCompletedCount = (patients) => {
    return patients.filter(patient => patient.status === "Complete").length;
  };

  return (
    <div className="page-container">
      <nav className="navigation-bar">
        <div className="nav-left">
          <Link to="/" className="back-button">← Back to Home</Link>
        </div>
        <div className="nav-center">
          <h2>Processed Runs</h2>
        </div>
        <div className="nav-right" />
      </nav>

      <div className="processed-runs">
        {error && <div className="error-message">{error}</div>}
        
        {runs.map(run => (
          <div key={run.id} className="run-container">
            <div className="run-header">
              <h3>{run.id}</h3>
              <div className="run-progress">
                <span className="progress-count">
                  {getCompletedCount(run.patients)}/{getTotalPatients(run)} Completed
                </span>
                <div className="progress-bar">
                  <div 
                    className="progress-fill"
                    style={{ 
                      width: `${(getCompletedCount(run.patients) / getTotalPatients(run)) * 100}%` 
                    }}
                  />
                </div>
              </div>
              <p className="run-date">Date: {run.date}</p>
            </div>
            
            <div className="patients-grid">
              {run.patients
                .filter(patient => patient.status === "Complete")
                .map(patient => (
                  <div key={patient.id} className="patient-card completed">
                    <h4>Patient: {patient.id}</h4>
                    <p>✅ Completed</p>
                    <button
                      onClick={() => handleViewReport(run.id, patient.id)}
                      className="view-report-button"
                    >
                      View Report
                    </button>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ProcessedRuns;