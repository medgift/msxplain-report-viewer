import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useProcessing } from '../context/ProcessingContext';
import { useNavigate } from 'react-router-dom';
import './FileUpload.css';

const FileUpload = () => {
    const [selectedFolder, setSelectedFolder] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadComplete, setUploadComplete] = useState(false);
const [runId, setRunId] = useState(null);
  const { setActiveRun, setProcessingStatus } = useProcessing();
  const navigate = useNavigate();
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentRunId, setCurrentRunId] = useState(null);
  const [error, setError] = useState(null); // Add this line
  const BATCH_SIZE = 100; // Number of files per batch

  const handleFolderSelect = (event) => {
    const files = Array.from(event.target.files);
    console.log(`Selected ${files.length} files`);
    setSelectedFolder(files);
  };

  const uploadBatch = async (batch, formData, runId) => {
    let url = '/api/upload-dicoms';
    if (runId) {
      url += `?run_id=${runId}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }
    
    return await response.json();
  };

  const handleUpload = async () => {
    if (!selectedFolder) return;

    setUploading(true);
    setUploadProgress(0);
    let batchRunId = null;
    
    try {
      const totalFiles = selectedFolder.length;
      let processedFiles = 0;
      let currentBatch = [];
      let lastResponse = null;

      for (let i = 0; i < totalFiles; i++) {
        currentBatch.push(selectedFolder[i]);
        
        if (currentBatch.length === BATCH_SIZE || i === totalFiles - 1) {
          const formData = new FormData();
          currentBatch.forEach(file => formData.append('files', file));
          
          // Use the run_id from the first batch for all subsequent batches
          lastResponse = await uploadBatch(currentBatch, formData, batchRunId);
          if (lastResponse.error) {
            throw new Error(lastResponse.error);
          }

          // Store run ID from first batch
          if (!batchRunId && lastResponse.run_id) {
            batchRunId = lastResponse.run_id;
            setCurrentRunId(batchRunId);
          }

          processedFiles += currentBatch.length;
          setUploadProgress(Math.round((processedFiles / totalFiles) * 100));
          currentBatch = [];
        }
      }

      setRunId(lastResponse.run_id);
      setUploadComplete(true);
      
    } catch (error) {
      console.error('Upload error:', error);
    } finally {
      setUploading(false);
    }
  };

  const handleStartProcessing = async () => {
    try {
        console.log('Starting processing for runId:', runId);
        setUploading(true);
        
        // Set active run in context and localStorage
        setActiveRun(runId);
        localStorage.setItem('activeRun', runId);
        
        const response = await fetch(`/api/process-scans/${runId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });      

        if (!response.ok) {
            throw new Error(`Processing failed: ${response.statusText}`);
        }

        const data = await response.json();
        if (data.error) {
            throw new Error(data.error);
        }

        // Initialize processing status
        setProcessingStatus({
            status: 'processing',
            total_patients: data.total_patients,
            patients: {}
        });

        // Store metadata
        localStorage.setItem('totalPatients', data.total_patients);
        localStorage.setItem('processingStartTime', Date.now().toString());
        
        // Navigate to processing status page
        navigate('/processing');

    } catch (error) {
        console.error('Processing error:', error);
        setError(error.message);
    } finally {
        setUploading(false);
    }
};

  return (
    <div className="page-container">
      <nav className="navigation-bar">
        <div className="nav-left">
          <Link to="/" className="back-button">← Back to Home</Link>
        </div>
        <div className="nav-center">
          <h2>Upload Patient Data</h2>
        </div>
        <div className="nav-right">
          <Link to="/processing" className="view-status-button">
            View Processing Status
          </Link>
        </div>
      </nav>

      <div className="upload-container">
        {error && ( // Add this error display
            <div className="error-message">
                {error}
            </div>
        )}
        <div className="upload-header">
          <p className="upload-instructions">
            Select a folder containing patient data. Supports large folders with multiple files.
          </p>
        </div>
        
        <div className="upload-controls">
          <input
            type="file"
            webkitdirectory="true"
            directory="true"
            onChange={handleFolderSelect}
            className="file-input"
            disabled={uploading}
            multiple
          />
          <button
            onClick={handleUpload}
            disabled={uploading || !selectedFolder}
            className="upload-button"
          >
            {uploading ? `Uploading... ${uploadProgress}%` : 'Upload Folder'}
          </button>

          {uploading && (
            <div className="progress-bar">
              <div 
                className="progress-fill"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}

          {uploadComplete && (
            <button
              onClick={handleStartProcessing}
              className="process-button"
            >
              Process Scans
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default FileUpload;