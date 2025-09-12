# Multi-stage build using official neuroimaging images
FROM antsx/ants:2.6.2 as ants-stage
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
    && rm -rf /var/lib/apt/lists/*

# Install dcm2niix
RUN apt-get update && apt-get install -y dcm2niix && rm -rf /var/lib/apt/lists/*

# Install FSL
ENV FSLDIR="/usr/share/fsl/6.0"
ENV FSLOUTPUTTYPE="NIFTI_GZ"
ENV PATH="${FSLDIR}/bin:${PATH}"
RUN wget -q https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/releases/fslinstaller.py \
    && python fslinstaller.py -d /usr/share/fsl -V 6.0.7.4 \
    && rm fslinstaller.py

# Copy ANTs from official image
ENV ANTSPATH="/opt/ants"
ENV PATH="${ANTSPATH}/bin:${PATH}"
COPY --from=ants-stage /opt/ants /opt/ants

# Copy FreeSurfer from official image (correct path: /usr/local/freesurfer)
ENV FREESURFER_HOME="/usr/local/freesurfer"
ENV PATH="${FREESURFER_HOME}/bin:${PATH}"
COPY --from=freesurfer-stage /usr/local/freesurfer /usr/local/freesurfer

# Install elastix
RUN wget -q https://github.com/SuperElastix/elastix/releases/download/5.0.1/elastix-5.0.1-linux.tar.bz2 \
    && tar -xjf elastix-5.0.1-linux.tar.bz2 \
    && mv elastix-5.0.1-linux /opt/elastix \
    && rm elastix-5.0.1-linux.tar.bz2
ENV PATH="/opt/elastix/bin:${PATH}"

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create necessary directories
RUN mkdir -p files/uploads files/processed files/DICOMS files/important_atlas

# Set up FreeSurfer license (you'll need to provide a valid license)
# Note: You need to mount your FreeSurfer license file or set it up properly
RUN touch ${FREESURFER_HOME}/license.txt

# Expose port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]