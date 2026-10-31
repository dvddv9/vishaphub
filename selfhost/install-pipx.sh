#!/usr/bin/env sh
# VishapHub without Docker: installs the `vishap-hub` command with pipx, then runs the setup questions.
#   PYTHON=python3.12 ./install-pipx.sh        (Python 3.11+)
set -eu
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Python 3.11 or newer is required (set PYTHON=...)."; exit 1; }
"$PY" -m pipx --version >/dev/null 2>&1 || "$PY" -m pip install --user pipx || { echo "Could not install pipx."; exit 1; }
"$PY" -m pipx install --force ./apps/hub
# The hub finds the validator and the analyser's rules as libraries in its own environment.
"$PY" -m pipx inject vishap-hub ./packages/core ./apps/validator "pytest==9.1.1" "edge-tts==7.3.1"
"$PY" -m pipx runpip vishap-hub install --no-deps ./apps/analyzer
"$PY" -m pipx ensurepath >/dev/null 2>&1 || true
echo
echo "Installed. Open a new terminal if 'vishap-hub' is not found, then:"
echo "  vishap-hub init      # model, privacy, how code is run"
echo "  vishap-hub doctor    # what this installation will do"
echo "  vishap-hub serve     # http://127.0.0.1:8080"
