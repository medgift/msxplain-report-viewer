import React from 'react';
import { Link } from 'react-router-dom';
import './styles.css';

const InputPage = () => {
  return (
    <div className="input-container">
      <h1>MS Lesion Detection</h1>
      <div className="button-container">
        <Link to="/upload" className="action-button">
          Upload New Patient Scans
        </Link>
        <Link to="/patients" className="action-button">
          View Existing Reports
        </Link>
      </div>
    </div>
  );
};

export default InputPage;