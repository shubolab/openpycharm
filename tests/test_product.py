import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from product import brand_application_info, brand_plist, brand_product_info, rewrite_jar, write_paths


class ProductTests(unittest.TestCase):
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
