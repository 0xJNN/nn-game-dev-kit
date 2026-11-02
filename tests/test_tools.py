import hashlib
import io
import zipfile
from unittest.mock import patch

from helpers import ProjectTest
from pipeline.common import StudioError, atomic_json
from pipeline.process import run_process
from pipeline.tools import extract_zip, fetch_tool, verified_download


class ToolTests(ProjectTest):
    def test_download_is_pinned_and_cached(self):
        payload = b"pinned archive"
        spec = {"url": "https://example.invalid/archive.zip", "sha256": hashlib.sha256(payload).hexdigest()}
        with patch("urllib.request.urlopen", return_value=io.BytesIO(payload)) as request:
            path = verified_download(spec, self.root)
            self.assertEqual(path.read_bytes(), payload)
        with patch("urllib.request.urlopen") as request:
            self.assertEqual(verified_download(spec, self.root), path)
            request.assert_not_called()

    def test_bad_checksum_is_not_installed(self):
        spec = {"url": "https://example.invalid/archive.zip", "sha256": "0" * 64}
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"bad")):
            with self.assertRaises(StudioError):
                verified_download(spec, self.root)
        self.assertFalse((self.root / "archive.zip").exists())
        self.assertEqual(list(self.root.glob(".download-*")), [])

    def test_cached_templates_do_not_redownload_gigabyte_archive(self):
        destination = self.root / ".studio/tools/godot/test"
        destination.mkdir(parents=True)
        (destination / "binary").write_bytes(b"tool")
        target = self.root / ".studio/tools/godot/templates"
        target.mkdir(parents=True)
        hashes = {}
        for name in ("linux_release.x86_64", "macos.zip"):
            (target / name).write_bytes(b"template")
            hashes[name] = hashlib.sha256(b"template").hexdigest()
        atomic_json(target / "manifest.json", {
            "version": "test", "archive_sha256": "pinned", "files": hashes,
        })
        record = {"version": "test", "templates": {"sha256": "pinned"}}
        with patch("pipeline.tools.tool_spec", return_value=(record, {"executable": "binary"})):
            with patch("pipeline.tools.verified_download") as download:
                result = fetch_tool("godot", templates=True, root=self.root)
                self.assertTrue(result["templates"])
                download.assert_not_called()

    def test_zip_cannot_escape_destination(self):
        path = self.root / "archive.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr("../escape", "no")
        with self.assertRaises(StudioError):
            extract_zip(path, self.root / "destination")

    def test_log_output_is_bounded(self):
        import sys
        result = run_process([sys.executable, "-c", "print('x' * 50000)"], self.root, 5,
                             self.root / "output.log", max_log_bytes=100)
        self.assertEqual(result["reason"], "log_limit")
        self.assertEqual((self.root / "output.log").stat().st_size, 100)
