import React, { useEffect, useState } from 'react';
import { useProcessing } from '../context/ProcessingContext';
import { Link } from 'react-router-dom';
import { authFetch } from '../api';
import './ProcessingStatus.css';

const ProcessingStatus = () => {
  const { activeRun, setActiveRun, processingStatus, setProcessingStatus } = useProcessing();
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
        const response = await authFetch(`/api/process-status/${activeRun}`);
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

  const getCompletedCount = (patients) => {
    if (!patients) return 0;
    return Object.values(patients).filter(patient => 
      patient?.steps && Object.values(patient.steps).every(step => step === 'completed')
    ).length;
  };

  const getTotalPatients = (processingStatus) => {
    if (!processingStatus) return 0;
    
    // First try to get from total_patients field
    if (typeof processingStatus.total_patients === 'number') {
      console.log('Using total_patients:', processingStatus.total_patients);
      return processingStatus.total_patients;
    }
    
    // Then try to get from patients object
    if (processingStatus.patients) {
      const count = Object.keys(processingStatus.patients).length;
      console.log('Using patients count:', count);
      return count;
    }
    
    return 0;
  };

  const getCurrentlyProcessingPatient = (patients) => {
    if (!patients) return null;
    return Object.entries(patients).find(([_, patient]) => 
      patient?.steps && Object.values(patient.steps).some(step => step === 'processing')
    );
  };

  return (
    <div className="page-container">
      <nav className="navigation-bar">
        <div className="nav-left">
          <Link to="/" className="back-button">← Back to Home</Link>
        </div>
        <div className="nav-center">
          <h2>Processing Status</h2>
        </div>
        <div className="nav-right" />
      </nav>

      <div className="processing-content">
        {error && <div className="error-message">{error}</div>}
        
        {processingStatus?.status === 'inactive' ? (
          <div className="inactive-message">
            <h3>No Active Works</h3>
            <p>There are currently no scans being processed.</p>
            <Link to="/upload" className="action-button">
              Upload New Scans
            </Link>
          </div>
        ) : (
          <div className="processing-container">
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
                <div className="run-container">
                  <div className="run-header">
                    <h2 className="run-id">Run: {activeRun}</h2>
                    <div className="run-progress">
                      <span className="progress-count">
                        {getCompletedCount(processingStatus?.patients || {})}/
                        {getTotalPatients(processingStatus)} Completed
                      </span>
                      <div className="progress-bar">
                        <div 
                          className="progress-fill"
                          style={{ 
                            width: `${(getCompletedCount(processingStatus?.patients || {}) / 
                                     Math.max(getTotalPatients(processingStatus), 1)) * 100}%` 
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {(() => {
                    const processingPatient = getCurrentlyProcessingPatient(processingStatus.patients);
                    if (!processingPatient) return null;

                    const [patientId, status] = processingPatient;
                    return (
                      <div key={patientId} className="patient-card processing">
                        <h3>Processing Patient: {patientId}</h3>
                        <div className="steps-container">
                          {Object.entries(status.steps).map(([step, stepStatus]) => (
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
                    );
                  })()}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ProcessingStatus;