# Antigravity Flatpak

Community Flatpak for [Antigravity](https://antigravity.google), Google's desktop app for coding agents, packaged as `com.google.Antigravity`. It is not affiliated with Google.

The official x86_64 tarball is not redistributed. Flatpak downloads it from Google at install time as [`extra-data`](https://docs.flatpak.org/en/latest/module-sources.html#extra-data) and verifies its size and SHA-256. The app runs on `org.electronjs.Electron2.BaseApp//26.08`, with zypak in place of Chromium's SUID sandbox. The runtime has no git, so the manifest builds it from source.

## Build and install

```bash
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.flatpak.Builder
./build.sh
```

`build.sh` builds into `builddir/`, exports the result to `repo/` and installs it from a local remote. Extra arguments go to `flatpak-builder`. Installation needs an internet connection to fetch the tarball from Google. To create a bundle afterwards:

```bash
flatpak build-bundle --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
  repo antigravity-x86_64.flatpak com.google.Antigravity stable
```

## Usage

```bash
flatpak run com.google.Antigravity
```

The desktop entry handles `antigravity://` links, so the browser can return to the app after sign-in.

### Agents and host tools

The app has access to your home directory, and the agents' commands run inside the sandbox, which has git, ssh and the usual command line tools of the Freedesktop runtime. Compilers, package managers and other programs installed on the host are not visible there, except those installed under your home directory.

Antigravity reads `PATH` from a login shell. If your login shell is not installed in the runtime (zsh and fish are not), the wrapper uses the runtime's bash, which reads `~/.bash_profile` and `~/.bashrc`. The wrapper also adds `~/.local/bin` to `PATH`.

To run a host program from the sandbox, call it through `flatpak-spawn`:

```bash
flatpak-spawn --host cargo build
```

The manifest grants `--talk-name=org.freedesktop.Flatpak` for this. It lets the app run any command outside the sandbox. To remove it:

```bash
flatpak override --user --no-talk-name=org.freedesktop.Flatpak com.google.Antigravity
```

### Data

Agent data lives in `~/.gemini/antigravity`, the same directory a native install uses. Electron settings and logs live in `~/.var/app/com.google.Antigravity/config/Antigravity`. Projects outside your home directory need an explicit permission:

```bash
flatpak override --user --filesystem=/path/to/projects com.google.Antigravity
```

### Launch options

Add Electron or Chromium flags to `~/.var/app/com.google.Antigravity/config/antigravity-flags.conf`, one per line. Empty lines and lines that start with `#` are ignored.

```conf
# Disable GPU acceleration
--disable-gpu
```

### Differences from the native app

- Updates come from Flatpak. The built-in updater only replaces AppImages and stays idle.
- The setup wizard that installs Antigravity IDE writes it under `~/.local/share/antigravity-ide`. The IDE then runs inside this sandbox, not as a host application.

## Updates

A [scheduled workflow](.github/workflows/update-antigravity.yml) runs every six hours. `scripts/update_antigravity.py` reads the feed the app's own updater uses, pins the new tarball's URL, size and checksum in the manifest and adds an AppStream release entry, then the workflow opens a pull request. A second job runs [flatpak-external-data-checker](https://github.com/flathub/flatpak-external-data-checker) for git. Build and launch the app before merging.

To run the update check locally:

```bash
python3 scripts/update_antigravity.py --dry-run   # check only
python3 scripts/update_antigravity.py             # update the manifest
python3 -m unittest discover -s tests             # offline tests for the updater
```

If Google changes the tarball layout, check `apply_extra.sh`, which extracts the app into `/app/extra/antigravity/`.

## Licenses

Packaging files are MIT and the AppStream metadata is CC0-1.0. Antigravity and its icon belong to Google; bundled third-party notices are preserved. git is GPL-2.0-only.
