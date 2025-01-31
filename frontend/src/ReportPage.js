import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import './styles.css';

const App = () => {
  const [summary, setSummary] = useState(null); // For summary statistics
  const [error, setError] = useState(null); // For error handling
  const [loading, setLoading] = useState(true);
  const openOHIFViewer = () => {
    // URL for the DICOMWeb server (Orthanc)
    const dicomWebUrl = "http://localhost:8042/dicom-web/";
    
    // Create URL to OHIF viewer with the DICOMWeb URL
    const ohifUrl = `http://localhost:3000/viewer?dicomWeb=${dicomWebUrl}`;

    // Open the OHIF Viewer in a new tab
    window.open(ohifUrl, "_blank");
  };

  useEffect(() => {
    // Fetch the pre-processed report from the backend
    fetch('http://127.0.0.1:5000/api/report')
      .then((response) => response.json())
      .then((json) => {
        if (json.error) {
          setError(json.error); // Handle error from backend
        } else {
          setSummary(json); // Set the summary data
        }
      })
      .catch((err) => {
        setError('Error connecting to the server'); // Handle network errors
      });
  }, []);

  if (loading) return <p>Loading...</p>;

  return (
    <div>
      <h1>MSXplain Report Provider</h1>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      {summary && (
        <div>
          <h2>Report Summary</h2>
          <h3>Counts by Lesion Type:</h3>
          <ul>
            {Object.entries(summary.counts_by_lesion_type).map(([type, count]) => (
              <li key={type}>
                {type}: {count}
              </li>
            ))}
          </ul>
          <p>Total Voxels Affected: {summary.total_voxels_affected}</p>
          <p>Total Lesion Volume: {summary.total_lesion_volume}</p>
        </div>
      )}

       {/* Button to navigate to the 3D image viewer */}
       <button onClick={openOHIFViewer}>View 3D DICOM in OHIF</button>
    </div>
  );
};

export default App;
