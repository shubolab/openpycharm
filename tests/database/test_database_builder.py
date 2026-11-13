import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_database_plugin as builder
import provision_database_drivers as provisioner


class DatabaseBuildControls(unittest.TestCase):
    def test_missing_driver_fails_closed_without_network_or_process(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(provisioner.urllib.request, "urlopen", side_effect=AssertionError("no implicit network")):
                with self.assertRaisesRegex(ValueError, "does not download"):
                    builder.driver_artifacts([Path(directory)])

    def test_cache_requires_exact_hash_size_and_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / "sources"
            cache = root / "cache"
            plugin.mkdir()
            cache.mkdir()
            data = b"owned JDBC test artifact"
            jar = cache / "driver-1.0.jar"
            item = {"name": jar.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            (plugin / "drivers.lock.json").write_text(json.dumps({"artifacts": [item]}))
            jar.write_bytes(data)
            with patch.object(builder, "SOURCE", plugin):
                self.assertEqual(builder.driver_artifacts([cache])[0][1], jar.resolve())
                jar.write_bytes(b"x" * len(data))
                with self.assertRaisesRegex(ValueError, "Missing authenticated"):
                    builder.driver_artifacts([cache])
                jar.unlink()
                target = root / "outside.jar"
                target.write_bytes(data)
                try:
                    jar.symlink_to(target)
                except OSError as error:
                    self.skipTest(str(error))
                with self.assertRaisesRegex(ValueError, "Missing authenticated"):
                    builder.driver_artifacts([cache])

    def test_provisioning_pin_cannot_change_origin_coordinate_or_name(self):
        item = json.loads((builder.SOURCE / "drivers.lock.json").read_text())["artifacts"][0]
        self.assertEqual(provisioner.artifact_url(item), item["url"])
        for change in ({"url": item["url"].replace("repo.maven.apache.org", "foreign.example")}, {"name": "../escape.jar"}, {"size": 2**40}, {"sha256": "not-a-hash"}, {"group": "../../escape"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                provisioner.artifact_url({**item, **change})

    def test_provisioning_rejects_redirect_before_following_it(self):
        response = type("Response", (), {"close": lambda self: None})()
        with self.assertRaisesRegex(ValueError, "does not follow redirects"):
            provisioner.NoRedirect().redirect_request(None, response, 302, "moved", {}, "http://foreign.example/driver.jar")

    def test_product_xml_injection_rejected_before_sdk_access(self):
        with patch.object(builder, "sdk_layout", side_effect=AssertionError("no SDK access")):
            with self.assertRaisesRegex(ValueError, "release version"):
                builder.build_plugin(Path("missing"), "1.0</version><id>wrong</id>")

    def test_descriptor_identity_and_version_must_match(self):
        original = (builder.SOURCE / "resources/META-INF/plugin.xml").read_bytes()
        self.assertIn(b"<version>0.2.0-test</version>", builder.descriptor(original, "0.2.0-test"))
        with self.assertRaisesRegex(ValueError, "identity/version"):
            builder.descriptor(original.replace(b"dev.openpycharm.database", b"foreign.database"), "0.2.0-test")

    def test_replacement_lgpl_driver_is_separate_and_matching_source_is_pinned(self):
        artifacts = json.loads((builder.SOURCE / "drivers.lock.json").read_text())["artifacts"]
        maria = [item for item in artifacts if item["artifact"] == "mariadb-java-client"]
        self.assertEqual({item["role"] for item in maria}, {"driver", "source"})
        self.assertEqual(len({item["version"] for item in maria}), 1)
        self.assertTrue((builder.SOURCE / "legal/LGPL-2.1.txt").is_file())
        self.assertTrue((builder.SOURCE / "legal/GPL-2.0.txt").is_file())

    def test_disposable_sql_fixture_is_replayable(self):
        import sqlite3
        sql = (ROOT / "fixtures/database/inventory.sql").read_text()
        with sqlite3.connect(":memory:") as connection:
            connection.executescript(sql)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT name FROM products WHERE sku='PY-001'").fetchone()[0], "Python workbook")


if __name__ == "__main__":
    unittest.main()
