#!/bin/bash
set -euo pipefail

cd /app/extra
ARCHIVE=antigravity.tar.gz
DEST=antigravity

# Re-running after a complete extraction leaves the installed files intact.
if [[ ! -f "$ARCHIVE" ]]; then
  test -x "$DEST/antigravity"
  exit 0
fi

rm -rf Antigravity-x64 "$DEST.new"
tar -xzf "$ARCHIVE" --no-same-owner
mv Antigravity-x64 "$DEST.new"

# zypak (from the Electron BaseApp) replaces the SUID sandbox helper, which
# cannot work inside Flatpak.
rm -f "$DEST.new/chrome-sandbox"
# Flatpak delivers updates. Without app-update.yml, electron-updater has no
# feed and never tries to replace files under /app.
rm -f "$DEST.new/resources/app-update.yml"
# Sets desktopName in package.json so the Wayland app ID and X11 WM_CLASS
# match the desktop file.
FLATPAK_ID=com.google.Antigravity \
  patch-electron-desktop-filename "$DEST.new/resources/app.asar"
test -x "$DEST.new/antigravity"
test -x "$DEST.new/resources/bin/language_server"

rm -rf "$DEST"
mv "$DEST.new" "$DEST"
rm -f "$ARCHIVE"
