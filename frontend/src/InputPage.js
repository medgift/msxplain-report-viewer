import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './styles.css';

const InputPage = () => {
  const [patientName, setPatientName] = useState('');
  const navigate = useNavigate();

  const handleButtonClick = () => {
    if (patientName) {
      navigate(`/report/${patientName}`);
    }
  };

  return (
    <div className="input-container">
      <header className="report-header">
        <h1>MSXplain Report</h1>
      </header>
      <div className="patient-input">
        <textarea
          value={patientName}
          onChange={(e) => setPatientName(e.target.value)}
          placeholder="Enter patient name"
        />
        <button onClick={handleButtonClick}>Load Report</button>
      </div>
    </div>
  );
};

export default InputPage;