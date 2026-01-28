#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Please install Python 3.10+ and try again."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv "${VENV_DIR}"
fi

PY="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

echo "Upgrading pip..."
"${PY}" -m pip install --upgrade pip

echo "Installing Toolbox and dependencies..."
"${PIP}" install -e "${ROOT_DIR}"

echo ""
echo "Done."
echo "Run with:"
echo "  ${PY} -m toolbox"
