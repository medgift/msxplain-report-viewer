import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "./HomePage";    // Page for entering patient name
import ReportPage from "./ReportPage";  // Page with report and button
import Viewer from "./Viewer";           // Page with 3D image navigation
import FileUpload from "./components/FileUpload";
import PatientList from "./PatientList";
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
          <Route path="/patients" element={<PatientList />} />
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