import React, { useEffect, useState } from 'react';
import { useProcessing } from '../context/ProcessingContext';
import { Link, useNavigate } from 'react-router-dom';
import './ProcessingStatus.css';

const ProcessingStatus = () => {
  const { activeRun, setActiveRun, processingStatus, setProcessingStatus } = useProcessing();
  const navigate = useNavigate();
  const [error, setError] = useState(null);

  useEffect(() => {
    // If no activeRun in context, try to get it from localStorage
    if (!activeRun) {
      const storedRun = localStorage.getItem('activeRun');
      if (storedRun) {
        setActiveRun(storedRun);
      }
    }
  }, [activeRun, setActiveRun]);

  useEffect(() => {
    let intervalId;

    const fetchStatus = async () => {
      if (!activeRun) return;

      try {
        const response = await fetch(`http://localhost:5000/api/process-status/${activeRun}`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Processing status data:', data);
        setProcessingStatus(data);

        // Check if processing is complete
        const allComplete = Object.values(data.patients).every(patient => 
          Object.values(patient.steps).every(step => step === 'completed')
        );

        if (allComplete) {
          clearInterval(intervalId);
        }
      } catch (error) {
        console.error('Error fetching status:', error);
        setError(error.message);
      }
    };

    if (activeRun) {
      // Initial fetch
      fetchStatus();
      // Start polling
      intervalId = setInterval(fetchStatus, 3000);
    }

    // Cleanup
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [activeRun, setProcessingStatus]);

  // Add console.log to debug render values
  console.log('Current state:', { activeRun, processingStatus });

  return (
    <div className="processing-container">
      <div className="navigation-header">
        <Link to="/upload" className="back-button">← Back to Upload</Link>
        <h2>Processing Status</h2>
      </div>

      {error && (
        <div className="error-message">
          Error: {error}
        </div>
      )}

      {!activeRun && (
        <div className="no-processing">
          <p>No active processing run found.</p>
          <Link to="/upload" className="action-button">Start New Processing</Link>
        </div>
      )}

      {activeRun && processingStatus?.patients && (
        <div className="processing-status">
          {Object.entries(processingStatus.patients).map(([patientId, status]) => (
            <div key={patientId} className="patient-card">
              <h3>Patient: {patientId}</h3>
              <div className="steps-container">
                {Object.entries(status.steps || {}).map(([step, stepStatus]) => (
                  <div key={step} className={`step-status ${stepStatus}`}>
                    <span className="step-label">{step}</span>
                    <span className="step-value">
                      {stepStatus === 'processing' && '⚙️ '}
                      {stepStatus === 'completed' && '✅ '}
                      {stepStatus === 'pending' && '⏳ '}
                      {stepStatus}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ProcessingStatus;