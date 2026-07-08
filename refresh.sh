#!/usr/bin/env bash
#
# Refresh the dashboard's data locally and publish it.
#
# The PRIMARY source is now ESPN (near-live, and its public API isn't IP-blocked),
# so the routine refresh runs automatically in GitHub Actions — see
# .github/workflows/refresh-data.yml. You usually don't need to run this by hand.
#
# What this local script adds on top of CI is the FBref SECOND OPINION: FBref
# (Opta) blocks datacenter IPs, so its cross-check can only run from a residential
# machine like your Mac. It's advisory and never blocks publishing.
#
# Usage:  ./refresh.sh    (or: npm run refresh)
#
set -euo pipefail
cd "$(dirname "$0")"

# ESPN fetch + validation use only the Python standard library.
echo "Fetching latest stats from ESPN ..."
python3 fetch_espn.py public/data.json

# Gate: a single ERROR exits non-zero and `set -e` aborts before commit, so the
# last good (already-committed) public/data.json stays published. WARNINGs don't block.
echo "Validating public/data.json ..."
python3 validate.py

# Advisory second opinion vs FBref (Opta). Local only — needs the venv with
# soccerdata and a residential IP. Skips itself gracefully if FBref is unreachable.
if [ -x venv/bin/python ]; then
  echo "Cross-checking against FBref (advisory, local only) ..."
  ./venv/bin/python validate_external.py || true
else
  echo "Skipping FBref cross-check (no venv). To enable it once:"
  echo "  /opt/anaconda3/bin/python3.12 -m venv venv"
  echo "  ./venv/bin/python -m pip install soccerdata lxml html5lib pandas"
fi

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
