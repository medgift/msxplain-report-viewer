# Multi-stage build using official neuroimaging images
FROM freesurfer/freesurfer:7.4.1 as freesurfer-stage
FROM antsx/ants:2.5.3 as ants-stage

# Main application stage
FROM python:3.8-slim

# Set working directory
WORKDIR /app

# Install system dependencies and neuroimaging tools
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    wget \
    curl \
    unzip \
    git \
    build-essential \
    cmake \
    libeigen3-dev \
    libinsighttoolkit4-dev \
    libfftw3-dev \
    libtiff5-dev \
    libfreetype6-dev \
    pkg-config \
    zlib1g-dev \
    libhdf5-dev \
    libhdf5-cpp-103 \
    libhdf5-103 \
    && rm -rf /var/lib/apt/lists/*

# Install dcm2niix
RUN apt-get update && apt-get install -y dcm2niix && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies BEFORE installing FSL to avoid conflicts
RUN pip install --no-cache-dir -r requirements.txt

# Set HD-BET to use a folder in /app instead of $HOME
ENV HOME=/app
ENV HDBET_PARAMS_FOLDER=/app/hd_bet_params

# Copy pre-downloaded HD-BET models and set them up
COPY hd_bet_models/ /tmp/hd_bet_models/
RUN python -c "\
import HD_BET.utils as utils; \
import shutil; \
import os; \
print('HD-BET parameter folder will be:', utils.folder_with_parameter_files); \
os.makedirs(utils.folder_with_parameter_files, exist_ok=True); \
[shutil.copy2(f'/tmp/hd_bet_models/{i}.model', utils.get_params_fname(i)) and print(f'Model {i} copied successfully') if os.path.exists(f'/tmp/hd_bet_models/{i}.model') else print(f'Warning: /tmp/hd_bet_models/{i}.model not found') for i in range(5)]; \
print('HD-BET models setup complete')" && rm -rf /tmp/hd_bet_models/

# Install FSL
RUN wget -q https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/releases/fslinstaller.py \
    && python fslinstaller.py -d /usr/share/fsl -V 6.0.7.4 \
    && rm fslinstaller.py

# Set FSL environment variables after installation
# Note: FSL installs to /usr/share/fsl/ directly, not /usr/share/fsl/6.0/
ENV FSLDIR="/usr/share/fsl"
ENV FSLOUTPUTTYPE="NIFTI_GZ"
ENV PATH="${FSLDIR}/bin:${PATH}"

# Copy ANTs from official image instead of building from source
ENV ANTSPATH="/opt/ants/bin"
ENV PATH="${ANTSPATH}:${PATH}"
COPY --from=ants-stage /opt/ants /opt/ants

# Copy ANTs libraries to system library path so they can be found
RUN cp -r /opt/ants/lib/* /usr/local/lib/ 2>/dev/null || true && \
    ldconfig


# Copy FreeSurfer from official image (correct path: /usr/local/freesurfer)
ENV FREESURFER_HOME="/usr/local/freesurfer"
ENV PATH="${FREESURFER_HOME}/bin:${PATH}"
COPY --from=freesurfer-stage /usr/local/freesurfer /usr/local/freesurfer

# Install elastix from package manager instead of binary download
# RUN apt-get update && apt-get install -y \
#     elastix \
#     && rm -rf /var/lib/apt/lists/*

# Copy the application code
COPY . .

# Verify tools are accessible (before switching to non-root user)
RUN echo "Verifying PATH: $PATH" && \
    echo "Checking fslorient..." && which fslorient && echo "✓ fslorient found" || echo "✗ fslorient NOT FOUND" && \
    echo "Checking antsRegistration..." && which antsRegistration && echo "✓ antsRegistration found" || echo "✗ antsRegistration NOT FOUND" && \
    echo "Checking mri_convert..." && which mri_convert && echo "✓ mri_convert found" || echo "✗ mri_convert NOT FOUND" && \
    echo "Checking for FSL in common locations..." && ls -la /usr/share/fsl/ 2>/dev/null || echo "FSL directory not found"

# Set up FreeSurfer license
COPY secrets/license.txt ${FREESURFER_HOME}/license.txt

# Create a non-root user to run the application
RUN groupadd -r msxplain && useradd -r -g msxplain -u 1000 msxplain

# Change ownership of app directory and files to non-root user
RUN chown -R msxplain:msxplain /app

# Switch to non-root user
USER msxplain

# Expose port
EXPOSE 5000

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
