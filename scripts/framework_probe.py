#!/usr/bin/env python3
"""Check framework config registration/persistence/runners in the actual native IDE.

The test-only listener uses the default project and never executes user code.
The ordinary welcome screen may create a workspace under the isolated JVM home.
Native Run/Debug server execution remains a separate acceptance workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from build_framework_plugin import ROOT, build_native_probe, build_plugin
from bootstrap import sha256
from native_probe import app_layout, prepare_profile
from provenance import verify_product_plugins, verify_source_inputs
from runtime_smoke import WindowsJob, WINDOWS_CREATE_SUSPENDED, WINDOWS_CREATE_NEW_PROCESS_GROUP, log_observation, stop_owned


def assess(native: dict, invocation: str, python: str, working_directory: str) -> dict:
    if native.get("invocationId") != invocation:
        raise ValueError("Framework report belongs to another invocation")
    if native.get("status") != "pass" or native.get("failure") or native.get("userCodeExecuted") is not False:
        raise ValueError("Native framework configuration probe failed: " + str(native.get("failure")))
    expected = {"OpenPyCharmDjango", "OpenPyCharmFlask", "OpenPyCharmFastAPI"}
    entries = native.get("configurations", [])
    if len(entries) != 3 or {entry.get("typeId") for entry in entries} != expected:
        raise ValueError("All three independent framework types must be registered")
    for entry in entries:
        if (entry.get("status") != "pass" or entry.get("factoryApplicable") is not True
                or entry.get("nativeRunRunner") != "PythonRunner"
                or entry.get("nativeDebugRunner") != "PyDebugRunner"
                or entry.get("nativeState") != "com.jetbrains.python.run.PythonScriptCommandLineState"
                or entry.get("factoryClonePreservesSelection") is not True
                or entry.get("argumentPersistence") != "pass"):
            raise ValueError("Incomplete native runner/state/persistence evidence")
        if (entry.get("sdkHomePersisted") != python or entry.get("workingDirectoryPersisted") != working_directory
                or entry.get("parentEnvironmentPersisted") is not False
                or entry.get("environmentPersisted", {}).get("OPENPYCHARM_FRAMEWORK_TEST") != "中文 space;$(literal)"):
            raise ValueError("Selected interpreter, working directory or environment did not persist")
        if not entry.get("nativeEditor", "").startswith("com.jetbrains.python."):
            raise ValueError("Native Python configuration editor was not observed")
    return {"status": "pass", "frameworks": 3, "userCodeExecuted": False,
            "scope": "Native EP registration, editor/state, runner selection and persistence"}


def assess_generators(native: dict, invocation: str, python: str, optout_python: str) -> dict:
    if (native.get("invocationId") != invocation or native.get("status") != "pass" or native.get("failure") or native.get("cleanupFailure")
            or native.get("nativeGuiCreateClicked") is not False):
        raise ValueError("Native generator integration failed or belongs to another invocation: " + str(native.get("failure", native.get("cleanupFailure"))))
    peers = native.get("generatorPeers", [])
    if len(peers) != 3 or {peer.get("framework") for peer in peers} != {"DJANGO", "FLASK", "FASTAPI"}:
        raise ValueError("All three native framework generator peers must be observed")
    for peer in peers:
        if (peer.get("nativePeer") != "com.jetbrains.python.newProjectWizard.impl.PyV3GeneratorPeer"
                or peer.get("dependencyCheckboxDefault") is not False or peer.get("dependencyCheckboxBinding") != "pass"):
            raise ValueError("Native SDK peer or opt-in dependency UI evidence is incomplete")

    def normalized(path):
        return str(path).replace("\\", "/").casefold() if os.name == "nt" else str(path)

    projects = native.get("projects", [])
    if len(projects) != 4 or {(project.get("framework"), project.get("installDependencies")) for project in projects} != {
        ("django", True), ("flask", True), ("fastapi", True), ("flask", False)}:
        raise ValueError("Native generation must exercise all three opt-in projects and a no-install project")
    for project in projects:
        expected = python if project["installDependencies"] else optout_python
        run = project.get("runConfiguration", {})
        required = {"requirements.txt", "README.md", "manage.py", "project_config/settings.py", "project_config/urls.py"} if project["framework"] == "django" else {"requirements.txt", "README.md", "app.py"}
        files = project.get("files", {})
        if (project.get("status") != "pass" or not project.get("collisionRejected")
                or normalized(project.get("sdkHome")) != normalized(expected)
                or normalized(project.get("moduleSdkAfterNativeStage")) != normalized(expected)
                or normalized(run.get("interpreter")) != normalized(expected)
                or normalized(run.get("workingDirectory")) != normalized(project.get("path")) or run.get("moduleSdk") is not True
                or run.get("typeId") != {"django": "OpenPyCharmDjango", "flask": "OpenPyCharmFlask", "fastapi": "OpenPyCharmFastAPI"}[project["framework"]]
                or not project.get("sdkCreatorContext", "").endswith("$ModuleAndProject")
                or not required.issubset(files) or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in files.values())):
            raise ValueError("Generated project lost its selected venv/module, files or native run configuration")
    processes = native.get("processLifecycle", {})
    for key in ("cancellationPreserved", "nonzeroExitPropagated", "timeoutPropagated", "normalExitChildrenCleaned", "failedExitChildrenCleaned"):
        if processes.get(key) is not True:
            raise ValueError("Owned dependency helper failure/cancellation evidence is incomplete")
    if processes.get("status") != "pass" or processes.get("ownedPidsAliveAfterCancellation") is not False:
        raise ValueError("Owned dependency helper cleanup did not pass")
    for key in ("ownedPids", "normalExitOwnedPids", "failedExitOwnedPids"):
        pids = processes.get(key, {})
        if not {"parent", "child"}.issubset(pids) or not all(isinstance(pid, (int, float)) and not isinstance(pid, bool) and pid > 0 for pid in pids.values()):
            raise ValueError("No owned parent/child process evidence was retained")
    return {"status": "pass", "frameworks": 3, "generatedProjects": 4, "nativeGuiCreateClicked": False,
            "scope": "Native generator UI/API, real selected venv/module, opt-in/out and helper lifecycle"}


def assess_venvs(selected: dict, no_install: dict, python: Path, optout_python: Path) -> None:
    expected = {"Django": "5.2.8", "Flask": "3.1.2", "fastapi": "0.121.0", "uvicorn": "0.38.0"}
    # Resolve the venv directory, never the executable symlink to its base Python.
    selected_root = python.parent.parent.resolve()
    optout_root = optout_python.parent.parent.resolve()
    if (selected.get("packages") != expected or selected.get("prefix") == selected.get("basePrefix")
            or no_install.get("prefix") == no_install.get("basePrefix")
            or Path(selected.get("prefix", "")).resolve() != selected_root
            or Path(no_install.get("prefix", "")).resolve() != optout_root
            or no_install.get("frameworkPackagesPresent") is not False):
        raise ValueError("Pinned dependencies or opt-out did not stay within the selected real venvs")


def assess_packaged(native: dict, manifest: dict, contents: Path, test_plugin: Path) -> dict:
    expected = next((entry for entry in manifest.get("plugins", []) if entry.get("id") == "dev.openpycharm.frameworks"), None)
    if expected is None:
        raise ValueError("Product manifest does not declare the framework plugin")
    observed = native.get("frameworkPlugin", {})
    normalize = lambda path: str(path).replace("\\", "/").casefold() if os.name == "nt" else str(path)
    if (observed.get("id") != expected["id"] or observed.get("version") != expected["version"]
            or observed.get("enabled") is not True or observed.get("bundled") is not True
            or observed.get("jarSha256") != expected["jarSha256"]
            or normalize(observed.get("path")) != normalize(contents / expected["path"])
            or normalize(observed.get("jar")) != normalize(contents / expected["jar"])
            or normalize(observed.get("applicationHome")) != normalize(contents)
            or normalize(observed.get("pluginPathProperty")) != normalize(test_plugin.as_posix())):
        raise ValueError("Framework implementation was not loaded from the authenticated native product directory")
    return {"status": "pass", "id": expected["id"], "version": expected["version"], "jarSha256": expected["jarSha256"],
            "loading": "Native home-relative third-party-plugins; only the test listener is injected"}


def assess_packaged_startup(observation: dict, manifest: dict) -> None:
    if (not all(observation.get(key) is True for key in ("ideStarted", "productIdentity", "vendorIdentity"))
            or not all(observation.get("isolatedPaths", {}).get(key) is True for key in ("config", "system", "plugins", "log"))
            or not all(observation.get("loadedPlugins", {}).get(key) is True for key in ("Python Community Edition", "Git", "Terminal"))
            or set(observation.get("packagedPlugins", {})) != {entry["id"] for entry in manifest.get("plugins", [])}
            or not observation.get("packagedPlugins") or not all(observation["packagedPlugins"].values())
            or observation.get("errorCount") != 0):
        raise ValueError("Native product startup identity, isolated paths or packaged plugin loading was not fully observed")


def run_probe(app: Path, sdk: Path, python: Path, profile: Path, timeout: int = 90, generators: bool = False, packaged: bool = False) -> dict:
    if not 10 <= timeout <= 180:
        raise ValueError("Use a 10–180 second native probe timeout")
    profile = profile.resolve()
    if profile.exists():
        raise ValueError("Choose a new isolated profile to avoid old reports or running instances")
    layout = app_layout(app)
    app_manifest_path = layout.contents / "openpycharm-build.json"
    app_manifest = json.loads(app_manifest_path.read_text(encoding="utf-8"))
    verified_plugins = verify_product_plugins(app_manifest, layout.contents)
    if packaged:
        verify_source_inputs(app_manifest)
        framework = next((entry for entry in app_manifest.get("plugins", []) if entry.get("id") == "dev.openpycharm.frameworks"), None)
        if framework is None:
            raise ValueError("The selected product does not bundle the framework plugin")
        if not isinstance(framework.get("build"), dict) or framework["build"].get("jarSha256") != framework["jarSha256"]:
            raise ValueError("The packaged framework build receipt does not match its JAR")
    python = python.absolute()
    if not python.is_file():
        raise ValueError("Select an existing interpreter for the persistence check")
    properties = prepare_profile(profile, [app, sdk])
    if packaged:
        plugin, build = layout.contents / framework["path"], framework["build"]
    else:
        plugin, build = build_plugin(sdk)
    probe = build_native_probe(sdk, plugin)
    invocation = uuid.uuid4().hex
    native_path = profile / "framework-native.json"
    work = profile / "working directory 中文"
    work.mkdir()
    isolated_home = profile / "home"
    isolated_home.mkdir()
    optout_python = None
    if generators:
        # Real clean venvs make installation and opt-out effects observable.
        original_python = python
        for name in ("selected-venv", "no-install-venv"):
            subprocess.run([str(original_python), "-m", "venv", str(profile / name)], check=True, timeout=60)
        executable = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        python = profile / "selected-venv" / executable
        optout_python = profile / "no-install-venv" / executable
    result = {"schema": 1, "application": str(app.resolve()), "profile": str(profile),
              "applicationBuild": {"version": app_manifest.get("version"), "upstreamBuild": app_manifest.get("upstreamBuild"),
                                   "sourceCommit": app_manifest.get("sourceCommit"), "manifestSha256": sha256(app_manifest_path)},
              "frameworkPluginBuild": build, "invocationId": invocation,
              "packagedMode": packaged, "verifiedPluginJars": verified_plugins,
              "isolatedJvmHome": str(isolated_home),
              "limitations": ["No user code is executed by the probe",
                              "The normal welcome provider may create a disposable project/venv under the isolated JVM home",
                              "Actual native Run/Debug, breakpoints, stop/reload and Windows UI remain separate acceptance gates"]}
    with tempfile.TemporaryDirectory(prefix="framework-launch-", dir=profile) as directory:
        temporary = Path(directory)
        vmoptions = temporary / "framework-probe.vmoptions"
        base = layout.contents / ("bin/pycharm.vmoptions" if layout.platform == "macos" else "bin/pycharm64.exe.vmoptions")
        properties_map = {"user.home": isolated_home.as_posix(),
                          "plugin.path": probe.as_posix() if packaged else ",".join(path.as_posix() for path in (plugin, probe)),
                          "openpycharm.framework.probe.report": native_path.as_posix(),
                          "openpycharm.framework.probe.output.root": profile.as_posix(),
                          "openpycharm.framework.probe.invocation.id": invocation,
                          "openpycharm.framework.probe.python": python.as_posix(),
                          "openpycharm.framework.probe.working.dir": work.as_posix()}
        if generators:
            properties_map.update({
                "openpycharm.framework.generator.probe.root": (profile / "generated projects 中文").as_posix(),
                "openpycharm.framework.generator.probe.optout.python": optout_python.as_posix(),
                "openpycharm.framework.generator.probe.python.version": subprocess.check_output([str(python), "--version"], text=True).strip(),
            })
            result["limitations"] = ["Native generator UI/API with a controlled SDK creator selecting real clean existing venvs",
                                     "The actual wizard Create/Cancel clicks and Windows desktop flow remain separate acceptance gates",
                                     "Pinned dependency installation is opt-in and targets only the disposable selected venv",
                                     "Portable process cleanup tracks observed descendants; an instant-spawn orphan before observation is not covered by a native OS job/session container"]
        if any(any(character in value for character in "\r\n\0") for value in properties_map.values()):
            raise ValueError("Native probe VM property contains a line break or NUL")
        vmoptions.write_text(base.read_text(encoding="utf-8") + "\n" +
                             "\n".join(f"-D{key}={value}" for key, value in properties_map.items()) + "\n", encoding="utf-8")
        environment = dict(os.environ, OPENPYCHARM_PROPERTIES=str(properties), OPENPYCHARM_VM_OPTIONS=str(vmoptions))
        executable = layout.contents / ("MacOS/pycharm" if layout.platform == "macos" else "bin/pycharm64.exe")
        with (profile / "framework-launch.log").open("wb") as log:
            process, job, resumed = None, None, False
            try:
                windows = layout.platform == "windows"
                job = WindowsJob() if windows else None
                options = ({"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP}
                           if windows else {"start_new_session": True})
                process = subprocess.Popen([str(executable)], env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, **options)
                result["ownedPid"] = process.pid
                if job is not None:
                    job.assign_and_resume(process)
                    resumed = True
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline and process.poll() is None and not native_path.is_file():
                    time.sleep(0.25)
                if not native_path.is_file():
                    raise ValueError("Native framework probe produced no report before timeout/process exit")
                native = json.loads(native_path.read_text(encoding="utf-8"))
                result["native"] = native
                result["assessment"] = (assess_generators(native, invocation, python.as_posix(), optout_python.as_posix()) if generators
                                        else assess(native, invocation, python.as_posix(), work.as_posix()))
                if packaged:
                    result["packagedAssessment"] = assess_packaged(native, app_manifest, layout.contents, probe)
                try:
                    process.wait(timeout=20)
                    result["nativeGracefulExit"] = process.returncode
                except subprocess.TimeoutExpired:
                    result["nativeGracefulExit"] = "timed-out; owned-session cleanup required"
                if result["nativeGracefulExit"] != 0:
                    result["assessment"] = {"status": "fail", "error": "Native probe did not exit normally: " + str(result["nativeGracefulExit"])}
            except Exception as error:
                result["assessment"] = {"status": "fail", "error": str(error)}
            finally:
                if process is not None:
                    if job is not None and not resumed and process.poll() is None:
                        process.kill()
                    try:
                        result["cleanup"] = stop_owned(process, job)
                    except Exception as error:
                        result["assessment"] = {"status": "fail", "error": "Owned process cleanup failed: " + str(error)}
                elif job is not None:
                    job.stop()
    idea_log = profile / "log/idea.log"
    if idea_log.is_file():
        observed = log_observation(idea_log.read_text(encoding="utf-8", errors="replace"), profile, work, app_manifest["upstreamBuild"], app_manifest.get("plugins", []))
        result["logObservation"] = observed
        if observed["errorCount"]:
            result["assessment"] = {"status": "fail", "error": "Native IDEA log contains ERROR or SEVERE entries"}
        if packaged:
            try:
                assess_packaged_startup(observed, app_manifest)
            except ValueError as error:
                result["assessment"] = {"status": "fail", "error": str(error)}
    else:
        result["assessment"] = {"status": "fail", "error": "Native IDEA log is missing"}
    if generators and result.get("assessment", {}).get("status") == "pass":
        try:
            check = "import importlib.metadata,json,sys;names=['Django','Flask','fastapi','uvicorn'];print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'basePrefix':sys.base_prefix,'packages':{n:importlib.metadata.version(n) for n in names}}))"
            selected = json.loads(subprocess.check_output([str(python), "-I", "-c", check], text=True, stderr=subprocess.STDOUT))
            no_install = json.loads(subprocess.check_output([str(optout_python), "-I", "-c",
                "import importlib.util,json,sys;print(json.dumps({'prefix':sys.prefix,'basePrefix':sys.base_prefix,'frameworkPackagesPresent':any(importlib.util.find_spec(n) for n in ['django','flask','fastapi','uvicorn'])}))"], text=True, stderr=subprocess.STDOUT))
            result["selectedVenvAfterInstallation"] = selected
            result["optOutVenvAfterGeneration"] = no_install
            assess_venvs(selected, no_install, python, optout_python)
        except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError) as error:
            result["assessment"] = {"status": "fail", "error": "Venv package verification failed: " + str(error)}
    (profile / "framework-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--generators", action="store_true", help="Exercise generator UI/API with clean disposable venvs and opt-in dependency installation")
    parser.add_argument("--packaged", action="store_true", help="Require the production framework JAR to load through the native product plugin directory")
    args = parser.parse_args()
    result = run_probe(args.app, args.sdk, args.python, args.profile, args.timeout, args.generators, args.packaged)
    print(json.dumps({"assessment": result["assessment"], "profile": result["profile"]}))
    if result["assessment"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
