#!/bin/bash
set -e

echo "Starting Disgram in production mode..."

# --- Ensure Git is available for git_manager integration ---
if ! command -v git >/dev/null 2>&1; then
  echo "Git not found, attempting to install..."
  install_cmd=""
  if command -v apt-get >/dev/null 2>&1; then
    install_cmd="apt-get update && apt-get install -y --no-install-recommends git"
  elif command -v apk >/dev/null 2>&1; then
    install_cmd="apk add --no-cache git"
  elif command -v yum >/dev/null 2>&1; then
    install_cmd="yum install -y git"
  elif command -v dnf >/dev/null 2>&1; then
    install_cmd="dnf install -y git"
  elif command -v microdnf >/dev/null 2>&1; then
    install_cmd="microdnf install -y git"
  elif command -v pacman >/dev/null 2>&1; then
    install_cmd="pacman -Sy --noconfirm git"
  fi

  if [ -n "$install_cmd" ]; then
    # shellcheck disable=SC2086
    sh -c "$install_cmd" || echo "Warning: Git installation command failed; continuing without Git"
  else
    echo "Warning: No known package manager found to install Git; continuing without Git"
  fi
fi

# Minimal Git configuration (safe to run even if Git missing)
if command -v git >/dev/null 2>&1; then
  # Avoid 'detected dubious ownership' in containerized/root environments
  git config --global --add safe.directory "$(pwd)" || true
  git config user.name "Disgram Bot" || true
  git config user.email "disgram@bot.local" || true
  echo "Git available: $(git --version)"
else
  echo "Git still not available; git-based log commits will be disabled"
fi

# --- Ensure Gunicorn is available (prefer installing via requirements.txt at build time) ---
if ! command -v gunicorn >/dev/null 2>&1; then
  echo "Gunicorn not found, attempting to install..."
  python -m pip install --no-cache-dir 'gunicorn>=20.1.0' || true
fi

# Configure server parameters (keep 1 worker to avoid duplicating background subprocesses)
PORT_TO_USE=${PORT:-8000}
WORKERS=${WORKERS:-1}
THREADS=${THREADS:-4}
TIMEOUT=${TIMEOUT:-120}

echo "Launching Gunicorn on 0.0.0.0:${PORT_TO_USE} (workers=${WORKERS}, threads=${THREADS}, timeout=${TIMEOUT})"
exec gunicorn --workers "${WORKERS}" --threads "${THREADS}" --timeout "${TIMEOUT}" --bind "0.0.0.0:${PORT_TO_USE}" --access-logfile - --error-logfile - main:app