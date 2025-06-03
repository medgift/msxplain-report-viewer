import React, { createContext, useContext, useState } from 'react';

const ProcessingContext = createContext();

export const ProcessingProvider = ({ children }) => {
    const [activeRun, setActiveRun] = useState(null);
    const [processingStatus, setProcessingStatus] = useState(null);

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

export const useProcessing = () => {
    const context = useContext(ProcessingContext);
    if (!context) {
        throw new Error('useProcessing must be used within a ProcessingProvider');
    }
    return context;
};