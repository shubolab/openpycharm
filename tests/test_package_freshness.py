import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("framework_integration_packager", SCRIPTS / "package.py")
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)
import build_framework_plugin
import build_http_plugin
import local_product
import provenance
import repairs


class ProductAssemblyFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "owned-source"
        inputs = {
            "scripts/package.py": "# owned assembly source\n",
            "product/platform.lock.json": "{}\n",
            "plugins/http-client/src/Client.kt": "class Client\n",
            "plugins/frameworks/src/Framework.java": "class Framework {}\n",
            "requirements-build.txt": "Pillow==12.1.0\n",
            "LICENSE": "owned license\n",
            "NOTICE": "owned notice\n",
        }
        for relative, content in inputs.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.framework_source = self.root / "plugins/frameworks/src/Framework.java"
        self.sdk = self.base / "authenticated-sdk/pycharm"
        (self.sdk / "bin").mkdir(parents=True)
        (self.sdk / "license").mkdir()
        (self.sdk / "bin/pycharm64.exe").write_bytes(b"fake launcher; never executed")
        (self.sdk / "product-info.json").write_text(json.dumps({
            "name": "PyCharm", "productCode": "PC", "version": "2026.1.4", "buildNumber": "261.26222.68"}))
        (self.sdk.parent / ".openpycharm-platform.json").write_text('{"schema":1}\n')
        self.output = self.root / "build/product/OpenPyCharm"
        self.http = self.make_plugin("http", "openpycharm-http.jar", b"compiled HTTP bytes")
        self.frameworks = self.make_plugin("frameworks", "frameworks.jar", b"compiled framework bytes")

    def make_plugin(self, name, jar_name, payload):
        directory = self.root / ".tools" / name / "plugin"
        jar = directory / "lib" / jar_name
        jar.parent.mkdir(parents=True)
        jar.write_bytes(payload)
        return directory, {"pluginDirectory": str(directory), "jarSha256": hashlib.sha256(payload).hexdigest()}

    def assemble(self, mutate_after_compile=False):
        def compiled_framework(*args, **kwargs):
            # These JAR bytes/receipts already exist. Simulate an editor changing
            # an input after compilation but before the product source snapshot.
            if mutate_after_compile:
                self.framework_source.write_text("class Framework { /* new source */ }\n", encoding="utf-8")
            return self.frameworks

        pillow = ModuleType("PIL")
        pillow.__version__ = "test-only"
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(packager, "ROOT", self.root))
            stack.enter_context(patch.object(packager, "PIN_PATH", self.root / "product/platform.lock.json"))
            stack.enter_context(patch.object(packager, "validate_cached", return_value=self.sdk))
            stack.enter_context(patch.object(packager.shutil, "disk_usage", return_value=SimpleNamespace(free=128 * 1024**3)))
            stack.enter_context(patch.object(packager, "source_inputs", side_effect=lambda: provenance.source_inputs(self.root)))
            stack.enter_context(patch.object(packager, "verify_source_inputs", side_effect=lambda manifest: provenance.verify_source_inputs(manifest, self.root), create=True))
            stack.enter_context(patch.object(build_http_plugin, "build", return_value=self.http[1]))
            stack.enter_context(patch.object(build_framework_plugin, "build_plugin", side_effect=compiled_framework))
            stack.enter_context(patch.object(repairs, "apply", return_value={}))
            stack.enter_context(patch.object(local_product, "apply", return_value={}))
            stack.enter_context(patch.object(packager, "brand_resources", return_value={}))
            stack.enter_context(patch.object(packager, "write_paths", return_value={}))
            stack.enter_context(patch.object(packager, "brand_product_info", side_effect=lambda info, version: {**info, "name": "OpenPyCharm", "openpycharmVersion": version}))
            stack.enter_context(patch.object(packager.subprocess, "check_output", return_value="test-source-commit\n"))
            stack.enter_context(patch.object(packager.subprocess, "run", side_effect=AssertionError("Native and signing processes must not run in this unit test")))
            stack.enter_context(patch.dict(sys.modules, {"PIL": pillow}))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return packager.assemble(self.sdk, "windows-x64", "0.1.0-dev.2", self.output)

    def test_stable_sources_promote_both_receipted_plugin_payloads(self):
        original = provenance.source_inputs(self.root)
        self.assertEqual(self.assemble(), self.output)
        report = json.loads((self.output / "openpycharm-build.json").read_text())
        self.assertEqual(report["sourceInputs"], original)
        self.assertEqual({entry["id"] for entry in report["plugins"]}, {"dev.openpycharm.http", "dev.openpycharm.frameworks"})
        self.assertEqual(len(provenance.verify_product_plugins(report, self.output)), 2)
        provenance.verify_source_inputs(report, self.root)

    def test_edit_after_plugin_compilation_rejects_product_before_promotion(self):
        with self.assertRaisesRegex(ValueError, "stale.*changed.*plugins/frameworks/src/Framework.java"):
            self.assemble(mutate_after_compile=True)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.framework_source.read_text(), "class Framework { /* new source */ }\n")
        self.assertFalse(any(self.output.parent.glob("assemble-*")))


if __name__ == "__main__":
    unittest.main()
