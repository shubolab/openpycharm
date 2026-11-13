import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("openpycharm_native_probe", ROOT / "scripts/native_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class NativeProbeBoundaryTests(unittest.TestCase):
    def test_existing_isolated_profile_is_preserved_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile with spaces"
            properties = probe.prepare_profile(profile, [])
            properties.write_text(properties.read_text() + "# existing user state must remain\n", encoding="utf-8")
            before = properties.read_bytes()
            self.assertEqual(probe.prepare_profile(profile, []), properties)
            self.assertEqual(properties.read_bytes(), before)

    def test_existing_profile_cannot_redirect_to_shared_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            properties = probe.prepare_profile(profile, [])
            data = properties.read_text().replace((profile / "config").as_posix(), (root / "shared-config").as_posix())
            properties.write_text(data, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "isolated"):
                probe.prepare_profile(profile, [])
            self.assertEqual(properties.read_text(), data)
            self.assertFalse((root / "shared-config").exists())

    def test_profile_inside_application_or_fixture_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for forbidden in (root / "application", root / "fixture"):
                with self.subTest(forbidden=forbidden):
                    with self.assertRaisesRegex(ValueError, "outside"):
                        probe.prepare_profile(forbidden / "profile", [forbidden])
                    self.assertFalse(forbidden.exists())

    def test_smart_native_report_must_include_sdk_and_test_producer(self):
        report = self.good_report()
        self.assertEqual(probe.validate_report(report, "current")["status"], "pass")
        invalid_cases = (
            (lambda item: item.update(invocationId="stale"), "another invocation"),
            (lambda item: item.update(pluginEnabled=False), "startup"),
            (lambda item: item.update(isDumbAtCapture=True), "smart"),
            (lambda item: item["files"][0].update(excluded=True), "active project content"),
            (lambda item: item["files"][0]["pythonSdk"]["classRootFiles"][0].update(valid=False), "Python SDK"),
            (lambda item: item["files"][0].update(fileLightProducers=[]), "test detection"),
        )
        for mutate, message in invalid_cases:
            with self.subTest(reason=message):
                candidate = copy.deepcopy(report)
                mutate(candidate)
                with self.assertRaisesRegex(ValueError, message):
                    probe.validate_report(candidate, "current")

    def test_windows_java_argument_file_keeps_unicode_and_rejects_newlines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "java.args"
            probe._write_java_arguments(path, ["--class-path", "C:\\工作 空间\\lib", "test🚀"])
            self.assertIn("工作 空间", path.read_text(encoding="utf-8"))
            self.assertIn("test🚀", path.read_text(encoding="utf-8"))
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "line break"):
                probe._write_java_arguments(path, ["one\n-Dunwanted=true"])
            self.assertEqual(path.read_bytes(), before)

    @staticmethod
    def good_report():
        return {
            "invocationId": "current", "pluginId": probe.PLUGIN_ID, "pluginEnabled": True,
            "isDumbAtCapture": False, "isReadAccessAllowed": True,
            "modules": [{"name": "fixture"}],
            "files": [{"module": "fixture", "inContent": True, "excluded": False,
                       "pythonSdk": {"version": "Python 3.14", "classRootFiles": [{"valid": True, "exists": True}]},
                       "testFileBasedOnSettings": True,
                       "fileLightProducers": [{"lightConfiguration": {"type": "tests"}}]}],
        }


if __name__ == "__main__":
    unittest.main()
