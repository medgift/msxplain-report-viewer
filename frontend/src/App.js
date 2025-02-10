import React from "react";
import { BrowserRouter as Router, Route, Routes, Navigate } from "react-router-dom";
import ReportPage from "./ReportPage";  // Page with report and button
import ThreeDImagePage from "./Viewer"; // Page with 3D image navigation
import InputPage from "./InputPage";    // Page for entering patient name

const App = () => {
  return (
    <Router>
      <Routes>
        {/* Initial page for entering patient name */}
        <Route path="/" element={<InputPage />} />
        {/* Page showing the report */}
        <Route path="/report/:patient_name" element={<ReportPage />} />
        {/* Page showing 3D image slices */}
        <Route path="/viewer/:patient_name" element={<ThreeDImagePage />} />
        {/* Redirect to the input page if no match is found */}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  );
};

export default App;