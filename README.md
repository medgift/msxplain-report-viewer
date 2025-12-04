# react_report

v1.0: First approach to create the report from the results of MSReport-Provider and a Viewer with the axial plane with the lesion map overlapping
v2.0: The system incorporates an uploading Page to upload a folder with more than 1 patient, the structure Folder/Patients/Session/Images(T1 and FLAIR). The folder can be processed using the MSReport provider Pipeline (Preprocessing, MSXplain Report Provider, Report generator).
v3.0: Complete incorporation of Report Provider with skull stripping, updating the model, converting the lesion_map to dicom_seg, and registering to flair space. Start the incorporation of the OHIF Viewer + Orthanc. 


## Docker
For docker this needs to be copied in the before building the image:

backend:
    - msxplain/model/*
    <!-- - config.yml -->
    - secrets/*
    - hd_bet_models/*

frontend:
    - public/*