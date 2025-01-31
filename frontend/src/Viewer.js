import React, { useState, useEffect } from "react";
import axios from "axios";
import './styles.css';

const ThreeDImagePage = () => {
  const [sliceNum, setSliceNum] = useState(0);
  const [imageData, setImageData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchSlice = async () => {
      try {
        const response = await axios.get(`http://127.0.0.1:5000/api/slice/${sliceNum}`);
        setImageData(response.data.slice);
      } catch (error) {
        console.error("Error fetching slice:", error);
        setError("Failed to load slice. Please try again.");
      }
    };

    fetchSlice();
  }, [sliceNum]);

  {error && <p style={{ color: 'red' }}>{error}</p>}

  const handleSliderChange = (event) => {
    setSliceNum(event.target.value);
  };

  return (
    <div>
      <h1>Brain Image Slice Viewer</h1>
      <div>
        {imageData ? (
          <img
            src={`data:image/png;base64,${btoa(imageData)}`}
            alt="Brain Slice"
            style={{ maxWidth: "100%", height: "auto" }}
          />
        ) : (
          <p>Loading slice...</p>
        )}
      </div>
      <input
        type="range"
        min="0"
        max="100"  // Replace with the actual number of slices
        value={sliceNum}
        onChange={handleSliderChange}
      />
      <p>Slice {sliceNum}</p>
    </div>
  );
};

export default ThreeDImagePage;