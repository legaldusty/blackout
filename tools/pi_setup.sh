#!/bin/bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y python3-picamera2 python3-opencv python3-venv python3-pip bluez git
cd "$(dirname "$0")/.."
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install mediapipe bleak numpy
.venv/bin/python -c "from eye import models; [models.path(n) for n in models.SOURCES]; print('models ready')"
rpicam-hello --list-cameras
