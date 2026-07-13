#!/usr/bin/env sh
# Quick Cloudflare Tunnel to local skill-map server (port 5000).
PORT="${PORT:-5000}"
echo "Starting Cloudflare quick tunnel -> http://localhost:${PORT}"
echo "Keep this running. Use 'npm run serve' in another terminal if needed."
exec cloudflared tunnel --url "http://localhost:${PORT}"
