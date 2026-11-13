import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
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
            # Windows tempfile paths can contain 8.3 aliases; prepare_profile
            # writes canonical paths. Mutate that actual value, not an alias.
            root = Path(directory).resolve()
            profile = root / "profile"
            properties = probe.prepare_profile(profile, [])
            original = properties.read_text(encoding="utf-8")
            isolated = (profile / "config").as_posix()
            self.assertIn(isolated, original)
            data = original.replace(isolated, (root / "shared-config").as_posix())
            self.assertNotEqual(data, original)
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

    def test_http_report_requires_actual_bundled_identity_registration_and_current_location(self):
        with tempfile.TemporaryDirectory() as directory:
            contents = Path(directory) / "relocated app/Contents"
            plugin = {"id": "dev.openpycharm.http", "version": "0.1.0-dev.2", "jarSha256": "a" * 64,
                      "path": "third-party-plugins/openpycharm-http", "jar": "third-party-plugins/openpycharm-http/lib/openpycharm-http.jar"}
            report = {"invocationId": "current", "pluginId": probe.PLUGIN_ID, "pluginEnabled": True,
                      "isDispatchThread": False, "isDumbAtCapture": False, "isReadAccessAllowed": True,
                      "inspectionMode": "application-registration-and-default-project-in-memory-PSI",
                      "httpPlugin": {**plugin, "enabled": True, "bundled": True,
                                     "path": str(contents / plugin["path"]), "jar": str(contents / plugin["jar"])},
                      "fileType": "dev.openpycharm.http.lang.HttpRequestFileType", "language": "OpenPyCharmHttpRequest",
                      "parserDefinition": "dev.openpycharm.http.lang.HttpRequestParserDefinition",
                      "syntaxHighlighter": "dev.openpycharm.http.lang.HttpRequestSyntaxHighlighter",
                      "actions": {"OpenPyCharm.Http.RunRequest": "dev.openpycharm.http.RunHttpRequestAction",
                                  "OpenPyCharm.Http.RunAllRequests": "dev.openpycharm.http.RunAllHttpRequestsAction",
                                  "OpenPyCharm.Http.SaveResponse": "dev.openpycharm.http.SaveHttpResponseAction"},
                      "servicesContributor": ["dev.openpycharm.http.HttpServicesContributor"], "tokens": ["METHOD", "URL"]}
            layout = SimpleNamespace(contents=contents)
            self.assertEqual(probe.validate_http_report(report, "current", layout, {"plugins": [plugin]})["status"], "pass")
            mutations = (
                lambda item: item.update(invocationId="stale"),
                lambda item: item.update(isDispatchThread=True),
                lambda item: item["httpPlugin"].update(jarSha256="b" * 64),
                lambda item: item["httpPlugin"].update(path=str(Path(directory) / "old app/Contents" / plugin["path"])),
                lambda item: item["httpPlugin"].update(bundled=False),
                lambda item: item.update(language="TEXT"),
                lambda item: item.update(parserDefinition=None),
                lambda item: item.update(actions={}),
                lambda item: item.update(servicesContributor=[]),
            )
            for mutate in mutations:
                candidate = copy.deepcopy(report)
                mutate(candidate)
                with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                    probe.validate_http_report(candidate, "current", layout, {"plugins": [plugin]})

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
