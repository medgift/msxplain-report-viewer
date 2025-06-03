import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "./components/HomePage";
import ReportPage from "./components/ReportPage";
import FileUpload from "./components/FileUpload";
import ProcessedRuns from './components/ProcessedRuns';
import { ProcessingProvider } from './context/ProcessingContext';
import ProcessingStatus from './components/ProcessingStatus';

const App = () => {
  return (
    <ProcessingProvider>
      <Router>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/upload" element={<FileUpload />} />
          <Route path="/processing" element={<ProcessingStatus />} />
          <Route path="/report/:run_id/:patient_name/:session" element={<ReportPage />} />
          <Route path="/processed-runs" element={<ProcessedRuns />} />
        </Routes>
      </Router>
    </ProcessingProvider>
  );
};

export default App;