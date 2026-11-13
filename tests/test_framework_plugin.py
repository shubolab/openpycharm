import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from framework_probe import assess, assess_generators, assess_packaged, assess_packaged_startup, assess_venvs


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


class FrameworkGeneratorEvidenceTests(unittest.TestCase):
    @staticmethod
    def report():
        projects = []
        for name, install in (("django", True), ("flask", True), ("fastapi", True), ("flask", False)):
            interpreter = "/selected-venv/bin/python" if install else "/no-install-venv/bin/python"
            path = "/generated 项目/" + name + ("-no-install" if not install else "")
            files = ["requirements.txt", "README.md", "manage.py", "project_config/settings.py", "project_config/urls.py"] if name == "django" else ["requirements.txt", "README.md", "app.py"]
            projects.append({"framework": name, "installDependencies": install, "status": "pass", "collisionRejected": True,
                             "sdkHome": interpreter, "moduleSdkAfterNativeStage": interpreter, "path": path,
                             "sdkCreatorContext": "com.jetbrains.python.sdk.ModuleOrProject$ModuleAndProject",
                             "files": {file: "a" * 64 for file in files},
                             "runConfiguration": {"interpreter": interpreter, "workingDirectory": path, "moduleSdk": True,
                                                  "typeId": {"django": "OpenPyCharmDjango", "flask": "OpenPyCharmFlask", "fastapi": "OpenPyCharmFastAPI"}[name]}})
        return {"invocationId": "current", "status": "pass", "nativeGuiCreateClicked": False,
                "generatorPeers": [{"framework": name, "nativePeer": "com.jetbrains.python.newProjectWizard.impl.PyV3GeneratorPeer",
                                    "dependencyCheckboxDefault": False, "dependencyCheckboxBinding": "pass"} for name in ("DJANGO", "FLASK", "FASTAPI")],
                "projects": projects, "processLifecycle": {"status": "pass", "ownedPids": {"parent": 1234, "child": 1235},
                    "ownedPidsAliveAfterCancellation": False, "cancellationPreserved": True, "nonzeroExitPropagated": True, "timeoutPropagated": True,
                    "normalExitChildrenCleaned": True, "normalExitOwnedPids": {"parent": 1236, "child": 1237},
                    "failedExitChildrenCleaned": True, "failedExitOwnedPids": {"parent": 1238, "child": 1239}}}

    def assess(self, report):
        return assess_generators(report, "current", "/selected-venv/bin/python", "/no-install-venv/bin/python")

    def test_complete_native_generation_evidence_passes_without_claiming_create_clicks(self):
        result = self.assess(self.report())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["generatedProjects"], 4)
        self.assertFalse(result["nativeGuiCreateClicked"])

    def test_incomplete_sdk_ui_install_optout_or_process_evidence_cannot_pass(self):
        cases = (
            lambda report: report.update(invocationId="old"),
            lambda report: report.update(nativeGuiCreateClicked=True),
            lambda report: report["generatorPeers"][0].update(dependencyCheckboxDefault=True),
            lambda report: report["generatorPeers"][0].update(nativePeer="mock peer"),
            lambda report: report["projects"].pop(),
            lambda report: report["projects"][0].update(moduleSdkAfterNativeStage="/wrong/python"),
            lambda report: report["projects"][3].update(sdkHome="/selected-venv/bin/python"),
            lambda report: report["projects"][0]["runConfiguration"].update(moduleSdk=False),
            lambda report: report["projects"][0]["runConfiguration"].update(typeId="DjangoLockedRunConfiguration"),
            lambda report: report["projects"][0]["files"].pop("manage.py"),
            lambda report: report["projects"][0].update(collisionRejected=False),
            lambda report: report["processLifecycle"].update(ownedPidsAliveAfterCancellation=True),
            lambda report: report["processLifecycle"].update(timeoutPropagated=False),
            lambda report: report["processLifecycle"].update(normalExitChildrenCleaned=False),
            lambda report: report["processLifecycle"].pop("failedExitOwnedPids"),
            lambda report: report["processLifecycle"].pop("ownedPids"),
        )
        for mutate in cases:
            report = copy.deepcopy(self.report())
            mutate(report)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.assess(report)

    def test_dependency_evidence_requires_exact_pins_and_both_selected_venvs(self):
        primary = Path("/disposable/selected-venv/bin/python")
        optout = Path("/disposable/no-install-venv/bin/python")
        selected = {"prefix": str(primary.parent.parent), "basePrefix": "/base-python",
                    "packages": {"Django": "5.2.8", "Flask": "3.1.2", "fastapi": "0.121.0", "uvicorn": "0.38.0"}}
        no_install = {"prefix": str(optout.parent.parent), "basePrefix": "/base-python", "frameworkPackagesPresent": False}
        assess_venvs(selected, no_install, primary, optout)
        for target, mutation in (("selected", {"prefix": "/unrelated-venv"}),
                                 ("selected", {"packages": {"Django": "9.9"}}),
                                 ("selected", {"basePrefix": selected["prefix"]}),
                                 ("optout", {"frameworkPackagesPresent": True}),
                                 ("optout", {"frameworkPackagesPresent": None}),
                                 ("optout", {"prefix": selected["prefix"]})):
            current_selected, current_optout = copy.deepcopy(selected), copy.deepcopy(no_install)
            (current_selected if target == "selected" else current_optout).update(mutation)
            with self.subTest(target=target, mutation=mutation), self.assertRaises(ValueError):
                assess_venvs(current_selected, current_optout, primary, optout)


