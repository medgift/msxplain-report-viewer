import React, { createContext, useState, useContext, useEffect } from 'react';

const ProcessingContext = createContext();

export const ProcessingProvider = ({ children }) => {
  const [activeRun, setActiveRun] = useState(() => {
    return localStorage.getItem('activeRun') || null;
  });
  const [processingStatus, setProcessingStatus] = useState({});

  useEffect(() => {
    if (activeRun) {
      localStorage.setItem('activeRun', activeRun);
    } else {
      localStorage.removeItem('activeRun');
    }
  }, [activeRun]);

  return (
    <ProcessingContext.Provider 
      value={{ 
        activeRun, 
        setActiveRun, 
        processingStatus, 
        setProcessingStatus 
      }}
    >
      {children}
    </ProcessingContext.Provider>
  );
};

export const useProcessing = () => useContext(ProcessingContext);