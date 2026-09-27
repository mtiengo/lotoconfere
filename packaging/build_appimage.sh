#!/usr/bin/env bash
# Linux: wrap the frozen onedir build into an .AppImage.
#
#   packaging/build_appimage.sh 0.1.0 x86_64
#
# appimagetool is downloaded to a temporary directory and checked against a
# pinned SHA-256: a build tool fetched from the internet is part of the supply
# chain, and an unpinned download is an unreviewed dependency.
set -euo pipefail

VERSION="${1:?usage: build_appimage.sh VERSION ARCH}"
ARCH="${2:-x86_64}"

APP_NAME="LotoConfere"
APPDIR="build/${APP_NAME}.AppDir"
OUTPUT="dist/${APP_NAME}-${VERSION}-linux-${ARCH}.AppImage"

# A tagged release, never `continuous`: the continuous asset is re-uploaded on
# every commit, so its digest changes under the pin and a verified build would
# start failing for no reason anybody could act on.
TOOL_VERSION="1.9.1"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/${TOOL_VERSION}/appimagetool-${ARCH}.AppImage"
# Refresh this pin deliberately, never automatically -- see the dependency-change skill.
TOOL_SHA256="${APPIMAGETOOL_SHA256:?set APPIMAGETOOL_SHA256 to the pinned digest}"

test -d "dist/${APP_NAME}" || { echo "no build at dist/${APP_NAME}; run pyinstaller first" >&2; exit 1; }

# One pin, one architecture. A digest that silently did not apply to the file
# being downloaded would be worse than no digest at all.
if [ "${ARCH}" != "x86_64" ]; then
  echo "the pinned appimagetool digest is for x86_64; pin ${ARCH} before building it" >&2
  exit 1
fi

echo "==> verifying HTTPS inside the frozen app"
"dist/${APP_NAME}/${APP_NAME}" --probe

echo "==> assembling ${APPDIR}"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/share/applications" \
         "${APPDIR}/usr/share/icons/hicolor/256x256/apps"
cp -R "dist/${APP_NAME}/." "${APPDIR}/usr/bin/"

ICON="src/lotoconfere/gui/icons/lotoconfere.png"
cp "${ICON}" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/lotoconfere.png"
cp "${ICON}" "${APPDIR}/lotoconfere.png"

cat > "${APPDIR}/usr/share/applications/lotoconfere.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=LotoConfere
Comment=Confira apostas das loterias da Caixa
Exec=LotoConfere
Icon=lotoconfere
Categories=Utility;
Terminal=false
DESKTOP
cp "${APPDIR}/usr/share/applications/lotoconfere.desktop" "${APPDIR}/lotoconfere.desktop"

cat > "${APPDIR}/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "${HERE}/usr/bin/LotoConfere" "$@"
APPRUN
chmod +x "${APPDIR}/AppRun"

echo "==> fetching appimagetool"
TOOL="$(mktemp -d)/appimagetool"
curl -fsSL "${TOOL_URL}" -o "${TOOL}"
echo "${TOOL_SHA256}  ${TOOL}" | sha256sum --check --status \
  || { echo "appimagetool SHA-256 mismatch" >&2; exit 1; }
chmod +x "${TOOL}"

echo "==> building ${OUTPUT}"
mkdir -p dist
# --appimage-extract-and-run: CI runners have no FUSE.
ARCH="${ARCH}" "${TOOL}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT}"

echo "==> done: ${OUTPUT}"
