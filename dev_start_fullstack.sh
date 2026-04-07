#!/usr/bin/env bash
# Local dev: same as `npm run dev` — Next (3000) + Flask (5002).
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
exec npm run dev
