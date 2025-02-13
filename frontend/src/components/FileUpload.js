import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './FileUpload.css';

const FileUpload = () => {
  const [folders, setFolders] = useState({
    flair: null,
    t1: null
  });
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState({});
  const [error, setError] = useState(null);

  const handleFolderSelect = (event, type) => {
    const files = Array.from(event.target.files);
    if (files.length > 0) {
      setFolders(prev => ({
        ...prev,
        [type]: files
      }));
      setError(null);
    }
  };

  const validateFiles = () => {
    if (!folders.flair || !folders.t1) {
      setError('Please select both FLAIR and T1 DICOM folders');
      return false;
    }
    return true;
  };

  const handleUpload = async () => {
    if (!validateFiles()) return;

    try {
      setUploading(true);
      setError(null);

      // Create FormData with both folders
      const formData = new FormData();
      
      // Add FLAIR files
      folders.flair.forEach((file) => {
        formData.append('flair_files', file, `flair/${file.name}`);
      });

      // Add T1 files
      folders.t1.forEach((file) => {
        formData.append('t1_files', file, `t1/${file.name}`);
      });

      const response = await axios.post('http://localhost:5000/api/upload-dicoms', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setProcessing(true);
      const patientId = response.data.patient_id;
      
      // Start polling for status
      const statusInterval = setInterval(async () => {
        try {
          const statusResponse = await axios.get(
            `http://localhost:5000/api/process-status/${patientId}`
          );
          
          setProgress(statusResponse.data);
          
          if (Object.values(statusResponse.data).every(status => status)) {
            clearInterval(statusInterval);
            setProcessing(false);
            window.location.href = `/report/${patientId}`;
          }
        } catch (error) {
          console.error('Error checking status:', error);
        }
      }, 5000);

    } catch (error) {
      setError(error.response?.data?.error || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="upload-container">
      <h2>Upload MRI Scans</h2>
      
      <div className="upload-box">
        <div className="folder-upload">
          <h3>FLAIR Images</h3>
          <input
            type="file"
            webkitdirectory="true"
            directory="true"
            multiple
            onChange={(e) => handleFolderSelect(e, 'flair')}
            disabled={uploading || processing}
          />
          {folders.flair && (
            <div className="file-count">
              {folders.flair.length} files selected
            </div>
          )}
        </div>

        <div className="folder-upload">
          <h3>T1 Images</h3>
          <input
            type="file"
            webkitdirectory="true"
            directory="true"
            multiple
            onChange={(e) => handleFolderSelect(e, 't1')}
            disabled={uploading || processing}
          />
          {folders.t1 && (
            <div className="file-count">
              {folders.t1.length} files selected
            </div>
          )}
        </div>
        
        <button 
          onClick={handleUpload}
          disabled={!folders.flair || !folders.t1 || uploading || processing}
          className="upload-button"
        >
          {uploading ? 'Uploading...' : processing ? 'Processing...' : 'Upload'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {processing && (
        <div className="progress-container">
          <h3>Processing Status:</h3>
          <div className="progress-items">
            <div className={`progress-item ${progress.preprocessing ? 'complete' : ''}`}>
              Preprocessing
            </div>
            <div className={`progress-item ${progress.msxplain ? 'complete' : ''}`}>
              MSXplain Analysis
            </div>
            <div className={`progress-item ${progress.report ? 'complete' : ''}`}>
              Report Generation
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileUpload; 