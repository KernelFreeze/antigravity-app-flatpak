#!/bin/bash

# electron-updater only replaces AppImages on Linux and skips its checks when
# APPIMAGE is unset. Flatpak delivers updates.
unset APPIMAGE

# Antigravity reads PATH and SSH_AUTH_SOCK from `$SHELL -ilc`. The host login
# shell (zsh, fish) is usually missing from the runtime, so fall back to the
# runtime's bash, which still reads ~/.bash_profile and ~/.bashrc from the
# shared home directory.
if [ ! -x "${SHELL:-}" ]; then
    export SHELL=/bin/bash
fi

# Default location of many user-installed CLIs.
export PATH="${HOME}/.local/bin:${PATH}"

FLAGS=()
if [ -f "${XDG_CONFIG_HOME}/antigravity-flags.conf" ]; then
    mapfile -t FLAGS < <(grep -Ev '^\s*($|#)' "${XDG_CONFIG_HOME}/antigravity-flags.conf")
fi

exec zypak-wrapper /app/extra/antigravity/antigravity "${FLAGS[@]}" "$@"
