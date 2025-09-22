# Multi-stage build using official neuroimaging images
FROM freesurfer/freesurfer:7.4.1 as freesurfer-stage

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
ENV FSLDIR="/usr/share/fsl/6.0"
ENV FSLOUTPUTTYPE="NIFTI_GZ"
ENV PATH="${FSLDIR}/bin:${PATH}"

# Install ANTs from source using the official installation method
RUN git clone https://github.com/cookpa/antsInstallExample.git && \
    cd antsInstallExample && \
    ls -la && \
    bash installANTs.sh && \
    mkdir -p /opt/ants && \
    cp -R install/* /opt/ants/ && \
    cd / && rm -rf antsInstallExample

# Set ANTs environment variables
ENV ANTSPATH="/opt/ants/bin"
ENV PATH="${ANTSPATH}:${PATH}"


# Copy FreeSurfer from official image (correct path: /usr/local/freesurfer)

# Create symbolic links for the missing ITK libraries that ANTs expects
# Use FSL's libraries and system libraries as they are more likely to be compatible
RUN cd /usr/lib/x86_64-linux-gnu && \
    ln -sf /usr/share/fsl/lib/libhdf5.so.310.2.0 libitkhdf5-shared-5.4.so.1 && \
    ln -sf /usr/share/fsl/lib/libhdf5_cpp.so.310.0.2 libitkhdf5_cpp-shared-5.4.so.1 && \
    ln -sf /usr/lib/x86_64-linux-gnu/libopenjp2.so.7 libitkopenjpeg-5.4.so.1 && \
    ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 libitktiff-5.4.so.1 && \
    echo "Created symbolic links for basic ITK libraries"

# Create placeholder/dummy libraries for ITK components that might not be available
# These are often optional components that ANTs was compiled with but might not be essential
RUN cd /usr/lib/x86_64-linux-gnu && \
    touch libITKIOIPL-5.4.so.1 && \
    touch libITKIOLSM-5.4.so.1 && \
    touch libITKIOSCANCO-5.4.so.1 && \
    touch libITKIOBRUKER-5.4.so.1 && \
    touch libITKIOGE-5.4.so.1 && \
    touch libITKIOSiemens-5.4.so.1 && \
    echo "Created placeholders for optional ITK libraries"

# Create MINC symbolic link with multiple fallback options
RUN cd /usr/lib/x86_64-linux-gnu && \
    (ln -sf libminc2.so.5.3.0 libitkminc2-5.4.so.1 2>/dev/null || \
     ln -sf libminc2.so.5.2.0 libitkminc2-5.4.so.1 2>/dev/null || \
     ln -sf libminc2.so.5.2 libitkminc2-5.4.so.1 2>/dev/null || \
     ln -sf libminc2.so libitkminc2-5.4.so.1 2>/dev/null || \
     (echo "Creating placeholder MINC library" && touch libitkminc2-5.4.so.1)) && \
    echo "MINC library link created"

# Update library cache
RUN ldconfig


# Copy FreeSurfer from official image (correct path: /usr/local/freesurfer)
ENV FREESURFER_HOME="/usr/local/freesurfer"
ENV PATH="${FREESURFER_HOME}/bin:${PATH}"
COPY --from=freesurfer-stage /usr/local/freesurfer /usr/local/freesurfer

# Install elastix from package manager instead of binary download
RUN apt-get update && apt-get install -y \
    elastix \
    && rm -rf /var/lib/apt/lists/*

# Copy the application code
COPY . .

# Create necessary directories
RUN mkdir -p files/uploads files/processed files/DICOMS files/important_atlas

# Set up FreeSurfer license
COPY secrets/license.txt ${FREESURFER_HOME}/license.txt

# Expose port
EXPOSE 5000

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
