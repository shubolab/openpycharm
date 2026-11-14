#!/usr/bin/env python3
"""Prepare/compile a native Notebook edit/save/reopen gate; launch only with --run.

Default preparation does not start an IDE. Runs use a new owned project/profile,
the selected product's actual bundled Notebook JAR, and retained timeout evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import tempfile
import uuid
import zipfile

import build_notebook_plugin as builder
from bootstrap import check_space, sha256
from native_probe import app_layout, prepare_profile
from provenance import verify_product_plugins
from runtime_smoke import WindowsJob, WINDOWS_CREATE_SUSPENDED, WINDOWS_CREATE_NEW_PROCESS_GROUP, stop_owned

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tests/notebooks/native-save"


def build_probe(sdk: Path, production_jar: Path) -> tuple[Path, dict]:
    layout = builder.sdk_layout(sdk)
    runtime = builder.execution_layout(layout)
    identity = {"sources": {path.name: sha256(path) for path in sorted(SOURCE.glob("*")) if path.is_file()},
                "productionJarSha256": sha256(production_jar),
                "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "builderSha256": sha256(Path(__file__))}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    work = ROOT / ".tools/notebook-save-native-probe" / key
    check_space(work, 64 * 1024**2); work.mkdir(parents=True, exist_ok=True)
    plugin = work / "plugin/lib/notebook-save-probe.jar"
    with builder.cache_lock(work / "build.lock"):
        with tempfile.TemporaryDirectory(prefix="compile-", dir=work) as directory:
            temporary = Path(directory); classes = temporary / "classes"
            compilation = builder.compile_java(layout, sorted(SOURCE.glob("*.java")), classes, temporary / "javac.args", [production_jar], runtime)
            cp = os.pathsep.join(map(str, [classes, production_jar, *builder.classpath(layout)]))
            payload_checks = json.loads(builder.run_java(runtime, ["-Djava.awt.headless=true", "-classpath", cp,
                "dev.openpycharm.notebooks.saveprobe.NotebookSavePayloadTest"], temporary).stdout)
            if payload_checks.get("status") != "pass":
                raise ValueError("Actual native-gate payload assertion controls failed")
            owned_checks = json.loads(builder.run_java(runtime, ["-Djava.awt.headless=true", "-classpath", cp,
                "dev.openpycharm.notebooks.saveprobe.NotebookSaveOwnedProjectTest", str(temporary)], temporary).stdout)
            if owned_checks.get("status") != "pass":
                raise ValueError("Owned new-project boundary controls failed")
            payloads = {path.relative_to(classes).as_posix(): path.read_bytes() for path in classes.rglob("*.class")
                        if not path.name.split("$", 1)[0].removesuffix(".class").endswith("Test")}
            payloads["META-INF/plugin.xml"] = (SOURCE / "plugin.xml").read_bytes()
            plugin.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(plugin, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in sorted(payloads.items()):
                    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED; archive.writestr(info, data)
    report = {"identity": identity, "pluginSha256": sha256(plugin), "compilation": compilation,
              "classes": sorted(name for name in payloads if name.endswith(".class")), "payloadAssertionTests": payload_checks,
              "ownedProjectBoundaryTests": owned_checks}
    (work / "build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return plugin.parent.parent, report


def prepare(sdk: Path, workspace: Path, app: Path | None = None) -> dict:
    workspace = workspace.absolute()
    if not workspace.resolve().is_relative_to((ROOT / ".tools").resolve()) or workspace.exists() or workspace.is_symlink():
        raise ValueError("Choose a new owned workspace below this checkout's .tools")
    layout = builder.sdk_layout(sdk)
    if workspace.resolve().is_relative_to(layout.sdk_root.resolve()):
        raise ValueError("The probe workspace cannot be inside the authenticated SDK")
    manifest = None
    if app is not None:
        product = app_layout(app)
        if workspace.resolve().is_relative_to(product.sdk_root.resolve()):
            raise ValueError("The probe workspace cannot be inside the product")
        manifest = json.loads((product.contents / "openpycharm-build.json").read_text(encoding="utf-8"))
        verify_product_plugins(manifest, product.contents)
        entry = next((entry for entry in manifest.get("plugins", []) if entry["id"] == "dev.openpycharm.notebooks"), None)
        if entry is None:
            raise ValueError("Selected actual product has no receipted notebook plugin")
        production_jar = product.contents / entry["jar"]
    else:
        production, _ = builder.build_plugin(sdk)
        production_jar = production / "lib/notebooks.jar"
    plugin, compiled = build_probe(sdk, production_jar)
    workspace.mkdir(parents=True)
    project = workspace / "project"; project.mkdir()
    fixture = project / "native-save.ipynb"
    data = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"large": 9007199254740993, "foreign": {"keep": [1, "中文", True]}},
            "cells": [{"id": "save-probe", "cell_type": "code", "metadata": {"trusted": False, "foreignCell": "keep"},
                       "source": ["print('原始保存夹具')\n", "value = 1\n"], "execution_count": 7,
                       "outputs": [{"output_type": "display_data", "data": {"text/plain": "Existing fixture output; not kernel evidence", "application/x-save-probe": {"keep": True}}, "metadata": {"foreignOutput": "keep"}}]}]}
    fixture.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    properties = prepare_profile(workspace / "profile", [layout.sdk_root, project, *([app] if app else [])])
    result = {"schema": 1, "nativeApplicationLaunched": False, "workspace": str(workspace), "project": str(project),
              "fixture": str(fixture), "initialFixtureSha256": sha256(fixture), "profile": str(workspace / "profile"),
              "properties": str(properties), "pluginDirectory": str(plugin), "probeBuild": compiled,
              "productionJarSha256": sha256(production_jar), "productManifest": manifest,
              "projectTrustBypassed": False, "kernelCodeExecuted": False,
              "projectCreationMode": "normal-ide-new-owned-project", "manualTrustClicked": False,
              "limitations": ["Preparation/compilation is not native save acceptance; --run is required in an owned actual product",
                              "The fixture's existing outputs are test data, not runtime Python execution evidence"]}
    (workspace / "prepared.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def run(app: Path, prepared: dict, timeout: int) -> dict:
    layout = app_layout(app); workspace = Path(prepared["workspace"]); profile = Path(prepared["profile"])
    report = workspace / "native-report.json"; invocation = uuid.uuid4().hex
    options = workspace / "probe.vmoptions"
    original = layout.contents / ("bin/pycharm.vmoptions" if layout.platform == "macos" else "bin/pycharm64.exe.vmoptions")
    flags = {"plugin.path": prepared["pluginDirectory"], "openpycharm.notebook.save.report": str(report),
             "openpycharm.notebook.save.root": str(workspace), "openpycharm.notebook.save.project": prepared["project"],
             "openpycharm.notebook.save.file": prepared["fixture"], "openpycharm.notebook.save.invocation": invocation,
             "openpycharm.notebook.save.expected.jar": prepared["productionJarSha256"],
             "openpycharm.notebook.save.mode": "normal-ide-new-owned-project",
             "openpycharm.notebook.save.initial.sha256": prepared["initialFixtureSha256"],
             "openpycharm.notebook.save.profile": str(profile), "openpycharm.notebook.save.application": str(layout.contents)}
    options.write_text(original.read_text(encoding="utf-8") + "\n" + "\n".join(f"-D{key}={value}" for key, value in flags.items()) + "\n", encoding="utf-8")
    environment = dict(os.environ, OPENPYCHARM_PROPERTIES=prepared["properties"], OPENPYCHARM_VM_OPTIONS=str(options))
    executable = layout.contents / ("MacOS/pycharm" if layout.platform == "macos" else "bin/pycharm64.exe")
    result = {**prepared, "launchRequested": True, "nativeApplicationLaunched": False, "invocationId": invocation, "application": str(app.absolute())}
    process = job = None; resumed = False
    with (workspace / "launch.log").open("wb") as log:
        try:
            windows = layout.platform == "windows"; job = WindowsJob() if windows else None
            kwargs = {"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP} if windows else {"start_new_session": True}
            process = subprocess.Popen([str(executable)], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **kwargs)
            result["ownedPid"] = process.pid; result["nativeApplicationLaunched"] = True
            if job is not None:
                job.assign_and_resume(process); resumed = True
            deadline = time.monotonic() + timeout
            while process.poll() is None and not report.is_file() and time.monotonic() < deadline:
                time.sleep(0.25)
            if not report.is_file():
                try:
                    dump = subprocess.run([str(layout.jcmd), str(process.pid), "Thread.print", "-l"], text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=15)
                    (workspace / "external-timeout-threads.txt").write_text(dump.stdout + dump.stderr, encoding="utf-8")
                except Exception as error:
                    result["threadDumpFailure"] = str(error)
                raise ValueError("No native report before timeout/process exit; preserve launch log and ordinary project-trust state")
            native = json.loads(report.read_text(encoding="utf-8")); result["native"] = native
            if native.get("invocationId") != invocation or native.get("plugin", {}).get("jarSha256") != prepared["productionJarSha256"]:
                raise ValueError("Native report does not bind this invocation and actual product notebook JAR")
            if (native.get("normalIdeNewProjectCreation") is not True or native.get("normalIdeProjectOpen") is not True
                    or native.get("expectedInitialFixtureHash") != prepared["initialFixtureSha256"]
                    or native.get("projectTrustBypassed") is not False or native.get("projectTrusted") is not True
                    or native.get("globalTrustChecksDisabled") is not False or native.get("manualTrustClicked") is not False
                    or native.get("projectCreationMode") != "normal-ide-new-owned-project"
                    or native.get("trustedProjectRoot") != prepared["project"]
                    or native.get("parentTrustedBefore") is not False or native.get("parentTrustedAfter") is not False):
                raise ValueError("Native owned new-project lifecycle/trust evidence did not pass")
            required = ["nativeUndoRestored", "pendingCellAndTextMerge", "nativeSavePersisted", "postSaveExternalDirtyMerge", "metadataAndExistingOutputsPreserved", "closeReopenSourcePreserved", "platformSaveAllPersisted",
                        "successfulReloadStatusRestored", "successfulReloadStateClean", "postSaveAllCanEdit"]
            if native.get("status") != "pass" or not all(native.get(key) is True for key in required) or native.get("heartbeatTicksAfterSave", 0) < 2:
                raise ValueError("Actual native edit/save/reopen or EDT heartbeat gate failed")
            result["assessment"] = {"status": "pass", "actualNativeSaveEngine": True, "kernelCodeExecuted": False}
        except Exception as error:
            result["assessment"] = {"status": "fail", "error": str(error)}
        finally:
            try:
                if process is not None:
                    if job is not None and not resumed and process.poll() is None:
                        process.kill()
                    result["cleanup"] = stop_owned(process, job); result["ownedProcessExit"] = process.returncode
                elif job is not None:
                    job.stop()
            except Exception as error:
                result["cleanup"] = {"status": "fail", "error": str(error), "ownedPid": None if process is None else process.pid}
                result["assessment"] = {"status": "fail", "error": "Owned process cleanup failed; retain exact PID and logs"}
    (workspace / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--run", action="store_true", help="Explicitly launch an owned actual IDE for the native gate")
    parser.add_argument("--timeout", type=int, default=150)
    args = parser.parse_args()
    if args.run and args.app is None:
        parser.error("--run requires an actual assembled/installed --app")
    if not 30 <= args.timeout <= 240:
        parser.error("Use timeout 30..240 seconds")
    prepared = prepare(args.sdk, args.workspace, args.app)
    if not args.run:
        print(json.dumps({"prepared": str(Path(prepared["workspace"]) / "prepared.json"), "nativeApplicationLaunched": False,
                          "probeJarSha256": prepared["probeBuild"]["pluginSha256"], "productionJarSha256": prepared["productionJarSha256"]}))
        return 0
    result = run(args.app, prepared, args.timeout)
    print(json.dumps({"result": str(Path(prepared["workspace"]) / "result.json"), "assessment": result["assessment"]}))
    return 0 if result["assessment"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
