import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from runtime_smoke import log_observation, run_smoke, startup_ready


class RuntimeStartupEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.profile = Path("/smoke-profile")
        self.project = self.profile / "project/hello-python"
        self.build = "261.26222.68"
        self.log = "\n".join([
            "2026-11-13 10:11:12,123 [  1] INFO - #AppStarter - IDE STARTED",
            f"2026-11-13 10:11:12,123 [  1] INFO - #AppStarter - IDE: OpenPyCharm (build #PC-{self.build}, test)",
            "2026-11-13 10:11:12,123 [  1] INFO - #AppStarter - JVM options: [-Didea.vendor.name=OpenPyCharm, -Dide.native.launcher=true]",
            "2026-11-13 10:11:12,123 [  1] INFO - #AppStarter - Loaded bundled plugins: Python Community Edition (261), Git (261), Terminal (261)",
            *(f"    idea.{name}.path={self.profile / name}" for name in ("config", "system", "plugins", "log")),
            f"2026-11-13 10:11:12,123 [  1] INFO - #AppStarter - args: {self.project}",
        ])

    def observe(self, text=None):
        return log_observation(self.log if text is None else text, self.profile, self.project, self.build)

    def test_launch_request_does_not_claim_project_trust_or_open_completion(self):
        observed = self.observe()
        self.assertTrue(startup_ready(observed))
        self.assertTrue(observed["projectOpenRequested"])
        self.assertFalse(observed["projectOpenedInLog"])

    def test_every_identity_plugin_path_and_project_check_is_required(self):
        observed = self.observe()
        for key in ("ideStarted", "productIdentity", "vendorIdentity", "projectOpenRequested"):
            candidate = copy.deepcopy(observed)
            candidate.pop(key)
            with self.subTest(missing=key):
                self.assertFalse(startup_ready(candidate))
        for section in ("loadedPlugins", "isolatedPaths"):
            for name in observed[section]:
                candidate = copy.deepcopy(observed)
                candidate[section].pop(name)
                with self.subTest(missing=f"{section}.{name}"):
                    self.assertFalse(startup_ready(candidate))
            candidate = copy.deepcopy(observed)
            candidate[section] = {}
            self.assertFalse(startup_ready(candidate))

    def test_other_products_builds_and_vendor_prefixes_cannot_pass(self):
        alternatives = [
            self.log.replace("IDE: OpenPyCharm", "IDE: PyCharm"),
            self.log.replace("build #PC-", "build #PY-"),
            self.log.replace(f"build #PC-{self.build},", f"build #PC-{self.build}.1,"),
            self.log.replace("vendor.name=OpenPyCharm,", "vendor.name=OpenPyCharmOther,"),
        ]
        for text in alternatives:
            with self.subTest(text=text):
                self.assertFalse(startup_ready(self.observe(text)))

    def test_namesake_plugins_or_reference_configuration_do_not_pass(self):
        for name in ("Python Community Edition", "Git", "Terminal"):
            text = self.log.replace(f"{name} (261)", f"{name} Extra (261)")
            with self.subTest(plugin=name):
                self.assertFalse(startup_ready(self.observe(text)))
        for name in ("config", "system", "plugins", "log"):
            text = self.log.replace(f"idea.{name}.path={self.profile / name}", f"idea.{name}.path=/reference/PyCharm/{name}")
            with self.subTest(path=name):
                self.assertFalse(startup_ready(self.observe(text)))

    def test_errors_fail_readiness_and_evidence_lists_are_bounded(self):
        errors = [f"2026-11-13 10:11:12,123 [  1] {level} - #Test - problem {number}"
                  for number, level in enumerate(["ERROR", "SEVERE"] * 40)]
        warnings = [f"2026-11-13 10:11:12,123 [  1] WARN - #Test - warning {number}" for number in range(30)]
        observed = self.observe(self.log + "\n" + "\n".join(errors + warnings))
        self.assertEqual(observed["errorCount"], 80)
        self.assertEqual(len(observed["errors"]), 50)
        self.assertEqual(observed["warningCount"], 30)
        self.assertEqual(len(observed["warnings"]), 20)
        self.assertFalse(startup_ready(observed))

    def test_warning_or_error_word_in_info_message_is_not_hidden_as_a_failure(self):
        text = self.log + "\n2026-11-13 10:11:12,123 [  1] WARN - #Test - upstream warning"
        text += "\n2026-11-13 10:11:12,123 [  1] INFO - #Test - documentation mentions ERROR - formatting"
        observed = self.observe(text)
        self.assertTrue(startup_ready(observed))
        self.assertEqual(observed["warningCount"], 1)
        self.assertEqual(observed["errorCount"], 0)

    def test_windows_logged_path_slashes_and_case_are_normalized(self):
        profile = Path("C:/SmokeProfile")
        project = profile / "project/hello-python"
        text = self.log.replace(str(self.profile), "c:\\smokeprofile")
        with patch("runtime_smoke.platform.system", return_value="Windows"):
            observed = log_observation(text, profile, project, self.build)
        self.assertTrue(startup_ready(observed))

    def test_existing_profile_is_rejected_before_any_process_or_fixture_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "OpenPyCharm.app"
            contents = app / "Contents"
            (contents / "MacOS").mkdir(parents=True)
            (contents / "MacOS/pycharm").write_bytes(b"test launcher, never executed")
            (contents / "openpycharm-build.json").write_text(json.dumps({"name": "OpenPyCharm", "upstreamProduct": "PC"}))
            profile = root / "existing-profile"
            profile.mkdir()
            sentinel = profile / "idea.log"
            sentinel.write_text("old evidence")
            with patch("runtime_smoke.platform.system", return_value="Darwin"), patch("runtime_smoke.subprocess.Popen") as popen:
                with self.assertRaisesRegex(ValueError, "new profile"):
                    run_smoke(app, profile)
                popen.assert_not_called()
            self.assertEqual(list(profile.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(), "old evidence")

    def test_observation_intervals_are_bounded_before_launch(self):
        for timeout, observe in ((9, 10), (301, 10), (120, 0), (120, 61)):
            with self.subTest(timeout=timeout, observe=observe), patch("runtime_smoke.platform.system", return_value="Darwin"):
                with self.assertRaisesRegex(ValueError, "timeout"):
                    run_smoke(Path("not-an-application"), timeout=timeout, observe=observe)


if __name__ == "__main__":
    unittest.main()
