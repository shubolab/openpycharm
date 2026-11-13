import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import installers
import runtime_smoke
from provenance import source_inputs, verify_product_plugins


class PluginReceiptControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.contents = self.root / "build/product"
        self.jar = self.contents / "third-party-plugins/http/lib/client.jar"
        self.jar.parent.mkdir(parents=True)
        self.jar.write_bytes(b"authenticated plugin payload")
        self.plugin = {"id": "dev.openpycharm.http", "name": "OpenPyCharm HTTP Client", "version": "0.1.0-dev.2",
                       "path": "third-party-plugins/http", "jar": self.jar.relative_to(self.contents).as_posix(),
                       "jarSha256": hashlib.sha256(self.jar.read_bytes()).hexdigest()}
        self.manifest = {"schema": 1, "name": "OpenPyCharm", "version": "0.1.0-dev.2", "target": "windows-x64",
                         "upstreamProduct": "PC", "sourceInputs": source_inputs(), "plugins": [self.plugin]}

    def test_installer_rejects_mutated_plugin_even_when_source_and_metadata_still_match(self):
        (self.contents / "openpycharm-build.json").write_text(json.dumps(self.manifest))
        (self.contents / "product-info.json").write_text(json.dumps({"name": "OpenPyCharm", "openpycharmVersion": "0.1.0-dev.2"}))
        (self.contents / "bin").mkdir()
        for name in ("pycharm64.exe", "openpycharm.bat"):
            (self.contents / "bin" / name).write_bytes(b"never executed")
        with patch.object(installers, "ROOT", self.root):
            self.assertEqual(installers.validate_product(self.contents, "windows-x64", "0.1.0-dev.2")[0], self.contents)
            self.jar.write_bytes(b"changed executable plugin payload")
            with self.assertRaisesRegex(ValueError, "JAR digest"):
                installers.validate_product(self.contents, "windows-x64", "0.1.0-dev.2")

    def test_startup_rejects_mutated_plugin_before_creating_a_profile_or_process(self):
        (self.contents / "openpycharm-build.json").write_text(json.dumps(self.manifest))
        self.jar.write_bytes(b"changed executable plugin payload")
        profile = self.root / "profile"
        with patch.object(runtime_smoke.platform, "system", return_value="Windows"), patch.object(runtime_smoke.subprocess, "Popen") as process:
            with self.assertRaisesRegex(ValueError, "JAR digest"):
                runtime_smoke.run_smoke(self.contents, profile)
            process.assert_not_called()
        self.assertFalse(profile.exists())

    def test_unowned_paths_duplicate_receipts_and_directory_payloads_cannot_be_hashed(self):
        for mutation in ({"jar": "../outside.jar"}, {"jar": "/outside.jar"}, {"path": "."},
                         {"jar": "third-party-plugins/http/../outside.jar"}, {"jar": "third-party-plugins/http/lib"},
                         {"jar": "C:\\outside.jar"}):
            candidate = {"plugins": [{**self.plugin, **mutation}]}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_product_plugins(candidate, self.contents)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify_product_plugins({"plugins": [self.plugin, copy.deepcopy(self.plugin)]}, self.contents)

    def test_a_symlink_cannot_substitute_for_the_receipted_plugin(self):
        original = self.jar.read_bytes()
        outside = self.root / "outside.jar"
        outside.write_bytes(original)
        self.jar.unlink()
        try:
            self.jar.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"Host cannot create test symlinks: {error}")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            verify_product_plugins(self.manifest, self.contents)
        self.assertEqual(outside.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
