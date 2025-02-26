import React from 'react';
import ReactDOM from 'react-dom/client'; // Import from `react-dom/client`
import './styles.css';  // Make sure this is present
import App from './App';

const rootElement = document.getElementById('root');

// Create a root and render the App component
const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);