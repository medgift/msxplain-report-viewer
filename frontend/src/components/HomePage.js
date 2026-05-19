import React from 'react';
import { Link } from 'react-router-dom';
import './HomePage.css';
import logo from '../assets/MSxplainLogo.png';

const HomePage = () => {
  return (
    <div className="home-container">
      <div className="logo-container">
        <img src={logo} alt="MSXplain Logo" className="logo" />
      </div>
      <h1 className="title">Welcome to MSXplain</h1>
      <p className="subtitle">
        Automated MS lesion detection and reporting system
      </p>
      <div className="actions">
        <Link to="/upload" className="home-button primary-button">
          Upload New Scan
        </Link>
        <Link to="/processed-runs" className="home-button secondary-button">
          View Existing Reports
        </Link>
      </div>
    </div>
  );
};

export default HomePage;