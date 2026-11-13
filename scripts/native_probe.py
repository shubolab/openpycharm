#!/usr/bin/env python3
"""Build and run a read-only Python PSI/test probe in an actual OpenPyCharm app.

The probe preserves the ordinary project-trust flow. A fresh profile may need a
person to trust the disposable fixture and select its Python SDK. This is native
semantic evidence, not Run/Test/Debug UI automation or full product acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
import uuid
import zipfile

from bootstrap import PIN_PATH, validate_cached
from platform_layout import cache_lock, detect_platform_layout, java_compiler_invocation
from runtime_smoke import WindowsJob, WINDOWS_CREATE_SUSPENDED, WINDOWS_CREATE_NEW_PROCESS_GROUP, stop_owned

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "tests/native"
PLUGIN_ID = "dev.openpycharm.native.probe"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def app_layout(app: Path):
    layout = detect_platform_layout(app)
    info = json.loads(layout.product_info.read_text(encoding="utf-8"))
    if info.get("name") != "OpenPyCharm" or not (layout.contents / "openpycharm-build.json").is_file():
        raise ValueError("Select an assembled or installed OpenPyCharm application")
    if layout.platform not in {"macos", "windows"}:
        raise ValueError("Native probes currently support macOS and Windows")
    return layout


def build_plugin(sdk: Path) -> tuple[Path, dict]:
    layout = detect_platform_layout(sdk)
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    pin = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    if validate_cached(layout.sdk_root.parent, pin, target) != layout.sdk_root:
        raise ValueError("Compile only against the authenticated open-source SDK")
    source_files = [SOURCES / "DiagnosticProbe.java", SOURCES / "plugin.xml"]
    identity = {"sources": {file.name: sha(file) for file in source_files},
                "sdkReceiptSha256": sha(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "compiler": subprocess.check_output([str(layout.javac), "-version"], text=True, stderr=subprocess.STDOUT, timeout=15).strip()}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
    work = ROOT / ".tools/native-probe" / key
    work.mkdir(parents=True, exist_ok=True)
    plugin = work / "plugin/lib/native-probe.jar"
    receipt = work / "build.json"
    with cache_lock(work / "build.lock"):
        if plugin.is_file() and receipt.is_file():
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            if saved.get("identity") == identity and saved.get("pluginSha256") == sha(plugin):
                return plugin.parent.parent, saved
        with tempfile.TemporaryDirectory(prefix="compile-", dir=work) as directory:
            temporary = Path(directory)
            classes = temporary / "classes"
            classes.mkdir()
            jars = sorted(layout.lib.glob("*.jar")) + sorted((layout.contents / "plugins/python-ce/lib").rglob("*.jar"))
            arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath",
                         os.pathsep.join(map(str, jars)), "-d", str(classes), str(SOURCES / "DiagnosticProbe.java")]
            invocation = java_compiler_invocation(layout.javac, arguments, temporary / "javac.args")
            result = subprocess.run(invocation.command, cwd=invocation.cwd, text=True, capture_output=True, timeout=90)
            if result.returncode:
                raise ValueError("Compiling native probe failed:\n" + result.stdout + result.stderr)
            candidate = temporary / "native-probe.jar"
            payloads = {file.relative_to(classes).as_posix(): file.read_bytes() for file in classes.rglob("*.class")}
            if "dev/openpycharm/probe/DiagnosticProbe.class" not in payloads:
                raise ValueError("Native probe implementation was not compiled")
            payloads["META-INF/plugin.xml"] = (SOURCES / "plugin.xml").read_bytes()
            with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in sorted(payloads.items()):
                    entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, data)
            plugin.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(plugin)
            saved = {"schema": 1, "identity": identity, "pluginSha256": sha(plugin),
                     "classes": sorted(name for name in payloads if name.endswith(".class"))}
            receipt.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return plugin.parent.parent, saved


def verify_archive(app: Path, plugin: Path) -> dict:
    """Use the actual product's JVM and IntelliJ ZIP reader, without launching UI."""
    layout = app_layout(app)
    archive = plugin / "lib/native-probe.jar"
    arguments = ["--add-opens=java.base/sun.nio.ch=ALL-UNNAMED", "--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED",
                 "--class-path", os.pathsep.join(str(layout.lib / name) for name in ("platform-loader.jar", "annotations.jar")),
                 str(SOURCES / "VerifyProbeArchive.java"), str(archive)]
    cwd = None
    command = [str(layout.java), *arguments]
    if os.name == "nt":
        argument_file = plugin.parent / "verify-probe.args"
        _write_java_arguments(argument_file, arguments)
        command = [str(layout.java), "@" + argument_file.name]
        cwd = argument_file.parent
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=60)
    if completed.returncode:
        raise ValueError("Actual product archive reader rejected the probe:\n" + completed.stdout + completed.stderr)
    report = json.loads(completed.stdout)
    if report.get("status") != "pass" or not report.get("closed") or report.get("sha256") != sha(archive):
        raise ValueError("Incomplete actual-product archive verification")
    report["helperSha256"] = sha(SOURCES / "VerifyProbeArchive.java")
    report["scope"] = "Actual product ZIP reader and all plugin payload bytes; plugin startup is verified separately"
    return report


