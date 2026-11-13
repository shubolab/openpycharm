import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from product import brand_application_info, brand_plist, brand_product_info, rewrite_jar, seal_python_helper_directories, write_paths


class ProductTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32" or getattr(os, "geteuid", lambda: 0)() == 0,
                     "Requires macOS/Linux filesystem permissions and a normal user")
    def test_native_helper_import_keeps_bundle_immutable_and_user_bytecode_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            contents = root / "build/owned/Contents"
            helpers = contents / "plugins/python-ce/helpers"
            helpers.mkdir(parents=True)
            (helpers / "sealed_helper.py").write_text("VALUE = 42\n")
            project = root / "project"
            project.mkdir()
            (project / "user_module.py").write_text("VALUE = 21\n")
            with patch("product.ROOT", root):
                report = seal_python_helper_directories(contents)
            env = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}}
            env["PYTHONPATH"] = os.pathsep.join([str(helpers), str(project)])
            result = subprocess.run([sys.executable, "-c",
                                     "import sealed_helper, user_module; print(sealed_helper.VALUE + user_module.VALUE)"],
                                    env=env, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), "63")
            self.assertFalse((helpers / "__pycache__").exists())
            self.assertTrue((project / "__pycache__").is_dir())
            self.assertFalse(report["userPythonEnvironmentModified"])

    def test_helper_permission_change_rejects_source_sdk_and_linked_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sdk = root / "sdk/Contents"
            helper = sdk / "plugins/python-ce/helpers"
            helper.mkdir(parents=True)
            with patch("product.ROOT", root), self.assertRaises(ValueError):
                seal_python_helper_directories(sdk)
            self.assertTrue(helper.stat().st_mode & 0o200)
            if sys.platform != "win32":
                owned = root / "build/owned/Contents"
                owned_helper = owned / "plugins/python-ce/helpers"
                owned_helper.mkdir(parents=True)
                (owned_helper / "escape").symlink_to(helper, target_is_directory=True)
                with patch("product.ROOT", root), self.assertRaises(ValueError):
                    seal_python_helper_directories(owned)
                self.assertTrue(owned_helper.stat().st_mode & 0o200)
                self.assertTrue(helper.stat().st_mode & 0o200)

    def test_branding_keeps_compatibility_and_one_override_per_key(self):
        source = {"productCode": "PC", "version": "2026.1.4", "buildNumber": "261.26222.68",
                  "bundledPlugins": ["PythonCore", "Git4Idea"],
                  "launch": [{"additionalJvmArguments": ["-Didea.vendor.name=JetBrains", "-Didea.paths.selector=PyCharmCE", "-Didea.platform.prefix=PyCharmCore"],
                              "customCommands": [{"commands": ["thinClient"]}]}]}
        original = copy.deepcopy(source)
        result = brand_product_info(source, "0.1.0-dev.1")
        self.assertEqual(source, original)
        self.assertEqual(result["buildNumber"], source["buildNumber"])
        self.assertEqual(result["bundledPlugins"], source["bundledPlugins"])
        args = result["launch"][0]["additionalJvmArguments"]
        self.assertEqual([a for a in args if a.startswith("-Didea.vendor.name=")], ["-Didea.vendor.name=OpenPyCharm"])
        self.assertIn("-Didea.platform.prefix=PyCharmCore", args)
        self.assertNotIn("customCommands", result["launch"][0])
        with self.assertRaises(ValueError):
            brand_product_info({**source, "productCode": "PY"}, "0.1.0")

    def test_application_resources_preserve_python_essential_plugin(self):
        header = b'<!-- Copyright JetBrains; Apache-2.0. -->\n'
        xml = b'<?xml version="1.0" encoding="UTF-8"?>\n' + header + b'<component xmlns="http://jetbrains.org/intellij/schema/application-info"><names product="PyCharm" fullname="PyCharm" edition="Community"/><build number="PC-261.26222.68"/><essential-plugin>PythonCore</essential-plugin></component>'
        branded = brand_application_info(xml)
        self.assertIn(header, branded)
        self.assertIn(b'Modified by OpenPyCharm contributors', branded)
        self.assertEqual(branded.count(b'<?xml'), 1)
        result = ET.fromstring(branded)
        ns = {"i": "http://jetbrains.org/intellij/schema/application-info"}
        self.assertEqual(result.find("i:names", ns).get("product"), "OpenPyCharm")
        self.assertEqual(result.find("i:essential-plugin", ns).text, "PythonCore")
        self.assertEqual(result.find("i:build", ns).get("number"), "PC-261.26222.68")

    def test_rewritten_jar_keeps_notices_and_drops_stale_offset_trailer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.jar"
            with zipfile.ZipFile(path, "w") as jar:
                jar.writestr("__index__", b"old-index")
                jar.writestr("NOTICE", b"upstream copyright")
                jar.writestr("info.xml", b"old")
                jar.comment = b"\x04\xff\xff\xff\x00"
            rewrite_jar(path, {"info.xml": b"new"})
            with zipfile.ZipFile(path) as jar:
                self.assertEqual(jar.read("NOTICE"), b"upstream copyright")
                self.assertEqual(jar.read("info.xml"), b"new")
                self.assertEqual(jar.comment, b"")

    def test_paths_do_not_share_reference_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            contents = Path(directory)
            (contents / "bin").mkdir()
            (contents / "bin/idea.properties").write_text("# upstream\n")
            paths = write_paths(contents, True)
            self.assertEqual(len(set(paths.values())), 4)
            self.assertTrue(all("OpenPyCharm" in path for path in paths.values()))
            self.assertTrue((contents / "bin/idea.properties").read_text().startswith("# upstream"))

    def test_bundle_identity_and_python_file_association(self):
        original = {"CFBundleName": "PyCharm", "CFBundleIdentifier": "com.jetbrains.pycharm.ce", "CFBundleExecutable": "pycharm",
                    "CFBundleDocumentTypes": [{"CFBundleTypeExtensions": ["py"]}], "NSCameraUsageDescription": "PyCharm camera"}
        result = brand_plist(original, "0.1.0-dev.1")
        self.assertEqual(result["CFBundleIdentifier"], "dev.openpycharm.ide")
        self.assertEqual(result["CFBundleExecutable"], "pycharm")
        self.assertEqual(result["CFBundleDocumentTypes"], original["CFBundleDocumentTypes"])
        self.assertEqual(result["CFBundleURLTypes"][0]["CFBundleURLSchemes"], ["openpycharm"])


if __name__ == "__main__":
    unittest.main()
