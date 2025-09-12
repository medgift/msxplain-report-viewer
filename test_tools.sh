#!/bin/bash

# Test script to verify neuroimaging tools installation
echo "Testing neuroimaging tools installation..."
echo "=========================================="

# Test FSL
echo -n "Testing FSL... "
if command -v fsl &> /dev/null; then
    echo "✓ FSL found"
    echo "  Version: $(cat $FSLDIR/etc/fslversion)"
else
    echo "✗ FSL not found"
fi

# Test FreeSurfer
echo -n "Testing FreeSurfer... "
if [ -d "$FREESURFER_HOME" ] && [ -f "$FREESURFER_HOME/bin/recon-all" ]; then
    echo "✓ FreeSurfer found"
    if [ -f "$FREESURFER_HOME/license.txt" ]; then
        echo "  ✓ License file found"
    else
        echo "  ⚠ License file missing"
    fi
else
    echo "✗ FreeSurfer not found"
fi

# Test ANTs
echo -n "Testing ANTs... "
if command -v antsRegistration &> /dev/null; then
    echo "✓ ANTs found"
    antsRegistration --version 2>&1 | head -1
else
    echo "✗ ANTs not found"
fi

# Test dcm2niix
echo -n "Testing dcm2niix... "
if command -v dcm2niix &> /dev/null; then
    echo "✓ dcm2niix found"
    dcm2niix -h 2>&1 | head -1
else
    echo "✗ dcm2niix not found"
fi

# Test elastix
echo -n "Testing elastix... "
if command -v elastix &> /dev/null; then
    echo "✓ elastix found"
    elastix --version 2>&1 | head -1
else
    echo "✗ elastix not found"
fi

# Test HD-BET
echo -n "Testing HD-BET... "
if python -c "import HD_BET" &> /dev/null; then
    echo "✓ HD-BET found"
else
    echo "✗ HD-BET not found"
fi

# Test Python packages
echo -n "Testing Python packages... "
MISSING_PACKAGES=""

for package in torch torchvision monai nibabel pydicom SimpleITK pandas numpy scipy; do
    if ! python -c "import $package" &> /dev/null; then
        MISSING_PACKAGES="$MISSING_PACKAGES $package"
    fi
done

if [ -z "$MISSING_PACKAGES" ]; then
    echo "✓ All Python packages found"
else
    echo "✗ Missing packages:$MISSING_PACKAGES"
fi

# Test GPU availability
echo -n "Testing GPU availability... "
if python -c "import torch; print('GPU available:', torch.cuda.is_available())" 2>/dev/null; then
    echo "✓ GPU test completed"
else
    echo "✗ GPU test failed"
fi

echo "=========================================="
echo "Test completed!"