def _write_java_arguments(path: Path, arguments: list[str]) -> None:
    rendered = []
    for argument in arguments:
        if any(character in argument for character in "\r\n\0"):
            raise ValueError("Java argument contains a line break or NUL")
        rendered.append('"' + argument.replace("\\", "\\\\").replace('"', '\\"') + '"')
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def prepare_profile(profile: Path, forbidden: list[Path]) -> Path:
    profile = profile.resolve()
    if any(profile.is_relative_to(path.resolve()) for path in forbidden):
        raise ValueError("The probe profile must be outside the application, SDK and fixture")
    properties = profile / "idea.properties"
    if properties.is_file():
        parsed = {}
        for line in properties.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith(("#", "!")):
                key, value = line.split("=", 1)
                parsed[key.strip()] = value.strip()
        for name in ("config", "system", "plugins", "log"):
            value = parsed.get(f"idea.{name}.path")
            if value is None or Path(value).resolve() != (profile / name).resolve():
                raise ValueError("An existing profile must keep all four IDEA paths isolated below itself")
        return properties
    if profile.exists() and any(profile.iterdir()):
        raise ValueError("A nonempty profile without idea.properties cannot be reused")
    profile.mkdir(parents=True, exist_ok=True)
    properties.write_text("\n".join(f"idea.{name}.path={(profile / name).as_posix()}" for name in ("config", "system", "plugins", "log")) +
                          "\nidea.initially.ask.config=never\nintellij.startup.wizard=false\n", encoding="utf-8")
    return properties


def validate_report(report: dict, invocation_id: str) -> dict:
    if report.get("invocationId") != invocation_id:
        raise ValueError("The native report belongs to another invocation")
    if report.get("pluginId") != PLUGIN_ID or not report.get("pluginEnabled"):
        raise ValueError("The expected native plugin did not report startup")
    if report.get("failure") or report.get("isDumbAtCapture") or not report.get("isReadAccessAllowed"):
        raise ValueError("Native PSI inspection failed or did not execute in smart read mode")
    if not report.get("modules") or not report.get("files"):
        raise ValueError("No project/module/file evidence was captured")
    file = report["files"][0]
    if not file.get("module") or not file.get("inContent") or file.get("excluded"):
        raise ValueError("The test fixture is not in active project content")
    sdk = file.get("pythonSdk")
    if not isinstance(sdk, dict) or not sdk.get("classRootFiles") or not all(item.get("valid") and item.get("exists") for item in sdk["classRootFiles"]):
        raise ValueError("The fixture requires a configured Python SDK with valid roots")
    candidates = list(file.get("fileLightProducers", []))
    for cls in file.get("classes", []):
        candidates.extend(cls.get("lightProducers", []))
    test_candidates = [item for item in candidates if isinstance(item.get("lightConfiguration"), dict)
                       and item["lightConfiguration"].get("type") == "tests"]
    if not file.get("testFileBasedOnSettings") or not test_candidates:
        raise ValueError("Native Python test detection did not recognize the fixture")
    return {"status": "pass", "testModule": file["module"], "pythonVersion": sdk.get("version"),
            "validSdkRoots": len(sdk["classRootFiles"]), "testConfigurationCandidates": len(test_candidates)}


