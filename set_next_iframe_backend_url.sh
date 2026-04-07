#!/usr/bin/env bash
# Writes frontend/.env.production.local so production builds know the Flask service URL.
# On Render, set NEXT_PUBLIC_FLASK_BACKEND_URL on the Next.js Web Service instead (Environment → add → redeploy).
set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: ./set_next_iframe_backend_url.sh https://your-flask-service.onrender.com"
    exit 1
fi

BACKEND_URL="$1"
ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT/frontend/.env.production.local"

printf 'NEXT_PUBLIC_FLASK_BACKEND_URL=%s\n' "$BACKEND_URL" > "$ENV_FILE"

echo "Wrote $ENV_FILE"
echo "Rebuild: cd frontend && npm run build"
