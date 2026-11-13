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
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from build_framework_plugin import ROOT, build_native_probe, build_plugin
from bootstrap import sha256
from native_probe import app_layout, prepare_profile
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


def run_probe(app: Path, sdk: Path, python: Path, profile: Path, timeout: int = 90) -> dict:
    if not 10 <= timeout <= 180:
        raise ValueError("Use a 10–180 second native probe timeout")
    profile = profile.resolve()
    if profile.exists():
        raise ValueError("Choose a new isolated profile to avoid old reports or running instances")
    layout = app_layout(app)
    app_manifest_path = layout.contents / "openpycharm-build.json"
    app_manifest = json.loads(app_manifest_path.read_text(encoding="utf-8"))
    python = python.absolute()
    if not python.is_file():
        raise ValueError("Select an existing interpreter for the persistence check")
    properties = prepare_profile(profile, [app, sdk])
    plugin, build = build_plugin(sdk)
    probe = build_native_probe(sdk, plugin)
    invocation = uuid.uuid4().hex
    native_path = profile / "framework-native.json"
    work = profile / "working directory 中文"
    work.mkdir()
    isolated_home = profile / "home"
    isolated_home.mkdir()
    result = {"schema": 1, "application": str(app.resolve()), "profile": str(profile),
              "applicationBuild": {"version": app_manifest.get("version"), "upstreamBuild": app_manifest.get("upstreamBuild"),
                                   "sourceCommit": app_manifest.get("sourceCommit"), "manifestSha256": sha256(app_manifest_path)},
              "frameworkPluginBuild": build, "invocationId": invocation,
              "isolatedJvmHome": str(isolated_home),
              "limitations": ["No user code is executed by the probe",
                              "The normal welcome provider may create a disposable project/venv under the isolated JVM home",
                              "Actual native Run/Debug, breakpoints, stop/reload and Windows UI remain separate acceptance gates"]}
    with tempfile.TemporaryDirectory(prefix="framework-launch-", dir=plugin.parent) as directory:
        temporary = Path(directory)
        vmoptions = temporary / "framework-probe.vmoptions"
        base = layout.contents / ("bin/pycharm.vmoptions" if layout.platform == "macos" else "bin/pycharm64.exe.vmoptions")
        properties_map = {"user.home": isolated_home.as_posix(),
                          "plugin.path": ",".join(path.as_posix() for path in (plugin, probe)),
                          "openpycharm.framework.probe.report": native_path.as_posix(),
                          "openpycharm.framework.probe.output.root": profile.as_posix(),
                          "openpycharm.framework.probe.invocation.id": invocation,
                          "openpycharm.framework.probe.python": python.as_posix(),
                          "openpycharm.framework.probe.working.dir": work.as_posix()}
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
                result["assessment"] = assess(native, invocation, python.as_posix(), work.as_posix())
                try:
                    process.wait(timeout=20)
                    result["nativeGracefulExit"] = process.returncode
                except subprocess.TimeoutExpired:
                    result["nativeGracefulExit"] = "timed-out; owned-session cleanup required"
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
        observed = log_observation(idea_log.read_text(encoding="utf-8", errors="replace"), profile, work, app_manifest["upstreamBuild"])
        result["logObservation"] = observed
        if observed["errorCount"]:
            result["assessment"] = {"status": "fail", "error": "Native IDEA log contains ERROR or SEVERE entries"}
    else:
        result["assessment"] = {"status": "fail", "error": "Native IDEA log is missing"}
    (profile / "framework-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    result = run_probe(args.app, args.sdk, args.python, args.profile, args.timeout)
    print(json.dumps({"assessment": result["assessment"], "profile": result["profile"]}))
    if result["assessment"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