def run_probe(app: Path, sdk: Path, profile: Path, project: Path, report: Path, test_file: Path,
              timeout: int = 90, delay: int = 10) -> dict:
    layout = app_layout(app)
    app, sdk, project, report = app.resolve(), sdk.resolve(), project.resolve(), report.resolve()
    if not project.is_dir() or not test_file.is_file():
        raise ValueError("Select the disposable Python fixture and an existing test file")
    if report.exists() or any(report.is_relative_to(path) for path in (app, sdk, project)):
        raise ValueError("Choose a new report outside the application, SDK and fixture")
    properties = prepare_profile(profile, [app, sdk, project])
    plugin, build = build_plugin(sdk)
    verification = verify_archive(app, plugin)
    invocation_id = uuid.uuid4().hex
    report.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": 1, "application": str(app), "profile": str(profile.resolve()), "project": str(project),
              "invocationId": invocation_id, "probeBuild": build, "archiveVerification": verification,
              "limitations": ["Ordinary project trust and Python SDK selection remain required",
                              "Probe requests can populate ordinary resolution caches",
                              "No Run/Test/Debug execution or full UI acceptance is established"]}
    with tempfile.TemporaryDirectory(prefix="launch-", dir=plugin.parent) as directory:
        temporary = Path(directory)
        options = temporary / "probe.vmoptions"
        original_options = layout.contents / ("bin/pycharm.vmoptions" if layout.platform == "macos" else "bin/pycharm64.exe.vmoptions")
        flags = {"plugin.path": plugin.as_posix(), "openpycharm.probe.report": report.as_posix(),
                 "openpycharm.probe.output.root": report.parent.as_posix(), "openpycharm.probe.invocation.id": invocation_id,
                 "openpycharm.probe.file": test_file.resolve().as_posix(), "openpycharm.probe.delay.seconds": str(delay)}
        options.write_text(original_options.read_text(encoding="utf-8") + "\n" +
                           "\n".join(f"-D{key}={value}" for key, value in flags.items()) + "\n", encoding="utf-8")
        environment = dict(os.environ, OPENPYCHARM_PROPERTIES=str(properties), OPENPYCHARM_VM_OPTIONS=str(options))
        executable = layout.contents / ("MacOS/pycharm" if layout.platform == "macos" else "bin/pycharm64.exe")
        log = profile.resolve() / "native-probe-launch.log"
        with log.open("wb") as stream:
            process, job, resumed = None, None, False
            try:
                windows = layout.platform == "windows"
                job = WindowsJob() if windows else None
                options = ({"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP}
                           if windows else {"start_new_session": True})
                process = subprocess.Popen([str(executable), str(project)], env=environment, stdin=subprocess.DEVNULL,
                                           stdout=stream, stderr=subprocess.STDOUT, **options)
                result["ownedPid"] = process.pid
                if job is not None:
                    job.assign_and_resume(process)
                    resumed = True
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline and process.poll() is None and not report.is_file():
                    time.sleep(0.5)
                if not report.is_file():
                    raise ValueError("No native report before timeout/process exit; inspect the launch log and ordinary trust/SDK setup")
                native = json.loads(report.read_text(encoding="utf-8"))
                result["assessment"] = validate_report(native, invocation_id)
                result["native"] = native
            except Exception as error:
                result["assessment"] = {"status": "fail", "error": str(error)}
                if report.is_file():
                    result["native"] = json.loads(report.read_text(encoding="utf-8"))
            finally:
                if process is not None:
                    # If job assignment failed the owned launcher is still
                    # suspended. Kill it before closing the potentially empty
                    # job, just as the native startup smoke guard does.
                    if job is not None and not resumed and process.poll() is None:
                        process.kill()
                    try:
                        result["cleanup"] = stop_owned(process, job)
                    except (OSError, subprocess.SubprocessError) as error:
                        result["assessment"] = {"status": "fail", "error": "Owned-process cleanup failed: " + str(error)}
                    result["ownedProcessExit"] = process.returncode
                elif job is not None:
                    job.stop()
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = "windows-x64" if platform.system() == "Windows" else "macos-arm64"
    parser.add_argument("--app", type=Path, default=ROOT / "build/product" / ("OpenPyCharm" if target == "windows-x64" else "OpenPyCharm.app"))
    parser.add_argument("--sdk", type=Path, default=ROOT / f".tools/platform/pycharm-2026.1.4-{target}" / ("pycharm" if target == "windows-x64" else "PyCharm.app"))
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--project", type=Path, default=ROOT / "fixtures/hello-python")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--test-file", type=Path, help="Defaults to PROJECT/tests/test_calculator.py")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--build-only", action="store_true", help="Compile and verify with the actual app ZIP reader; do not launch UI")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 180 or not 0 <= args.delay <= 120:
        parser.error("Use timeout 1..180 seconds and delay 0..120 seconds")
    try:
        if args.build_only:
            plugin, build = build_plugin(args.sdk)
            result = {"pluginDirectory": str(plugin), "build": build, "archiveVerification": verify_archive(args.app, plugin),
                      "nativeApplicationLaunched": False}
        else:
            profile = args.profile or ROOT / ".state" / ("native-probe-" + uuid.uuid4().hex[:12])
            report = args.report or profile / "native-probe-report.json"
            result = run_probe(args.app, args.sdk, profile, args.project, report,
                               args.test_file or args.project / "tests/test_calculator.py", args.timeout, args.delay)
            print(json.dumps({"report": str(report.resolve()), "assessment": result["assessment"]}, ensure_ascii=False))
            if result["assessment"]["status"] != "pass":
                raise SystemExit(1)
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        parser.exit(1, f"Native probe failed: {error}\n")


if __name__ == "__main__":
    main()
