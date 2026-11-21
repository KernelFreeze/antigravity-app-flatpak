#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if command -v flatpak-builder >/dev/null 2>&1; then
  BUILDER=(flatpak-builder)
else
  BUILDER=(flatpak run --user org.flatpak.Builder)
fi

"${BUILDER[@]}" \
  --user --install-deps-from=flathub --assumeyes \
  --force-clean --disable-rofiles-fuse --repo=repo \
  "$@" builddir com.google.Antigravity.yml

# Install on the host so apply_extra can create its own sandbox.
flatpak remote-add --user --if-not-exists --no-gpg-verify \
  antigravity-local "${PWD}/repo"
flatpak install --user --assumeyes --noninteractive --reinstall \
  antigravity-local com.google.Antigravity//stable
