#!/usr/bin/env bash
set -euo pipefail

# Dedisc installer – Python 3.14 + patched pycdio

APP_ID="pl.septicwolf818.Dedisc"
APP_NAME="Dedisc"
PYTHON_BIN="python3.14"
INSTALL_DIR="${HOME}/.local/share/${APP_NAME}"
VENV_DIR="${INSTALL_DIR}/venv"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
BIN_DIR="${HOME}/.local/bin"
PATCH_FILE="pycdio-py314.patch"

command -v "${PYTHON_BIN}" >/dev/null 2>&1 || {
  echo "✗ Python ${PYTHON_BIN} not found. Install Python 3.14 first." >&2; exit 1;
}

PYVER=$("${PYTHON_BIN}" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
[ "${PYVER}" = "3.14" ] || { echo "✗ Need Python 3.14, got ${PYVER}" >&2; exit 1; }

mkdir -p "${INSTALL_DIR}" "${BIN_DIR}" "${DESKTOP_DIR}" "${ICON_DIR}"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -a "${SRC_DIR}/src" "${INSTALL_DIR}/"
cp -a "${SRC_DIR}/po" "${INSTALL_DIR}/" 2>/dev/null || true
cp -a "${SRC_DIR}/data" "${INSTALL_DIR}/" 2>/dev/null || true
cp -a "${SRC_DIR}/requirements.txt" "${INSTALL_DIR}/" 2>/dev/null || true
cp -a "${SRC_DIR}/${PATCH_FILE}" "${INSTALL_DIR}/" 2>/dev/null || true

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip wheel setuptools >/dev/null

PATCH_DIR=$(mktemp -d)
trap "rm -rf ${PATCH_DIR}" EXIT

"${VENV_DIR}/bin/pip" download --no-deps --no-binary :all: pycdio==2.1.1 -d "${PATCH_DIR}"
tar xf "${PATCH_DIR}"/pycdio-*.tar.gz -C "${PATCH_DIR}"
cd "${PATCH_DIR}/pycdio-2.1.1"
patch -p1 < "${INSTALL_DIR}/${PATCH_FILE}"
"${VENV_DIR}/bin/pip" install .
cd "${SRC_DIR}"

# Install remaining deps
grep -v '^pycdio' "${INSTALL_DIR}/requirements.txt" | "${VENV_DIR}/bin/pip" install -r /dev/stdin

# Launcher
cat > "${BIN_DIR}/${APP_NAME}" <<EOL
#!/usr/bin/env bash
VENV="${VENV_DIR}"
APP_DIR="${INSTALL_DIR}"
export PYTHONPATH="\${APP_DIR}"
exec "\${VENV}/bin/python3" "\${APP_DIR}/src/main.py" "\$@"
EOL
chmod +x "${BIN_DIR}/${APP_NAME}"

# Translations
mkdir -p "${INSTALL_DIR}/locale/pl/LC_MESSAGES"
msgfmt -o "${INSTALL_DIR}/locale/pl/LC_MESSAGES/dedisc.mo" "${SRC_DIR}/po/pl.po" 2>/dev/null || true

# Desktop entry
sed -e 's|@APP_ID@|'"${APP_ID}"'|g' -e 's|@BIN_PATH@|'"${BIN_DIR}/${APP_NAME}"'|g' \
	"${SRC_DIR}/data/dedisc.desktop.in" > "${DESKTOP_DIR}/${APP_ID}.desktop"
cp "${SRC_DIR}/data/pl.septicwolf818.Dedisc.svg" "${ICON_DIR}/${APP_ID}.svg"
gtk-update-icon-cache -f "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
update-desktop-database "${DESKTOP_DIR}" >/dev/null 2>&1 || true

echo "✓ Dedisc installed to ${INSTALL_DIR}"
echo "  Launcher:  ${BIN_DIR}/${APP_NAME}"
echo "  Desktop:   ${DESKTOP_DIR}/${APP_ID}.desktop"
echo "  Icon:      ${ICON_DIR}/${APP_ID}.svg"
