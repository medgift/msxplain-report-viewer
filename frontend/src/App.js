import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import InputPage from "./InputPage";    // Page for entering patient name
import ReportPage from "./ReportPage";  // Page with report and button
import Viewer from "./Viewer";           // Page with 3D image navigation
import FileUpload from "./components/FileUpload";
import PatientList from "./PatientList";
import ProcessedRuns from './components/ProcessedRuns';

const App = () => {
  return (
    <Router>
      <Routes>
        {/* Initial page for entering patient name */}
        <Route path="/" element={<InputPage />} />
        <Route path="/upload" element={<FileUpload />} />
        <Route path="/patients" element={<PatientList />} />
        {/* Page showing the report */}
        <Route path="/report/:patient_name" element={<ReportPage />} />
        <Route path="/report/:run_id/:patient_name" element={<ReportPage />} />
        {/* Page showing 3D image slices */}
        <Route path="/viewer/:patient_name" element={<Viewer />} />
        <Route path="/viewer/:run_id/:patient_name" element={<Viewer />} />
        <Route path="/processed-runs" element={<ProcessedRuns />} />
      </Routes>
    </Router>
  );
};

export default App;