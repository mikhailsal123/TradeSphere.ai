#!/usr/bin/env bash
# Frontend Web Service on Render (Node): build + start from the frontend/ directory.

echo "TradeSphere Next.js frontend on Render"
echo ""
echo "1. Push this repo to GitHub."
echo "2. In Render: New → Web Service → connect the repo."
echo "3. Either import render-frontend.yaml or set manually:"
echo "   - Environment: Node"
echo "   - Build:  cd frontend && npm ci && npm run build"
echo "   - Start:  cd frontend && npm start"
echo ""
echo "The main page iframe should point at your Flask service URL (see frontend/src/app/page.tsx)."
echo "See README.md → Deployment."
