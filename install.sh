#!/usr/bin/env bash
set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python 3.10+ is required. Please install Python 3.10+ and try again."
  exit 1
fi

"${PYTHON_BIN}" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
if [ $? -ne 0 ]; then
  echo "Python 3.10+ is required."
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "On macOS, install a newer Python with Homebrew:"
    echo "  brew install python@3.11"
  else
    echo "Please install Python 3.10+ and try again."
  fi
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Creating virtual environment..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

PY="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

echo "Upgrading pip..."
"${PY}" -m pip install --upgrade pip

echo "Installing Toolbox and dependencies..."
"${PIP}" install -e "${ROOT_DIR}"

RUN_SCRIPT="${ROOT_DIR}/run.sh"
cat > "${RUN_SCRIPT}" <<'EOS'
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
EOS
chmod +x "${RUN_SCRIPT}"

read -r -p "Create global 'toolbox' command in /usr/local/bin? (y/N): " CREATE_GLOBAL
if [[ "${CREATE_GLOBAL}" == "y" || "${CREATE_GLOBAL}" == "Y" ]]; then
  sudo tee /usr/local/bin/toolbox >/dev/null <<EOS
#!/usr/bin/env bash
set -euo pipefail
exec "${ROOT_DIR}/.venv/bin/toolbox"
EOS
  sudo chmod +x /usr/local/bin/toolbox
  echo "Global command installed: toolbox"
fi

echo ""
echo "Done."
echo "Run with:"
echo "  ${PY} -m toolbox"
echo "  ./run.sh"
echo "  toolbox (if installed globally)"
