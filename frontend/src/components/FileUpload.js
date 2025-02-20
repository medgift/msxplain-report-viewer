import React, { useState, useEffect } from 'react';
import './FileUpload.css';
import { Progress, Button } from 'antd';
import { useNavigate, Link } from 'react-router-dom';

const FileUpload = () => {
  console.log('FileUpload component rendered');
  const [selectedFolder, setSelectedFolder] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [runId, setRunId] = useState(null);
  const [uploadComplete, setUploadComplete] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState({
    patients: {}
  });
  const [progress, setProgress] = useState({});
  const [error, setError] = useState(null);
  const [reportPath, setReportPath] = useState(null);
  const navigate = useNavigate();

  const getProgressPercent = (step) => {
    if (!step) return 0;
    switch (step) {
      case 'pending': return 0;
      case 'processing': return 50;
      case 'completed': return 100;
      default: return 0;
    }
  };

  const isProcessingComplete = () => {
    if (!processingStatus.patients || Object.keys(processingStatus.patients).length === 0) return false;
    
    return Object.values(processingStatus.patients).every(patient => 
      patient.steps &&
      patient.steps.preprocessing === 'completed' &&
      patient.steps.msxplain === 'completed' &&
      patient.steps.report === 'completed'
    );
  };

  const hasProcessingStarted = () => {
    if (!processing || !uploadComplete) return false;
    return Object.values(processingStatus.patients || {}).some(patient => 
      patient.steps && Object.values(patient.steps).some(step => step === 'completed')
    );
  };

  useEffect(() => {
    let intervalId;
    if (runId && processing) {
      intervalId = setInterval(async () => {
        try {
          const response = await fetch(`http://localhost:5000/api/process-status/${runId}`);
          const data = await response.json();
          setProcessingStatus(data);
          
          // Check if all patients are completed
          const allCompleted = Object.values(data.patients).every(patient => 
            patient.steps &&
            patient.steps.preprocessing === 'completed' &&
            patient.steps.msxplain === 'completed' &&
            patient.steps.report === 'completed'
          );
          
          if (allCompleted) {
            // Don't set processing to false when complete
            clearInterval(intervalId);
          }
        } catch (error) {
          console.error('Error checking status:', error);
          setProcessing(false);
          clearInterval(intervalId);
        }
      }, 2000);

      return () => {
        if (intervalId) {
          clearInterval(intervalId);
        }
      };
    }
  }, [runId, processing]);

  const handleFolderSelect = (event) => {
    const files = event.target.files;
    setSelectedFolder(files);
    setUploadComplete(false);
  };

  const handleUpload = async () => {
    if (!selectedFolder || selectedFolder.length === 0) return;

    setUploading(true);
    const formData = new FormData();
    
    // Add each file to formData maintaining their relative paths
    const patientFolders = new Set();
    Array.from(selectedFolder).forEach(file => {
      // Extract patient ID from file path (second level folder)
      const pathParts = file.webkitRelativePath.split('/');
      if (pathParts.length > 1) {
        const patientId = pathParts[1]; // Get the patient folder name
        patientFolders.add(patientId);
      }
      formData.append('files', file, file.webkitRelativePath);
    });

    try {
      const response = await fetch('http://localhost:5000/api/upload-dicoms', {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      setRunId(data.run_id);
      
      // Initialize progress status for each patient folder
      const initialStatus = {
        patients: {}
      };
      patientFolders.forEach(patientId => {
        if (patientId) { // Only add if patientId exists
          initialStatus.patients[patientId] = {
            steps: {
              preprocessing: 'pending',
              msxplain: 'pending',
              report: 'pending'
            }
          };
        }
      });
      setProcessingStatus(initialStatus);
      
      setUploadComplete(true);
    } catch (error) {
      console.error('Error uploading:', error);
      setError(error.message);
    } finally {
      setUploading(false);
    }
  };

  const handleProcess = async () => {
    if (!runId) return;

    setProcessing(true);
    try {
      console.log(`Starting processing for run_id: ${runId}`);
      const response = await fetch(`http://localhost:5000/api/process-scans/${runId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Processing started:', data);
      
      // Keep checking status until processing is complete
      const statusCheckInterval = setInterval(async () => {
        try {
          const statusResponse = await fetch(`http://localhost:5000/api/process-status/${runId}`);
          const statusData = await statusResponse.json();
          setProcessingStatus(statusData);

          // Check if all processing is complete
          const allComplete = Object.values(statusData.patients).every(
            patient => patient.steps.preprocessing === 'completed' &&
                      patient.steps.msxplain === 'completed' &&
                      patient.steps.report === 'completed'
          );

          if (allComplete) {
            clearInterval(statusCheckInterval);
            // Keep processing true to maintain the completion message
            // Don't reset processing status
          }
        } catch (error) {
          console.error('Error checking status:', error);
          clearInterval(statusCheckInterval);
          setError('Error checking processing status');
          setProcessing(false);
        }
      }, 2000);

    } catch (error) {
      console.error('Error starting processing:', error);
      setProcessing(false);
      setError(error.message);
    }
  };

  const handleViewReport = () => {
        navigate('/processed-runs');
  };

  return (
    <div className="upload-container">
      <div className="navigation-header">
        <Link to="/" className="back-button">← Back to Home</Link>
        <h2>Upload Patient Data</h2>
      </div>
      <div className="upload-header">
        <h2>Upload Patient Data</h2>
        <p className="upload-instructions">
          Select a folder containing patient data. Each patient folder should contain session folders with 'flair' and 't1' subfolders.
        </p>
      </div>
      
      {(!processing || !isProcessingComplete()) && (
        <div className="upload-controls">
          <input
            type="file"
            webkitdirectory="true"
            directory="true"
            onChange={handleFolderSelect}
            className="file-input"
            disabled={processing}
          />
          <button
            onClick={handleUpload}
            disabled={uploading || !selectedFolder || processing}
            className="upload-button"
          >
            {uploading ? 'Uploading...' : 'Upload Folder'}
          </button>
          {uploadComplete && !processing && (
            <button
              onClick={handleProcess}
              disabled={processing}
              className="process-button"
            >
              Process Files
            </button>
          )}
        </div>
      )}

      {error && <div className="error-message">{error}</div>}

      {processing && !isProcessingComplete() && Object.entries(processingStatus.patients || {}).map(([patientId, status]) => (
        <div key={patientId} className="patient-container">
          <div className="patient-header">
            <h3>Patient: {patientId}</h3>
          </div>
          
          {status && status.steps && (
            <>
              <div className="progress-section">
                <div className="progress-label">Preprocessing:</div>
                <div className="progress-bar-container">
                  <div 
                    className={`progress-bar ${status.steps.preprocessing === 'error' ? 'error' : 'success'}`}
                    style={{width: `${getProgressPercent(status.steps.preprocessing)}%`}}
                  />
                </div>
              </div>

              <div className="progress-section">
                <div className="progress-label">MSXplain Analysis:</div>
                <div className="progress-bar-container">
                  <div 
                    className={`progress-bar ${status.steps.msxplain === 'error' ? 'error' : 'success'}`}
                    style={{width: `${getProgressPercent(status.steps.msxplain)}%`}}
                  />
                </div>
              </div>

              <div className="progress-section">
                <div className="progress-label">Report Generation:</div>
                <div className="progress-bar-container">
                  <div 
                    className={`progress-bar ${status.steps.report === 'error' ? 'error' : 'success'}`}
                    style={{width: `${getProgressPercent(status.steps.report)}%`}}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      ))}

      {processing && isProcessingComplete() && (
        <div className="completion-message">
          <p>Processing completed successfully!</p>
          <Button
            type="primary"
            onClick={handleViewReport}
            style={{ marginTop: '10px' }}
          >
            View Report
          </Button>
        </div>
      )}
    </div>
  );
};

export default FileUpload;