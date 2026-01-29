#!/usr/bin/env sh
set -eu

REPO_OWNER="clevrthings"
REPO_NAME="Toolbox"
BRANCH="main"
DEFAULT_INSTALL_DIR="${HOME}/Toolbox"

echo "Default install path: ${DEFAULT_INSTALL_DIR}"
if [ -n "${TOOLBOX_INSTALL_DIR:-}" ]; then
  INSTALL_DIR="${TOOLBOX_INSTALL_DIR}"
  echo "Using TOOLBOX_INSTALL_DIR=${INSTALL_DIR}"
else
  printf "Install path (press Enter to accept default): "
  if [ -t 0 ]; then
    read -r INSTALL_DIR || true
  else
    read -r INSTALL_DIR < /dev/tty || true
  fi
fi
if [ -z "${INSTALL_DIR}" ]; then
  INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
fi

if [ -d "${INSTALL_DIR}" ]; then
  echo "Install directory already exists: ${INSTALL_DIR}"
  if [ "${TOOLBOX_OVERWRITE:-}" = "1" ]; then
    OVERWRITE="y"
    echo "TOOLBOX_OVERWRITE=1 set, overwriting."
  else
    printf "Overwrite it? (y/N): "
    read -r OVERWRITE || true
  fi
  if [ "${OVERWRITE}" != "y" ] && [ "${OVERWRITE}" != "Y" ]; then
    echo "Remove it or choose a different location."
    exit 1
  fi
  rm -rf "${INSTALL_DIR}"
fi

TMP_DIR="$(mktemp -d)"
ZIP_PATH="${TMP_DIR}/toolbox.zip"

echo "Downloading ${REPO_OWNER}/${REPO_NAME} (${BRANCH})..."
curl -fsSL "https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${BRANCH}.zip" -o "${ZIP_PATH}"

echo "Extracting..."
unzip -q "${ZIP_PATH}" -d "${TMP_DIR}"

EXTRACTED_DIR="${TMP_DIR}/${REPO_NAME}-${BRANCH}"
if [ ! -d "${EXTRACTED_DIR}" ]; then
  echo "Extraction failed."
  exit 1
fi

mv "${EXTRACTED_DIR}" "${INSTALL_DIR}"

echo "Running installer..."
cd "${INSTALL_DIR}"
chmod +x install.sh
if [ "${TOOLBOX_GLOBAL:-}" = "1" ]; then
  echo "TOOLBOX_GLOBAL=1 set, will create global command."
  TOOLBOX_GLOBAL=1 ./install.sh
else
  CREATE_GLOBAL="n"
  if [ -t 0 ]; then
    printf "Create global 'toolbox' command? (y/N): "
    read -r CREATE_GLOBAL || true
  else
    read -r CREATE_GLOBAL < /dev/tty || true
  fi
  if [ "${CREATE_GLOBAL}" = "y" ] || [ "${CREATE_GLOBAL}" = "Y" ]; then
    TOOLBOX_GLOBAL=1 ./install.sh
  else
    ./install.sh
  fi
fi
