import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from provenance import verify_product_plugins


class DatabasePayloadReceipts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.contents = Path(self.temp.name)
        self.directory = self.contents / "third-party-plugins/openpycharm-database"
        files = {}
        for name in ("lib/database.jar", "lib/sqlite.jar", "lib/postgresql.jar", "lib/mariadb.jar", "legal/mariadb-sources.jar"):
            path = self.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("owned " + name).encode())
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.entry = {"id": "dev.openpycharm.database", "name": "OpenPyCharm Database", "version": "0.1.0-dev.3",
                      "path": self.directory.relative_to(self.contents).as_posix(),
                      "jar": (self.directory / "lib/database.jar").relative_to(self.contents).as_posix(),
                      "jarSha256": files["lib/database.jar"], "files": files, "build": {"files": copy.deepcopy(files)}}

    def verify(self, entry=None):
        return verify_product_plugins({"plugins": [entry or self.entry]}, self.contents)

    def test_entire_replaceable_driver_and_source_set_verifies(self):
        self.assertEqual(len(self.verify()), 1)

    def test_driver_mutation_and_missing_lgpl_source_are_rejected(self):
        path = self.directory / "lib/sqlite.jar"
        original = path.read_bytes()
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "payload digest"):
            self.verify()
        path.write_bytes(original)
        (self.directory / "legal/mariadb-sources.jar").unlink()
        with self.assertRaisesRegex(ValueError, "bounded regular file"):
            self.verify()

    def test_extra_executable_plugin_payload_cannot_hide_outside_receipt(self):
        (self.directory / "lib/foreign.jar").write_bytes(b"unreceipted executable")
        with self.assertRaisesRegex(ValueError, "unreceipted"):
            self.verify()

    def test_database_cannot_fall_back_to_primary_jar_only_validation(self):
        entry = copy.deepcopy(self.entry)
        del entry["files"]
        with self.assertRaisesRegex(ValueError, "complete driver/source"):
            self.verify(entry)
        entry = copy.deepcopy(self.entry)
        del entry["files"]["legal/mariadb-sources.jar"]
        with self.assertRaisesRegex(ValueError, "authenticated build"):
            self.verify(entry)

    def test_path_traversal_and_symlink_driver_substitution_are_rejected(self):
        for name in ("../outside.jar", "/outside.jar", "lib/../outside.jar", "lib\\outside.jar"):
            entry = copy.deepcopy(self.entry)
            digest = entry["files"].pop("lib/sqlite.jar")
            entry["files"][name] = digest
            entry["build"]["files"] = copy.deepcopy(entry["files"])
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, "paths must stay"):
                self.verify(entry)
        target = self.contents / "outside.jar"
        driver = self.directory / "lib/sqlite.jar"
        target.write_bytes(driver.read_bytes())
        driver.unlink()
        try:
            driver.symlink_to(target)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
