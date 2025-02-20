import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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

  return (
    <div className="processed-runs">
      <h2>Processed Runs</h2>
      
      {error && <div className="error-message">{error}</div>}
      
      {runs.map(run => (
        <div key={run.id} className="run-container">
          <h3>Run: {run.id}</h3>
          <p>Date: {run.date}</p>
          
          <div className="patients-grid">
            {run.patients.map(patient => (
              <div key={patient.id} className="patient-card">
                <h4>Patient: {patient.id}</h4>
                <p>Status: {patient.status}</p>
                {patient.status === "Complete" && (
                  <button
                    onClick={() => handleViewReport(run.id, patient.id)}
                    className="view-report-button"
                  >
                    View Report
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ProcessedRuns;