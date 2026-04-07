#!/usr/bin/env bash
# Local: Flask on port 5002 (same as dev iframe default), then Next.js production server (npm start in frontend/).
FLASK_PORT=5002 python3 flask_backend.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 5

# Start Next.js frontend on port 3000
cd frontend
npm start
