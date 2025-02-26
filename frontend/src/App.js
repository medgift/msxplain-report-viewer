import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "./components/HomePage";
import ReportPage from "./components/ReportPage";
import Viewer from "./components/Viewer";
import FileUpload from "./components/FileUpload";
import ProcessedRuns from './components/ProcessedRuns';
import { ProcessingProvider } from './context/ProcessingContext';
import ProcessingStatus from './components/ProcessingStatus';

const App = () => {
  return (
    <ProcessingProvider>
      <Router>
        <Routes>
          {/* Initial page for entering patient name */}
          <Route path="/" element={<HomePage />} />
          <Route path="/upload" element={<FileUpload />} />
          <Route path="/processing" element={<ProcessingStatus />} />
          {/* Page showing the report */}
          <Route path="/report/:patient_name" element={<ReportPage />} />
          <Route path="/report/:run_id/:patient_name" element={<ReportPage />} />
          {/* Page showing 3D image slices */}
          <Route path="/viewer/:patient_name" element={<Viewer />} />
          <Route path="/viewer/:run_id/:patient_name" element={<Viewer />} />
          <Route path="/processed-runs" element={<ProcessedRuns />} />
        </Routes>
      </Router>
    </ProcessingProvider>
  );
};

export default App;