import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useProcessing } from '../context/ProcessingContext';
import './FileUpload.css';

const FileUpload = () => {
    const [selectedFolder, setSelectedFolder] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadComplete, setUploadComplete] = useState(false);
const [runId, setRunId] = useState(null);
  const { setActiveRun } = useProcessing();
  const navigate = useNavigate();

  const handleFolderSelect = (event) => {
        setSelectedFolder(Array.from(event.target.files));
  };

  const handleUpload = async () => {
    if (!selectedFolder) return;

    setUploading(true);
    const formData = new FormData();
    selectedFolder.forEach(file => {
      formData.append('files', file);
    });

    try {
      const response = await fetch('http://localhost:5000/api/upload-dicoms', {
        method: 'POST',
        body: formData
      });
      
      const data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }

      setRunId(data.run_id);
      setUploadComplete(true);
      setUploading(false);
    } catch (error) {
      console.error('Upload error:', error);
      setUploading(false);
    }
  };

  const handleStartProcessing = async () => {
    try {
      console.log('Starting processing for runId:', runId);
      
      // First set the active run before making the API call
      setActiveRun(runId);
      localStorage.setItem('activeRun', runId);
      
      const response = await fetch(`http://localhost:5000/api/process-scans/${runId}`, {
        method: 'POST'
      });      
      const data = await response.json();

      if (data.error) {
        throw new Error(data.error);
      }

      navigate('/processing');
    } catch (error) {
      console.error('Processing error:', error);
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
        <div className="upload-header">
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
            disabled={uploading}
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