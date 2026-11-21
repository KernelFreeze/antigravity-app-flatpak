#!/usr/bin/env python3
"""Pin the latest official Antigravity Linux build in the Flatpak packaging.

The version comes from the electron-updater feed that the app itself polls.
The feed lists the AppImage and .deb of a release; the tarball this package
installs sits next to them under the same versioned build directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "com.google.Antigravity.yml"
METAINFO = "com.google.Antigravity.metainfo.xml"
FEED_URL = (
    "https://antigravity-hub-auto-updater-974169037036.us-central1.run.app"
    "/manifest/latest-x64-linux.yml"
)
BUILD_PREFIX = "https://storage.googleapis.com/antigravity-public/antigravity-hub/"
TARBALL_RE = re.compile(
    re.escape(BUILD_PREFIX) + r"(\d+\.\d+\.\d+)-(\d+)/linux-x64/Antigravity\.tar\.gz"
)
FEED_FILE_RE = re.compile(
    re.escape(BUILD_PREFIX) + r"(\d+\.\d+\.\d+)-(\d+)/linux-x64/Antigravity\.(?:AppImage|deb)"
)
SOURCE_RE = re.compile(
    r"^      - type: extra-data\n.*?(?=^      - type:|\Z)", re.M | re.S
)
# Files whose presence shows the archive is the Electron app, not an error page.
REQUIRED_MEMBERS = (
    "Antigravity-x64/antigravity",
    "Antigravity-x64/resources/app.asar",
    "Antigravity-x64/resources/bin/language_server",
)
USER_AGENT = "antigravity-flatpak-updater"


@dataclass(frozen=True)
class Artifact:
    version: str
    url: str
    sha256: str
    size: int


def version_key(version: str) -> tuple[int, ...]:
    return tuple(map(int, version.split(".")))


def version_from_url(url: str) -> str:
    match = TARBALL_RE.fullmatch(url)
    if not match:
        raise ValueError(f"Unexpected Antigravity tarball URL: {url}")
    return match.group(1)


def field(source: str, name: str) -> str:
    matches = re.findall(rf"^        {re.escape(name)}: (\S+)$", source, re.M)
    if len(matches) != 1:
        raise ValueError(f"Expected one extra-data {name} field")
    return matches[0]


def read_source(manifest: str) -> tuple[re.Match[str], Artifact]:
    matches = list(SOURCE_RE.finditer(manifest))
    if len(matches) != 1:
        raise ValueError("Expected one extra-data source")
    match = matches[0]
    source = match.group()
    if field(source, "filename") != "antigravity.tar.gz":
        raise ValueError("Unexpected extra-data filename")
    url = field(source, "url")
    sha256 = field(source, "sha256")
    size = int(field(source, "size"))
    if not re.fullmatch(r"[a-f0-9]{64}", sha256) or size <= 0:
        raise ValueError("Invalid current tarball checksum or size")
    return match, Artifact(version_from_url(url), url, sha256, size)


def parse_feed(feed: str) -> tuple[str, list[str]]:
    """Returns the version and file URLs of an electron-updater feed.

    The feed is a small, flat YAML document, so a line scan avoids depending
    on a YAML library.
    """
    versions = re.findall(r"^version: *'?\"?([^\s'\"]+)'?\"?$", feed, re.M)
    if len(versions) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", versions[0]):
        raise ValueError("Update feed has no valid version")
    urls = re.findall(r"^ *- url: *(\S+)$", feed, re.M)
    return versions[0], urls


def tarball_url(version: str, feed_urls: list[str]) -> str:
    builds = set()
    for url in feed_urls:
        match = FEED_FILE_RE.fullmatch(url)
        if match and match.group(1) == version:
            builds.add(match.group(2))
    if len(builds) != 1:
        raise ValueError(f"Update feed lists no single build URL for {version}")
    return f"{BUILD_PREFIX}{version}-{builds.pop()}/linux-x64/Antigravity.tar.gz"


def fetch(url: str, headers: dict[str, str] | None = None):
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    return urllib.request.urlopen(request, timeout=60)


def download(url: str, version: str) -> Artifact:
    digest = hashlib.sha256()
    size = 0
    with tempfile.TemporaryFile() as stream:
        with fetch(url) as response:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                stream.write(chunk)
            expected_size = response.headers.get("Content-Length")
        if expected_size is not None and size != int(expected_size):
            raise ValueError("Tarball download was truncated")
        stream.seek(0)
        if stream.read(2) != b"\x1f\x8b":
            raise ValueError("Download is not a gzip tarball")
        stream.seek(0)
        try:
            with tarfile.open(fileobj=stream, mode="r:gz") as archive:
                names = set(archive.getnames())
        except (tarfile.TarError, EOFError, OSError) as error:
            raise ValueError(f"Download is not a valid tarball: {error}") from error
        missing = [name for name in REQUIRED_MEMBERS if name not in names]
        if missing:
            raise ValueError(f"Tarball is missing {', '.join(missing)}")
    return Artifact(version, url, digest.hexdigest(), size)


def fetch_latest(current: Artifact) -> Artifact:
    # The feed answers a client that is already current with the version
    # alone, so it only lists download URLs when sent an older version.
    with fetch(FEED_URL, {"x-app-version": current.version}) as response:
        version, urls = parse_feed(response.read().decode("utf-8"))
    if version == current.version:
        return current
    if version_key(version) < version_key(current.version):
        raise ValueError("Update feed returned an older Antigravity version")
    return download(tarball_url(version, urls), version)


def render_update(
    manifest: str, metainfo: str, latest: Artifact, date: str
) -> tuple[str, str, Artifact]:
    match, current = read_source(manifest)
    component = ET.fromstring(metainfo)
    if component.findtext("id") != "com.google.Antigravity":
        raise ValueError("Unexpected AppStream component")
    releases = component.find("releases")
    if releases is None or releases.find(f"./release[@version='{current.version}']") is None:
        raise ValueError("Current manifest version is missing from AppStream releases")

    source = match.group()
    for name, value in (
        ("url", latest.url),
        ("sha256", latest.sha256),
        ("size", str(latest.size)),
    ):
        source = re.sub(
            rf"^(        {name}: )\S+$",
            lambda m: m.group(1) + value,
            source,
            count=1,
            flags=re.M,
        )
    manifest = manifest[: match.start()] + source + manifest[match.end() :]

    if latest.version != current.version:
        if releases.find(f"./release[@version='{latest.version}']") is not None:
            raise ValueError("Latest version is already an older AppStream release")
        marker = "  <releases>\n"
        if metainfo.count(marker) != 1:
            raise ValueError("Expected one AppStream releases section")
        entry = (
            f'    <release version="{latest.version}" date="{date}">\n'
            "      <url>https://antigravity.google</url>\n"
            "      <description>\n"
            "        <p>Update the official Linux build.</p>\n"
            "      </description>\n"
            "    </release>\n"
        )
        metainfo = metainfo.replace(marker, marker + entry, 1)
    ET.fromstring(metainfo)
    return manifest, metainfo, current


def update(root: Path, *, dry_run: bool = False) -> tuple[bool, Artifact, Artifact]:
    manifest_path, metainfo_path = root / MANIFEST, root / METAINFO
    original_manifest = manifest_path.read_text(encoding="utf-8")
    original_metainfo = metainfo_path.read_text(encoding="utf-8")
    _, current = read_source(original_manifest)
    latest = fetch_latest(current)
    manifest, metainfo, _ = render_update(
        original_manifest,
        original_metainfo,
        latest,
        dt.datetime.now(dt.timezone.utc).date().isoformat(),
    )
    changed = (manifest, metainfo) != (original_manifest, original_metainfo)
    if changed and not dry_run:
        # Both files were validated above, so neither write leaves the pair inconsistent.
        manifest_path.write_text(manifest, encoding="utf-8")
        metainfo_path.write_text(metainfo, encoding="utf-8")
    return changed, current, latest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report without changing files")
    args = parser.parse_args()
    try:
        changed, current, latest = update(ROOT, dry_run=args.dry_run)
    except (OSError, ValueError, urllib.error.URLError, ET.ParseError) as error:
        print(f"Update failed: {error}", file=sys.stderr)
        return 1

    status = "Update available" if changed else "Already current"
    print(f"{status}: {current.version} -> {latest.version}")
    print(f"URL: {latest.url}\nSHA-256: {latest.sha256}\nSize: {latest.size}")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(
                f"changed={str(changed).lower()}\nprevious_version={current.version}\n"
                f"version={latest.version}\nurl={latest.url}\n"
                f"sha256={latest.sha256}\nsize={latest.size}\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
