import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './FileUpload.css';
import { Progress, Button } from 'antd';

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

  const getProgressPercent = (step) => {
    if (!step) return 0;
    switch (step) {
      case 'pending': return 0;
      case 'processing': return 50;
      case 'completed': return 100;
      default: return 0;
    }
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
          const allCompleted = Object.values(data.patients).every(
            patient => patient.status === 'completed' || patient.status === 'error'
          );
          
          if (allCompleted) {
            setProcessing(false);
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
    Array.from(selectedFolder).forEach(file => {
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
      setProcessingStatus(data);
    } catch (error) {
      console.error('Error starting processing:', error);
      setProcessing(false);
    }
  };

  const handleViewReport = () => {
    // Implement report viewing logic here
    window.open(`/api/view-report/${runId}`, '_blank');
  };

  return (
    <div className="upload-container">
      <div className="upload-header">
        <h2>Upload Patient Data</h2>
        <p className="upload-instructions">
          Select a folder containing patient data. Each patient folder should contain session folders with 'flair' and 't1' subfolders.
        </p>
      </div>
      
      <div className="upload-controls">
        <input
          type="file"
          webkitdirectory="true"
          directory="true"
          onChange={handleFolderSelect}
          className="file-input"
        />
        <button
          onClick={handleUpload}
          disabled={uploading || !selectedFolder}
          className="upload-button"
        >
          {uploading ? 'Uploading...' : 'Upload Folder'}
        </button>
        {uploadComplete && (
          <button
            onClick={handleProcess}
            disabled={processing}
            className="process-button"
          >
            {processing ? 'Processing...' : 'Process Files'}
          </button>
        )}
      </div>

      {error && <div className="error-message">{error}</div>}

      {runId && Object.entries(processingStatus.patients || {}).map(([patientId, status]) => (
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

      {runId && (
        <Button
          type="primary"
          onClick={handleViewReport}
          style={{ marginTop: '10px' }}
        >
          View Report
        </Button>
      )}
    </div>
  );
};

export default FileUpload; 