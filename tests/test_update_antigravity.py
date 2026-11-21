"""Behavior checks for Antigravity tarball updates, without network access."""

import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "update_antigravity", ROOT / "scripts/update_antigravity.py"
)
updater = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = updater
spec.loader.exec_module(updater)

VERSION = "99.1.0"
BUILD = "1234567890"
BUILD_DIR = f"{updater.BUILD_PREFIX}{VERSION}-{BUILD}/linux-x64"


def tarball(members=updater.REQUIRED_MEMBERS):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in members:
            data = b"fixture"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def feed(version=VERSION, build_dir=BUILD_DIR):
    return (
        f"version: {version}\n"
        "files:\n"
        f"  - url: {build_dir}/Antigravity.AppImage\n"
        "    sha512: AAAA\n"
        "    size: 10\n"
        f"  - url: {build_dir}/Antigravity.deb\n"
        "    sha512: BBBB\n"
        "    size: 10\n"
        "path: Antigravity.AppImage\n"
    ).encode()


class Response(io.BytesIO):
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body) if length is None else length)}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in (updater.MANIFEST, updater.METAINFO):
            (self.root / name).write_bytes((ROOT / name).read_bytes())
        self.before = self.files()
        _, self.current = updater.read_source(self.before[0])
        self.url = f"{BUILD_DIR}/Antigravity.tar.gz"
        self.requests = []

    def files(self):
        return tuple(
            (self.root / name).read_text(encoding="utf-8")
            for name in (updater.MANIFEST, updater.METAINFO)
        )

    def run_update(self, feed_body=None, body=None, length=None, dry_run=False):
        def fake_fetch(url, headers=None):
            self.requests.append((url, headers))
            if url == updater.FEED_URL:
                return Response(feed() if feed_body is None else feed_body)
            return Response(tarball() if body is None else body, length)

        with patch.object(updater, "fetch", side_effect=fake_fetch):
            return updater.update(self.root, dry_run=dry_run)

    def test_new_build_pins_tarball_and_preserves_release_history(self):
        changed, previous, latest = self.run_update()
        self.assertTrue(changed)
        self.assertEqual(previous, self.current)
        self.assertEqual(latest.url, self.url)
        self.assertEqual(latest.sha256, hashlib.sha256(tarball()).hexdigest())
        self.assertEqual(latest.size, len(tarball()))
        self.assertEqual(
            self.requests[0], (updater.FEED_URL, {"x-app-version": self.current.version})
        )
        manifest, metainfo = self.files()
        _, source = updater.read_source(manifest)
        self.assertEqual(source, latest)
        releases = ET.fromstring(metainfo).findall("./releases/release")
        self.assertEqual(releases[0].get("version"), VERSION)
        self.assertIn(self.current.version, [r.get("version") for r in releases])
        self.assertEqual(manifest.count("type: extra-data"), 1)
        self.assertIn("git-2.56.1.tar.xz", manifest)

    def test_current_version_is_a_noop_without_downloading(self):
        changed, _, latest = self.run_update(feed_body=f"version: {self.current.version}\n".encode())
        self.assertFalse(changed)
        self.assertEqual(latest, self.current)
        self.assertEqual([url for url, _ in self.requests], [updater.FEED_URL])
        self.assertEqual(self.files(), self.before)

    def test_dry_run_reports_update_without_writing(self):
        changed, _, latest = self.run_update(dry_run=True)
        self.assertTrue(changed)
        self.assertEqual(latest.version, VERSION)
        self.assertEqual(self.files(), self.before)

    def test_older_feed_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "older"):
            self.run_update(feed_body=feed(version="0.0.1", build_dir=BUILD_DIR.replace(VERSION, "0.0.1")))
        self.assertEqual(self.files(), self.before)

    def test_feed_without_matching_build_urls_is_rejected(self):
        bodies = (
            f"version: {VERSION}\n".encode(),
            feed(build_dir=BUILD_DIR.replace("https:", "http:")),
            feed(build_dir=BUILD_DIR.replace("storage.googleapis.com", "example.com")),
            feed(build_dir=BUILD_DIR.replace(VERSION, "98.0.0")),
            feed(build_dir=BUILD_DIR.replace("linux-x64", "linux-arm64")),
        )
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaisesRegex(ValueError, "build URL"):
                    self.run_update(feed_body=body)
                self.assertEqual(self.files(), self.before)

    def test_invalid_download_leaves_both_files_untouched(self):
        bodies = (
            b"",
            b"<html>download failed</html>",
            b"\x1f\x8b" + b"x" * 100,
            tarball(members=("Antigravity-x64/antigravity",)),
        )
        for body in bodies:
            with self.subTest(body=body[:16]):
                with self.assertRaisesRegex(ValueError, "tarball|Tarball"):
                    self.run_update(body=body)
                self.assertEqual(self.files(), self.before)

    def test_truncated_download_leaves_both_files_untouched(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.run_update(length=len(tarball()) + 1)
        self.assertEqual(self.files(), self.before)

    def test_invalid_metadata_cannot_partially_update_manifest(self):
        (self.root / updater.METAINFO).write_text("<component>")
        with self.assertRaises(ET.ParseError):
            self.run_update()
        self.assertEqual((self.root / updater.MANIFEST).read_text(), self.before[0])


if __name__ == "__main__":
    unittest.main()
