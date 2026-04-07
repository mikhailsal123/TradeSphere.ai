#!/usr/bin/env bash
# Render deploy is Git-based: push to GitHub and let Render build from render.yaml (or dashboard settings).

echo "TradeSphere backend on Render"
echo ""
echo "1. Push this repo to GitHub."
echo "2. In Render: New → Web Service → connect the repo."
echo "3. Use the settings from render.yaml (Python, gunicorn flask_backend:app) or import the blueprint."
echo "4. Set secrets (e.g. CEREBRAS_TOKEN) in the Render dashboard if you use AI features."
echo ""
echo "On the Next.js Render service, set NEXT_PUBLIC_FLASK_BACKEND_URL to this backend's URL, then redeploy the frontend."
echo "On this Flask service, optionally set SHELL_SITE_URL to your Next.js URL (link on the backend main-page stub)."
echo "Local builds: ./set_next_iframe_backend_url.sh https://your-flask-service.onrender.com"
echo ""
echo "See README.md → Deployment for the full picture."
