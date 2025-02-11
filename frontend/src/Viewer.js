import React, { useState, useEffect, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import './styles.css';

const ThreeDImagePage = () => {
  const { patient_name } = useParams(); // Obtener patient_name de los parámetros de la URL
  const [sliceNum, setSliceNum] = useState(0);
  const [displayedSlice, setDisplayedSlice] = useState(0);
  const [imageData, setImageData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [maxSlice, setMaxSlice] = useState(255);
  const [showFalsePositives, setShowFalsePositives] = useState(false);
  const [lesionCounts, setLesionCounts] = useState(null);
  const [isMouseOverImage, setIsMouseOverImage] = useState(false);

  // Fetch total lesions info on component mount
  useEffect(() => {
    const fetchTotalLesions = async () => {
      try {
        const response = await axios.get(`http://127.0.0.1:5000/api/total_lesions/${patient_name}`);
        setLesionCounts(response.data);
      } catch (error) {
        console.error("Error fetching lesion info:", error);
      }
    };
    fetchTotalLesions();
  }, [patient_name]);

  // Color mapping for the legend - matching backend colors exactly
  const lesionColors = {
    'Deep White Matter': '#FF0000',             // Red
    'Juxtacortical': '#00FF00',  // Green
    'Periventricular': '#0000FF',// Blue
    'Infratentorial': '#FFFF00', // Yellow
    'False Positive': '#808080'  // Gray - match Excel naming
  };

  const renderLesionInfo = () => {
    if (!lesionCounts) return null;

    if (showFalsePositives) {
      // Only show false positives when in false positive mode
      return (
        <div className="lesion-legend">
          <div className="legend-item">
            <div 
              className="color-circle" 
              style={{ backgroundColor: lesionColors['False positive'] }}
            ></div>
            <span>False positive: {lesionCounts.false_positives}</span>
          </div>
        </div>
      );
    }

    // Show true lesions count and types (excluding false positives)
    return (
      <div className="lesion-legend">
        <div className="legend-total">True Lesions: {lesionCounts.true_lesions}</div>
        {Object.entries(lesionCounts.lesion_types)
          .filter(([type]) => type !== 'False positive')
          .map(([type, count]) => (
            <div key={type} className="legend-item">
              <div 
                className="color-circle" 
                style={{ backgroundColor: lesionColors[type] }}
              ></div>
              <span>{type}: {count}</span>
            </div>
          ))}
      </div>
    );
  };

  const debouncedFetchSlice = useCallback(
    (() => {
      let timeoutId = null;
      return (sliceNumber) => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        timeoutId = setTimeout(async () => {
          setLoading(true);
          try {
            const response = await axios.get(
              `http://127.0.0.1:5000/api/slice/${patient_name}/${sliceNumber}`,
              {
                params: { show_false_positives: showFalsePositives },
                responseType: 'arraybuffer'
              }
            );
            
            // Update max slice number from headers if available
            const totalSlices = response.headers['x-total-slices'];
            if (totalSlices) {
              setMaxSlice(parseInt(totalSlices) - 1);
            }
            
            const base64 = btoa(
              new Uint8Array(response.data)
                .reduce((data, byte) => data + String.fromCharCode(byte), '')
            );
            
            const imageUrl = `data:image/png;base64,${base64}`;
            setImageData(imageUrl);
            setDisplayedSlice(sliceNumber);  // Actualize the slice displayed
            setError(null);
          } catch (error) {
            console.error("Error loading slice:", error);
            setError("Could not load the image. Please try again.");
          } finally {
            setLoading(false);
          }
        }, 300);
      };
    })(),
    [showFalsePositives, patient_name]
  );

  // Effect to load the image when sliceNum changes
  useEffect(() => {
    debouncedFetchSlice(sliceNum);
  }, [sliceNum, debouncedFetchSlice]);

  const handleWheel = (event) => {
    if (isMouseOverImage) {
      event.preventDefault(); // Prevent page scroll
      // Determine the direction of the scroll
      const direction = event.deltaY > 0 ? 1 : -1;
      // Compute the new slice number
      setSliceNum((prevSlice) => {
        const newSlice = prevSlice + direction;
        // Ensure the value is within the limits
        if (newSlice < 0) return 0;
        if (newSlice > maxSlice) return maxSlice;
        return newSlice;
      });
    }
  };

  useEffect(() => {
    const handleScroll = (event) => {
      if (isMouseOverImage) {
        event.preventDefault();
      }
    };

    window.addEventListener('wheel', handleScroll, { passive: false });

    return () => {
      window.removeEventListener('wheel', handleScroll);
    };
  }, [isMouseOverImage]);

  return (
    <div className="viewer-container">
      <div className="navigation-bar">
        <Link to={`/report/${patient_name}`} className="back-button">
          Back to Report
        </Link>
      </div>
      
      <header className="viewer-header">
        <h1>Brain Slice Viewer</h1>
        <div className="viewer-controls">
          <button 
            className={`toggle-button ${showFalsePositives ? 'active' : ''}`}
            onClick={() => setShowFalsePositives(!showFalsePositives)}
          >
            {showFalsePositives ? 'Show True Lesions' : 'Show False Positives'}
          </button>
          {renderLesionInfo()}
        </div>
      </header>
      
      <div 
        className="image-container" 
        onWheel={handleWheel}
        onMouseEnter={() => setIsMouseOverImage(true)}
        onMouseLeave={() => setIsMouseOverImage(false)}
      >
        {error && <p className="error-message">{error}</p>}
        {loading ? (
          <div className="loading-container">
            <p>Loading slice {sliceNum}...</p>
          </div>
        ) : (
          imageData && (
            <div className="image-wrapper">
              <img
                src={imageData}
                alt={`Brain slice ${displayedSlice}`}
                className="brain-slice-image"
              />
            </div>
          )
        )}
      </div>
      
      <div className="controls">
        <input
          type="range"
          min="0"
          max={maxSlice}
          value={sliceNum}
          onChange={(e) => setSliceNum(parseInt(e.target.value))}
          className="slice-slider"
        />
        <p>Slice: {sliceNum} / {maxSlice}</p>
      </div>
    </div>
  );
};

export default ThreeDImagePage;