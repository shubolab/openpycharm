#!/usr/bin/env python3
"""Compile the independent, default-off frontend M0 without starting an IDE.

No tool provisioning or product packaging is invoked. The compiled fixture/cache
boundaries are this checkout's own .tools, not a general user-project feature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from bootstrap import PIN_PATH, check_space, sha256
from build_framework_plugin import sdk_layout, execution_layout, run_java
from platform_layout import cache_lock, java_compiler_invocation
from provision_frontend_tools import PIN, ROOT, DEFAULT_CACHE, load_pin, owned
from runtime_smoke import WindowsJob, WINDOWS_CREATE_SUSPENDED, WINDOWS_CREATE_NEW_PROCESS_GROUP, stop_owned

SOURCE = ROOT / "plugins/frontend"
ID = "dev.openpycharm.frontend.m0"
VERSION = "0.1.0-dev.4-m0"


def source_inputs() -> dict:
    paths = []
    if SOURCE.is_symlink() or not SOURCE.is_dir():
        raise ValueError("Frontend source must be a regular owned directory")
    for parent, directories, files in os.walk(SOURCE, followlinks=False):
        directories[:] = sorted(name for name in directories if name != "__pycache__")
        for name in directories + sorted(files):
            path = Path(parent) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("Frontend source cannot contain symlinks/special files")
            if stat.S_ISREG(mode): paths.append(path)
    paths += [ROOT / "LICENSE", Path(__file__), ROOT / "scripts/bootstrap.py", ROOT / "scripts/platform_layout.py",
              ROOT / "scripts/build_framework_plugin.py", ROOT / "scripts/provision_frontend_tools.py", PIN_PATH]
    paths += sorted((ROOT / "tests/frontend").glob("*.java"))
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Frontend build input must be a regular owned file")
        for ancestor in path.parents:
            if ancestor == ROOT: break
            if ancestor.is_symlink(): raise ValueError("Frontend build source ancestor symlink")
        else: raise ValueError("Frontend build source escaped its root")
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(paths)}


def compile_java(layout, runtime, sources: list[Path], destination: Path, argument_file: Path, extra=None):
    destination.mkdir()
    cp = sorted(layout.lib.glob("*.jar")) + (extra or [])
    arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath", os.pathsep.join(map(str, cp)),
                 "-d", str(destination), *map(str, sources)]
    command = java_compiler_invocation(runtime.javac, arguments, argument_file)
    result = subprocess.run(command.command, cwd=command.cwd, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError("Frontend compilation failed:\n" + result.stdout + result.stderr)
    return {"sdkClasspathJars": len(cp), "release": 21, "stdout": result.stdout, "stderr": result.stderr}


def expected_runtime(pin: dict, target: str) -> dict:
    items = [item for item in pin["artifacts"] if not item.get("target") or item["target"] == target]
    files = {}
    for item in items:
        if files.keys() & item["payload"].keys(): raise ValueError("Frontend pinned payload overlap")
        files.update(item["payload"])
    node = next(item for item in items if item["id"].startswith("node-"))
    return {"files": files, "entries": {"node": node["nodeExecutable"], **pin["runtimeEntries"]}}


def descriptor(data: bytes, version: str) -> bytes:
    data = data.replace(b"@VERSION@", version.encode()); root = ET.fromstring(data)
    if (root.findtext("id") != ID or root.findtext("version") != version
            or {value.text for value in root.findall("depends")} != {"com.intellij.modules.platform", "com.intellij.modules.lsp"}
            or root.find("extensions/integrationProvider").attrib.get("implementation") != "dev.openpycharm.frontend.FrontendLspProvider"):
        raise ValueError("Frontend descriptor identity/normal dependency/EP differs")
    return data


def build(sdk: Path, version: str = VERSION, host_sdk: Path | None = None) -> tuple[Path, dict]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-[A-Za-z0-9.-]+", version) is None:
        raise ValueError("Frontend M0 needs an explicit prerelease version")
    layout = sdk_layout(sdk); runtime = execution_layout(layout, host_sdk); pin = load_pin()
    identity = {"pluginId": ID, "version": version, "sources": source_inputs(),
                "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "executionSdkReceiptSha256": sha256(runtime.sdk_root.parent / ".openpycharm-platform.json"),
                "compiler": subprocess.check_output([str(runtime.javac), "-version"], text=True, stderr=subprocess.STDOUT, timeout=15).strip(),
                "compiledFixtureParent": (ROOT / ".tools/frontend-m0-fixtures").as_posix(),
                "compiledCacheParent": DEFAULT_CACHE.as_posix()}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest(); work = owned(ROOT / ".tools/frontend-plugin" / key)
    check_space(work, 64 * 1024**2); work.mkdir(parents=True, exist_ok=True)
    jar = owned(work / "plugin/lib/frontend-m0.jar"); receipt = owned(work / "build.json")
    if (work / "build.lock").is_symlink(): raise ValueError("Frontend build lock cannot be a symlink")
    with cache_lock(work / "build.lock"):
        if jar.is_file() and not jar.is_symlink() and receipt.is_file() and not receipt.is_symlink():
            saved = json.loads(receipt.read_text())
            if saved.get("identity") == identity and saved.get("jarSha256") == sha256(jar) and saved.get("archiveVerification", {}).get("status") == "pass":
                return jar.parent.parent, saved
        with tempfile.TemporaryDirectory(prefix="compile-", dir=work) as directory:
            temporary = Path(directory); generated = temporary / "FrontendBuildScope.java"
            generated.write_text("package dev.openpycharm.frontend;\nfinal class FrontendBuildScope {\n" +
                "static final String FIXTURE_PARENT=" + json.dumps(identity["compiledFixtureParent"]) + ";\n" +
                "static final String CACHE_PARENT=" + json.dumps(identity["compiledCacheParent"]) + ";\n" +
                "static final String LOCK_SHA256=" + json.dumps(sha256(PIN)) + ";\n}\n")
            classes = temporary / "classes"
            compilation = compile_java(layout, runtime, [*sorted((SOURCE / "src").rglob("*.java")), generated], classes, temporary / "javac.args")
            payloads = {path.relative_to(classes).as_posix(): path.read_bytes() for path in sorted(classes.rglob("*.class"))}
            for path in sorted((SOURCE / "resources").rglob("*")):
                if path.is_file():
                    name = path.relative_to(SOURCE / "resources").as_posix()
                    payloads[name] = descriptor(path.read_bytes(), version) if name == "META-INF/plugin.xml" else path.read_bytes()
            payloads.update({"META-INF/LICENSE": (ROOT / "LICENSE").read_bytes(), "META-INF/NOTICE": (SOURCE / "NOTICE").read_bytes(),
                             "META-INF/frontend-tools.lock.json": PIN.read_bytes()})
            for target in ("macos-arm64", "windows-x64"):
                payloads["META-INF/frontend-runtime-" + target + ".json"] = json.dumps(expected_runtime(pin, target), sort_keys=True).encode()
            candidate = temporary / "frontend-m0.jar"
            with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, content in sorted(payloads.items()):
                    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, content)
            reader_args = ["--add-opens=java.base/sun.nio.ch=ALL-UNNAMED", "--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED",
                "--class-path", os.pathsep.join(str(layout.lib / name) for name in ("platform-loader.jar", "annotations.jar")),
                str(SOURCE / "build-support/VerifyFrontendArchive.java"), str(candidate)]
            verification = json.loads(run_java(runtime, reader_args, temporary).stdout)
            if verification.get("status") != "pass" or verification.get("closed") is not True or verification.get("sha256") != sha256(candidate):
                raise ValueError("Frontend actual archive-reader verification failed")
            if source_inputs() != identity["sources"]: raise ValueError("Frontend sources changed during compilation")
            jar.parent.mkdir(parents=True, exist_ok=True); candidate.replace(jar)
            saved = {"schema": 1, "identity": identity, "version": version, "jarSha256": sha256(jar), "pluginDirectory": str(jar.parent.parent),
                     "targetPlatform": layout.platform, "executionPlatform": runtime.platform, "nativeTargetRuntime": layout.platform == runtime.platform,
                     "compilation": compilation, "classes": sorted(name for name in payloads if name.endswith(".class")),
                     "payloadSha256": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(payloads.items())},
                     "archiveVerification": verification, "productionPackaged": False, "nativeIdeStarted": False,
                     "limitations": ["Compile/archive-reader proof only; PC module/EP/service, native stdio/editor/UI and Windows execution remain separate gates"]}
            receipt.write_text(json.dumps(saved, indent=2) + "\n")
    return jar.parent.parent, saved


def native_process_check(runtime, arguments: list[str], directory: Path) -> dict:
    """Own the helper JVM and all test descendants; preserve cleanup even if it hangs."""
    command, cwd = [str(runtime.java), *arguments], None
    windows = os.name == "nt"
    if windows:
        from native_probe import _write_java_arguments
        argument_file = directory / "frontend-native.args"
        _write_java_arguments(argument_file, arguments)
        command, cwd = [str(runtime.java), "@" + argument_file.name], directory
    process = job = None; resumed = False; cleanup = None; failure = None; out = err = ""
    try:
        job = WindowsJob() if windows else None
        options = {"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP} if windows else {"start_new_session": True}
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", **options)
        if job is not None:
            job.assign_and_resume(process); resumed = True
        out, err = process.communicate(timeout=60)
        if process.returncode: failure = "Native SDK process control returned failure"
    except subprocess.TimeoutExpired as error:
        failure = "Native SDK process control exceeded its 60-second deadline"
        out = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        err = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
    except Exception as error:
        failure = type(error).__name__ + ": " + str(error)
    finally:
        try:
            if process is not None:
                if job is not None and not resumed and process.poll() is None: process.kill()
                cleanup = stop_owned(process, job)
            elif job is not None: job.stop()
        except Exception as error:
            cleanup = {"status": "fail", "ownedPid": None if process is None else process.pid, "error": str(error)}
            failure = "Native SDK control helper cleanup failed"
    if failure and process is not None:
        try: out, err = process.communicate(timeout=3)
        except Exception: pass
    if failure:
        evidence = {"failure": failure, "stdout": out, "stderr": err, "externalWatchdogCleanup": cleanup}
        (directory.parent / "native-process-last-failure.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        raise ValueError(failure + "\n" + out + err)
    result = json.loads(out); result["externalWatchdogCleanup"] = cleanup; result["stderr"] = err
    return result


def checks(sdk: Path, plugin: Path, host_sdk: Path | None = None, worker_fixture: Path | None = None, process_fixture: Path | None = None) -> dict:
    layout = sdk_layout(sdk); runtime = execution_layout(layout, host_sdk)
    directory = owned(ROOT / ".tools/frontend-checks"); directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="checks-", dir=directory) as name:
        temporary = Path(name); classes = temporary / "classes"; jar = plugin / "lib/frontend-m0.jar"
        compile_java(layout, runtime, sorted((ROOT / "tests/frontend").glob("*.java")), classes, temporary / "javac.args", [jar])
        cp = os.pathsep.join(map(str, [classes, jar, *sorted(layout.lib.glob("*.jar"))]))
        report = json.loads(run_java(runtime, ["-Djava.awt.headless=true", "-cp", cp, "dev.openpycharm.frontend.FrontendScopeTest"], temporary).stdout)
        report["boundedOutput"] = json.loads(run_java(runtime, ["-Djava.awt.headless=true", "-cp", cp,
            "dev.openpycharm.frontend.FrontendBoundedOutputTest"], temporary).stdout)
        report["lifetimeIdentity"] = json.loads(run_java(runtime, ["-Djava.awt.headless=true", "-cp", cp,
            "dev.openpycharm.frontend.FrontendLifetimeTest"], temporary).stdout)
        if process_fixture is not None:
            process_fixture = owned(process_fixture)
            marker = json.loads((process_fixture / ".openpycharm-frontend-m0.json").read_text(encoding="utf-8"))
            args = ["-Djava.awt.headless=true", "-Didea.home.path=" + str(runtime.contents), "-cp", cp,
                    "dev.openpycharm.frontend.FrontendNativeProcessCheck", str(process_fixture), marker["nonce"],
                    marker["toolsReceipt"], marker["toolsReceiptSha256"]]
            report["nativeProcessControl"] = native_process_check(runtime, args, temporary)
        if worker_fixture is not None:
            marker = json.loads((worker_fixture / ".openpycharm-frontend-m0.json").read_text())
            args = ["-Djava.awt.headless=true", "-cp", cp, "dev.openpycharm.frontend.FrontendWorkerCheck", str(worker_fixture),
                    marker["nonce"], marker["toolsReceipt"], marker["toolsReceiptSha256"]]
            report["workerAuthentication"] = json.loads(run_java(runtime, args, temporary).stdout)
        report.update(targetPlatform=layout.platform, executionPlatform=runtime.platform, nativeTargetRuntime=layout.platform == runtime.platform,
                      nativeIdeStarted=False, jarSha256=sha256(jar))
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True); parser.add_argument("--host-sdk", type=Path)
    parser.add_argument("--version", default=VERSION); parser.add_argument("--test", action="store_true")
    parser.add_argument("--worker-fixture", type=Path)
    parser.add_argument("--process-fixture", type=Path, help="Explicitly run pinned owned Node/TLS through public SDK process handler, not an IDE")
    args = parser.parse_args(); plugin, report = build(args.sdk, args.version, args.host_sdk)
    result = {"plugin": str(plugin), "build": report}
    if args.test: result["checks"] = checks(args.sdk, plugin, args.host_sdk, args.worker_fixture, args.process_fixture)
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
