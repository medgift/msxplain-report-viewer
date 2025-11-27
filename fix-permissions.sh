#!/bin/bash

# Script to fix permissions for Docker volumes
# Run this before starting containers for the first time

echo "Creating directories and fixing permissions..."

# Create backend files directories if they don't exist
mkdir -p backend/files/uploads
mkdir -p backend/files/processed
mkdir -p backend/files/DICOMS
mkdir -p backend/files/important_atlas

# Set ownership to user ID 1000 (matches Docker container user)
# This ensures files created by the container are owned by your user
sudo chown -R 1000:1000 backend/files

# Set proper permissions
chmod -R 755 backend/files

echo "✓ Permissions fixed!"
echo "You can now run: docker-compose up"
