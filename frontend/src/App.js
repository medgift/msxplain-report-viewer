import React from "react";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import ReportPage from "./ReportPage";  // Page with report and button
import Viewer from "./Viewer"; // Page with 3D image navigation

const App = () => {
  return (
    <Router>
      <Routes>
        {/* Default page showing the report */}
        <Route path="/" element={<ReportPage />} />
        {/* Page showing 3D image slices */}
        <Route path="/Viewer" element={<Viewer />} />
      </Routes>
    </Router>
  );
};


export default App;

// import React from 'react';
// import { BrowserRouter as Router, Route, Routes, Link } from 'react-router-dom';
// import ReportPage from './ReportPage';

// const OHIFViewer = () => {
//   window.location.href = 'http://localhost:3000'; // Redirect to OHIF
//   return null;
// };

// function App() {
//   return (
//     <Router>
//       <Routes>
//         <Route path="/" element={<ReportPage />} />
//         <Route path="/dicom-viewer" element={<OHIFViewer />} />
//       </Routes>
//     </Router>
//   );
// }

// export default App;