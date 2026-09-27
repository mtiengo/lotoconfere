#!/usr/bin/env bash
# macOS: ad-hoc sign the frozen bundle, verify the signature, then wrap it in a .dmg.
#
#   packaging/build_dmg.sh 0.1.0 arm64
#
# The signing step is not optional and not cosmetic. An unsigned or broken bundle
# makes macOS call the app "damaged" and offer no Open Anyway, leaving the user a
# terminal command -- and this audience cannot be asked to run one. Ad-hoc signing
# gives the ordinary "unidentified developer" path instead: System Settings ->
# Privacy & Security -> Open Anyway. If verification fails, so does this script,
# because shipping the "damaged" dialog is worse than shipping nothing.
set -euo pipefail

VERSION="${1:?usage: build_dmg.sh VERSION ARCH}"
ARCH="${2:?usage: build_dmg.sh VERSION ARCH}"

APP_NAME="LotoConfere"
BUNDLE="dist/${APP_NAME}.app"
DMG="dist/${APP_NAME}-${VERSION}-macos-${ARCH}.dmg"
STAGING="$(mktemp -d)/${APP_NAME}"

test -d "${BUNDLE}" || { echo "no bundle at ${BUNDLE}; run pyinstaller first" >&2; exit 1; }

echo "==> ad-hoc signing ${BUNDLE}"
codesign --force --deep --sign - "${BUNDLE}"

echo "==> verifying the signature"
codesign --verify --deep --strict --verbose=2 "${BUNDLE}"

echo "==> verifying HTTPS inside the frozen app"
"${BUNDLE}/Contents/MacOS/${APP_NAME}" --probe

echo "==> building ${DMG}"
mkdir -p "${STAGING}"
cp -R "${BUNDLE}" "${STAGING}/"
ln -s /Applications "${STAGING}/Applications"
hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGING}" -ov -format UDZO "${DMG}"

echo "==> done: ${DMG}"