class PackagedFrameworkEvidenceTests(unittest.TestCase):
    def test_welcome_probe_requires_all_non_project_startup_boundaries(self):
        manifest = {"plugins": [{"id": "dev.openpycharm.http"}, {"id": "dev.openpycharm.frameworks"}]}
        observation = {"ideStarted": True, "productIdentity": True, "vendorIdentity": True, "errorCount": 0,
                       "isolatedPaths": {key: True for key in ("config", "system", "plugins", "log")},
                       "loadedPlugins": {key: True for key in ("Python Community Edition", "Git", "Terminal")},
                       "packagedPlugins": {entry["id"]: True for entry in manifest["plugins"]}}
        assess_packaged_startup(observation, manifest)
        mutations = [lambda candidate, key=key: candidate.update({key: False}) for key in ("ideStarted", "productIdentity", "vendorIdentity")]
        for group in ("isolatedPaths", "loadedPlugins", "packagedPlugins"):
            mutations += [lambda candidate, group=group, key=key: candidate[group].update({key: False}) for key in observation[group]]
        mutations += [lambda candidate: candidate.update(errorCount=1), lambda candidate: candidate["packagedPlugins"].pop("dev.openpycharm.frameworks")]
        for mutate in mutations:
            current = copy.deepcopy(observation)
            mutate(current)
            with self.subTest(observation=current), self.assertRaises(ValueError):
                assess_packaged_startup(current, manifest)

    def test_native_product_location_version_and_exact_jar_are_required(self):
        contents, probe = Path("/candidate/OpenPyCharm/Contents"), Path("/owned/test-listener")
        entry = {"id": "dev.openpycharm.frameworks", "version": "0.1.0-dev.2", "jarSha256": "a" * 64,
                 "path": "third-party-plugins/openpycharm-frameworks", "jar": "third-party-plugins/openpycharm-frameworks/lib/frameworks.jar"}
        plugin = {"id": entry["id"], "version": entry["version"], "jarSha256": entry["jarSha256"], "enabled": True, "bundled": True,
                  "path": str(contents / entry["path"]), "jar": str(contents / entry["jar"]),
                  "applicationHome": str(contents), "pluginPathProperty": probe.as_posix()}
        self.assertEqual(assess_packaged({"frameworkPlugin": plugin}, {"plugins": [entry]}, contents, probe)["status"], "pass")
        for mutation in ({"id": "locked.frameworks"}, {"version": "old"}, {"jarSha256": "b" * 64}, {"enabled": False}, {"bundled": False},
                         {"path": "/external/plugin"}, {"jar": "/external/frameworks.jar"}, {"applicationHome": "/reference/PyCharm"},
                         {"pluginPathProperty": probe.as_posix() + "," + str(contents / entry["path"])}):
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "authenticated native product"):
                assess_packaged({"frameworkPlugin": {**plugin, **mutation}}, {"plugins": [entry]}, contents, probe)
        with self.assertRaisesRegex(ValueError, "does not declare"):
            assess_packaged({"frameworkPlugin": plugin}, {"plugins": []}, contents, probe)


if __name__ == "__main__":
    unittest.main()
