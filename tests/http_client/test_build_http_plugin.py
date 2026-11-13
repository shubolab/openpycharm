import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("http_plugin_builder", ROOT / "scripts/build_http_plugin.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class HttpPluginBuildBoundaries(unittest.TestCase):
    def test_compiler_is_taken_only_from_hash_matching_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / "plugin"
            plugin.mkdir()
            data = b"pinned compiler artifact"
            jar = root / "cache/compiler.jar"
            jar.parent.mkdir()
            jar.write_bytes(data)
            (plugin / "compiler.lock.json").write_text(json.dumps({"artifacts": [{
                "name": jar.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}]}))
            with patch.object(builder, "PLUGIN", plugin):
                artifacts, _ = builder.compiler_classpath([jar.parent])
                self.assertEqual(artifacts, [jar.resolve()])
                jar.write_bytes(b"changed compiler bytes!")
                with self.assertRaisesRegex(ValueError, "does not download"):
                    builder.compiler_classpath([jar.parent])

    def test_missing_compiler_is_not_implicitly_downloaded(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(builder.subprocess, "run", side_effect=AssertionError("No compiler/download process permitted")):
                with self.assertRaisesRegex(ValueError, "Missing authenticated cached compiler"):
                    builder.compiler_classpath([Path(directory)])

    def test_invalid_descriptor_version_is_rejected_before_sdk_or_output_access(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with patch.object(builder, "authenticated_layout", side_effect=AssertionError("No SDK access permitted")):
                with self.assertRaisesRegex(ValueError, "release version"):
                    builder.build(Path("missing-sdk"), output, "1.0</version><id>wrong</id>")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
