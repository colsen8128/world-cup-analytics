#!/usr/bin/env bash
#
# Refresh the dashboard's data and publish it.
#
# FBref/Cloudflare blocks datacenter IPs, so the fetch can't run on GitHub
# Actions — it must run from a machine with a normal (residential) IP, like
# your Mac. This script pulls fresh stats, commits public/data.json, and pushes.
# The push triggers the GitHub Pages deploy, so the live site updates in ~1-2 min.
#
# Usage:  ./refresh.sh    (or: npm run refresh)
#
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x venv/bin/python ]; then
  echo "No venv found. Create it once with:" >&2
  echo "  /opt/anaconda3/bin/python3.12 -m venv venv" >&2
  echo "  ./venv/bin/python -m pip install soccerdata lxml html5lib pandas" >&2
  exit 1
fi

echo "Fetching latest stats from FBref ..."
./venv/bin/python fetch_fbref.py

if git diff --quiet -- public/data.json; then
  echo "No data changes — nothing to push."
  exit 0
fi

git add public/data.json
git commit -m "Update stats $(date -u +%F)"
git push
echo
echo "Pushed. GitHub Pages will redeploy in ~1-2 min:"
echo "  https://colsen8128.github.io/world-cup-analytics/"
