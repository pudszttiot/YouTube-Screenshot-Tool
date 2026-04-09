#!/usr/bin/env bash
# exit on error
set -o errexit

# Install Python dependencies
pip install -r requirements.txt

# Update package list and install ffmpeg
apt-get update
apt-get install -y ffmpeg
