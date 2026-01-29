#!/usr/bin/env sh
set -eu

REPO_OWNER="clevrthings"
REPO_NAME="Toolbox"
BRANCH="main"
DEFAULT_INSTALL_DIR="${HOME}/Toolbox"

echo "Default install path: ${DEFAULT_INSTALL_DIR}"
printf "Install path (press Enter to accept default): "
read -r INSTALL_DIR || true
if [ -z "${INSTALL_DIR}" ]; then
  INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
fi

if [ -d "${INSTALL_DIR}" ]; then
  echo "Install directory already exists: ${INSTALL_DIR}"
  echo "Remove it or choose a different location."
  exit 1
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
./install.sh
