#!/bin/bash
# Double-click (macOS) or run (Linux) to launch the TAHMO live dashboard.
cd "$(dirname "$0")"
python3 tahmo_server.py
