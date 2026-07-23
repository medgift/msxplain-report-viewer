import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HomePage from "./components/HomePage";
import ReportPage from "./components/ReportPage";
import FileUpload from "./components/FileUpload";
import ProcessedRuns from './components/ProcessedRuns';
import { ProcessingProvider } from './context/ProcessingContext';
import ProcessingStatus from './components/ProcessingStatus';
import Login from './components/Login';
import ProtectedRoute from './components/ProtectedRoute';

const protect = (element) => <ProtectedRoute>{element}</ProtectedRoute>;

const App = () => {
  return (
    <ProcessingProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={protect(<HomePage />)} />
          <Route path="/upload" element={protect(<FileUpload />)} />
          <Route path="/processing" element={protect(<ProcessingStatus />)} />
          <Route
            path="/report/:run_id/:patient_name/:session"
            element={protect(<ReportPage />)}
          />
          <Route path="/processed-runs" element={protect(<ProcessedRuns />)} />
        </Routes>
      </Router>
    </ProcessingProvider>
  );
};

export default App;
