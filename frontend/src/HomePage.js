import React from 'react';
import { Link } from 'react-router-dom';
import './styles.css';

const HomePage = () => {
  return (
    <div>
      <div className="app-header">
        <h1>MSXplain</h1>
      </div>
      <div className="input-container">
        <h2>Report Provider and Automatic Segmentation</h2>
        <div className="button-container">
          <Link to="/upload" className="action-button">
            Upload New Patient Scans
          </Link>
          <Link to="/processed-runs" className="action-button">
            View Existing Reports
          </Link>
        </div>
      </div>
    </div>
  );
};

export default HomePage;