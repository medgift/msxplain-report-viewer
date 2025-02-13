import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import './styles.css';

const PatientList = () => {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchPatients = async () => {
      try {
        const response = await axios.get('http://localhost:5001/api/patients');
        setPatients(response.data);
        setLoading(false);
      } catch (err) {
        setError('Error loading patients');
        setLoading(false);
      }
    };

    fetchPatients();
  }, []);

  if (loading) return <div className="loading">Loading patients...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="patient-list-container">
      <div className="navigation-bar">
        <Link to="/" className="back-button">
          Back to Home
        </Link>
      </div>
      
      <h1>Patient Reports</h1>
      
      {patients.length === 0 ? (
        <p>No patient reports available.</p>
      ) : (
        <div className="patient-grid">
          {patients.map((patient) => (
            <Link 
              to={`/report/${patient.id}`} 
              key={patient.id}
              className="patient-card"
            >
              <h3>Patient ID: {patient.id}</h3>
              <p>Scan Date: {patient.scan_date}</p>
              <p>Status: {patient.status}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export default PatientList; 