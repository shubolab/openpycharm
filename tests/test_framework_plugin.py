import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from framework_probe import assess


class FrameworkEvidenceTests(unittest.TestCase):
    @staticmethod
    def native_report():
        return {"invocationId": "current", "status": "pass", "userCodeExecuted": False,
                "configurations": [
                    {"typeId": name, "status": "pass", "factoryApplicable": True, "nativeRunRunner": "PythonRunner",
                     "nativeDebugRunner": "PyDebugRunner", "nativeState": "com.jetbrains.python.run.PythonScriptCommandLineState",
                     "nativeEditor": "com.jetbrains.python.run.configuration.PythonConfigurationFragmentedEditor",
                     "factoryClonePreservesSelection": True,
                     "argumentPersistence": "pass", "sdkHomePersisted": "/venv/bin/python",
                     "workingDirectoryPersisted": "/fixture project 中文", "parentEnvironmentPersisted": False,
                     "environmentPersisted": {"OPENPYCHARM_FRAMEWORK_TEST": "中文 space;$(literal)"}}
                    for name in ("OpenPyCharmDjango", "OpenPyCharmFlask", "OpenPyCharmFastAPI")]}

    def assess(self, report):
        return assess(report, "current", "/venv/bin/python", "/fixture project 中文")

    def test_complete_current_native_evidence_passes_without_claiming_execution(self):
        result = self.assess(self.native_report())
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["userCodeExecuted"])
        self.assertEqual(result["frameworks"], 3)

    def test_stale_or_incomplete_framework_reports_fail(self):
        cases = (
            lambda report: report.update(invocationId="stale"),
            lambda report: report.update(status="fail", failure="native exception"),
            lambda report: report.update(userCodeExecuted=True),
            lambda report: report["configurations"].pop(),
            lambda report: report["configurations"][0].update(typeId="DjangoLockedRunConfiguration"),
            lambda report: report["configurations"][0].update(factoryApplicable=False),
            lambda report: report["configurations"][0].pop("factoryClonePreservesSelection"),
            lambda report: report["configurations"][0].update(nativeDebugRunner="another runner"),
            lambda report: report["configurations"][0].update(nativeState="generic command line"),
            lambda report: report["configurations"][0].pop("argumentPersistence"),
            lambda report: report["configurations"][0].update(sdkHomePersisted="/wrong/python"),
            lambda report: report["configurations"][0].update(workingDirectoryPersisted="/wrong/project"),
            lambda report: report["configurations"][0].update(environmentPersisted={}),
            lambda report: report["configurations"][0].update(parentEnvironmentPersisted=True),
            lambda report: report["configurations"][0].update(nativeEditor="mock editor"),
        )
        for mutate in cases:
            report = copy.deepcopy(self.native_report())
            mutate(report)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.assess(report)


if __name__ == "__main__":
    unittest.main()
