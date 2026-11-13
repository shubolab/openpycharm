"""Guard the distribution boundary: only a verified OSS Python SDK is reusable."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("openpycharm_bootstrap", ROOT / "scripts/bootstrap.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pin = json.loads(bootstrap.PIN_PATH.read_text(encoding="utf-8"))
        self.sdk = self.root / "cached" / "PyCharm.app"
        self.info = self.sdk / "Contents/Resources/product-info.json"
        self.info.parent.mkdir(parents=True)
        self.metadata = {key: self.pin[key] for key in ("version", "productCode", "buildNumber")}
        self.metadata.update(launch=[{"os": "macOS", "arch": "aarch64"}], bundledPlugins=["PythonCore"])
        self.write_metadata()

    def write_metadata(self):
        self.info.write_text(json.dumps(self.metadata), encoding="utf-8")

    def seal_cache(self):
        receipt = {
            "schema": 1,
            "target": "macos-arm64",
            "pinSha256": bootstrap.sha256(bootstrap.PIN_PATH),
            "archiveSha256": self.pin["targets"]["macos-arm64"]["sha256"],
            "treeSha256": bootstrap.tree_digest(self.sdk),
        }
        (self.sdk.parent / bootstrap.RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")
        return receipt

    def assert_cache_rejected(self):
        with self.assertRaises(ValueError):
            bootstrap.validate_cached(self.sdk.parent, self.pin, "macos-arm64")

    def test_cache_reuse_requires_valid_receipt_and_unchanged_sdk(self):
        self.assert_cache_rejected()
        self.seal_cache()
        self.assertEqual(bootstrap.validate_cached(self.sdk.parent, self.pin, "macos-arm64"), self.sdk)
        (self.sdk / "unrecorded-plugin.jar").write_bytes(b"added after authentication")
        self.assert_cache_rejected()

    def test_changed_receipt_cannot_select_another_archive_or_target(self):
        for key, value in (("archiveSha256", "0" * 64), ("target", "windows-x64"), ("pinSha256", "1" * 64)):
            with self.subTest(field=key):
                receipt = self.seal_cache()
                receipt[key] = value
                (self.sdk.parent / bootstrap.RECEIPT_NAME).write_text(json.dumps(receipt), encoding="utf-8")
                self.assert_cache_rejected()

    def test_product_identity_and_python_plugin_are_required_even_with_receipt(self):
        invalid = (
            {"productCode": "PY"},
            {"buildNumber": "261.0"},
            {"version": "2026.2"},
            {"bundledPlugins": []},
            {"bundledPlugins": ["PythonCore", "Pythonid"]},
            {"launch": [{"os": "macOS", "arch": "x86_64"}]},
        )
        original = dict(self.metadata)
        for changes in invalid:
            with self.subTest(changes=changes):
                self.metadata = dict(original, **changes)
                self.write_metadata()
                self.seal_cache()
                self.assert_cache_rejected()

    def test_changed_executable_mode_invalidates_cache(self):
        if os.name == "nt":
            self.skipTest("Windows does not preserve POSIX executable modes")
        launcher = self.sdk / "launcher"
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o755)
        self.seal_cache()
        launcher.chmod(0o644)
        self.assert_cache_rejected()

    def test_changed_symlink_target_invalidates_cache(self):
        link = self.sdk / "current"
        try:
            link.symlink_to("first")
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        self.seal_cache()
        link.unlink()
        link.symlink_to("second")
        self.assert_cache_rejected()

    def test_archive_bytes_must_match_the_pinned_size_and_digest(self):
        archive = self.root / "installer.zip"
        archive.write_bytes(b"authenticated input")
        asset = {"size": archive.stat().st_size, "sha256": bootstrap.sha256(archive)}
        bootstrap.authenticate_archive(archive, asset)
        archive.write_bytes(b"unauthenticated in!")
        with self.assertRaises(ValueError):
            bootstrap.authenticate_archive(archive, asset)

    def test_windows_archive_cannot_write_outside_staging_or_create_links(self):
        for index, name in enumerate(("../escaped", "/absolute", "C:/drive", "safe\\..\\escape", "link")):
            with self.subTest(member=name):
                archive = self.root / f"unsafe-{index}.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    entry = zipfile.ZipInfo(name)
                    if name == "link":
                        entry.create_system = 3
                        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    bundle.writestr(entry, "outside")
                staging = self.root / f"staging-{index}"
                staging.mkdir()
                with self.assertRaises(ValueError):
                    bootstrap.extract_windows(archive, staging)
        self.assertFalse((self.root / "escaped").exists())

    def test_windows_archive_accepts_a_product_at_archive_root(self):
        self.check_windows_archive_layout("")

    def test_windows_archive_accepts_a_wrapped_product_root(self):
        self.check_windows_archive_layout("pycharm-2026.1.4/")

    def check_windows_archive_layout(self, prefix):
        archive = self.root / "valid-windows-sdk.zip"
        metadata = b'{"productCode":"PC","version":"2026.1.4"}'
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(prefix + "product-info.json", metadata)
            bundle.writestr(prefix + "bin/pycharm64.exe", b"native launcher")
            bundle.writestr(prefix + "plugins/python-ce/lib/python-ce.jar", b"python plugin")
        staging = self.root / "valid-staging"
        staging.mkdir()
        sdk = bootstrap.extract_windows(archive, staging)
        self.assertEqual(sdk, staging / "pycharm")
        self.assertEqual((sdk / "product-info.json").read_bytes(), metadata)
        self.assertEqual((sdk / "bin/pycharm64.exe").read_bytes(), b"native launcher")
        self.assertEqual((sdk / "plugins/python-ce/lib/python-ce.jar").read_bytes(), b"python plugin")
        self.assertEqual(list(staging.iterdir()), [sdk])


if __name__ == "__main__":
    unittest.main()
