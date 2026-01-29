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

RUN_SCRIPT="${ROOT_DIR}/run.sh"
cat > "${RUN_SCRIPT}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SOURCE="${BASH_SOURCE[0]}"
while [ -L "${SOURCE}" ]; do
  SOURCE="$(readlink "${SOURCE}")"
done
ROOT_DIR="$(cd "$(dirname "${SOURCE}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Virtual environment not found. Run ./install.sh first."
  exit 1
fi
exec "${VENV_DIR}/bin/toolbox"
EOF
chmod +x "${RUN_SCRIPT}"

read -r -p "Create global 'toolbox' command in /usr/local/bin? (y/N): " CREATE_GLOBAL
if [[ "${CREATE_GLOBAL}" == "y" || "${CREATE_GLOBAL}" == "Y" ]]; then
  sudo tee /usr/local/bin/toolbox >/dev/null <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${ROOT_DIR}/.venv/bin/toolbox"
EOF
  sudo chmod +x /usr/local/bin/toolbox
  echo "Global command installed: toolbox"
fi

echo ""
echo "Done."
echo "Run with:"
echo "  ${PY} -m toolbox"
echo "  ./run.sh"
echo "  toolbox (if installed globally)"
