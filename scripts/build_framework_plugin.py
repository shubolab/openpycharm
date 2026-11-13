#!/usr/bin/env python3
"""Compile the independent framework plugin with an authenticated native JBR.

Target classes come only from the authenticated OSS SDK. An explicit native
host SDK supports cross-platform classpath checks without claiming target
runtime acceptance. No Gradle, dependency downloads or SDK copies are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from bootstrap import PIN_PATH, check_space, sha256, validate_cached
from platform_layout import cache_lock, detect_platform_layout, java_compiler_invocation

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "plugins/frameworks"
PLUGIN_ID = "dev.openpycharm.frameworks"


def sdk_layout(sdk: Path):
    layout = detect_platform_layout(sdk)
    if layout.platform not in {"macos", "windows"}:
        raise ValueError("Select the pinned macOS or Windows OSS PyCharm SDK")
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    if validate_cached(layout.sdk_root.parent, json.loads(PIN_PATH.read_text()), target) != layout.sdk_root:
        raise ValueError("Compile only against the authenticated open-source SDK")
    return layout


def execution_layout(target, host_sdk: Path | None = None):
    runtime = sdk_layout(host_sdk) if host_sdk is not None else target
    expected = {"Darwin": "macos", "Windows": "windows"}.get(platform.system())
    if runtime.platform != expected:
        raise ValueError("Use an authenticated native --host-sdk for cross-platform classpath checks")
    return runtime


def classpath(layout) -> list[Path]:
    return sorted(layout.lib.glob("*.jar")) + sorted((layout.contents / "plugins/python-ce/lib").rglob("*.jar"))


def source_inputs() -> dict[str, str]:
    for directory in (ROOT / "plugins", SOURCE):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Framework source symlinks and special directories are not supported")
    files = []
    for parent, directories, names in os.walk(SOURCE, followlinks=False):
        directories[:] = sorted(name for name in directories if name != "__pycache__")
        for name in directories + sorted(names):
            path = Path(parent) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("Framework source symlinks and special files are not supported")
            if stat.S_ISREG(mode):
                files.append(path)
    files += [ROOT / "LICENSE", Path(__file__).resolve(), ROOT / "scripts/bootstrap.py",
              ROOT / "scripts/platform_layout.py", PIN_PATH, ROOT / "product/product.json"]
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Framework build input must be a regular file")
        for parent in path.parents:
            if parent == ROOT:
                break
            if parent.is_symlink() or not parent.is_dir():
                raise ValueError("Framework build input ancestor cannot contain symlinks or special directories")
        else:
            raise ValueError("Framework build input escaped the owned source root")
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(files)}


def compile_java(layout, sources: list[Path], destination: Path, argument_file: Path,
                 extra_classpath: list[Path] | None = None, runtime=None):
    destination.mkdir()
    arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath",
                 os.pathsep.join(map(str, classpath(layout) + (extra_classpath or []))),
                 "-d", str(destination), *map(str, sources)]
    invocation = java_compiler_invocation((runtime or layout).javac, arguments, argument_file)
    result = subprocess.run(invocation.command, cwd=invocation.cwd, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise ValueError("Framework Java compilation failed:\n" + result.stdout + result.stderr)
    return {"stdout": result.stdout, "stderr": result.stderr}


def run_java(runtime, arguments: list[str], directory: Path, timeout: int = 45):
    command, cwd = [str(runtime.java), *arguments], None
    if os.name == "nt":
        from native_probe import _write_java_arguments
        argument_file = directory / "framework-java.args"
        _write_java_arguments(argument_file, arguments)
        command, cwd = [str(runtime.java), "@" + argument_file.name], directory
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if completed.returncode:
        raise ValueError("Framework JVM checks failed:\n" + completed.stdout + completed.stderr)
    return completed


def verify_archive(layout, runtime, jar: Path, directory: Path) -> dict:
    arguments = ["--add-opens=java.base/sun.nio.ch=ALL-UNNAMED", "--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED",
                 "--class-path", os.pathsep.join(str(layout.lib / name) for name in ("platform-loader.jar", "annotations.jar")),
                 str(SOURCE / "build-support/VerifyFrameworkArchive.java"), str(jar)]
    report = json.loads(run_java(runtime, arguments, directory, timeout=60).stdout)
    if report.get("status") != "pass" or report.get("closed") is not True or report.get("sha256") != sha256(jar):
        raise ValueError("Incomplete actual IntelliJ archive-reader verification")
    return report


def render_descriptor(data: bytes, version: str) -> bytes:
    data = data.replace(b"@VERSION@", version.encode("utf-8"))
    descriptor = ET.fromstring(data)
    if descriptor.tag != "idea-plugin" or descriptor.findtext("id") != PLUGIN_ID or descriptor.findtext("version") != version:
        raise ValueError("Framework descriptor identity/version differs from the requested product")
    return data


def build_plugin(sdk: Path, version: str | None = None, host_sdk: Path | None = None) -> tuple[Path, dict]:
    version = version if version is not None else json.loads((ROOT / "product/product.json").read_text())["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Use a concrete framework plugin release version")
    layout = sdk_layout(sdk)
    runtime = execution_layout(layout, host_sdk)
    identity = {"pluginId": PLUGIN_ID, "version": version, "sources": source_inputs(),
                "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "executionSdkReceiptSha256": sha256(runtime.sdk_root.parent / ".openpycharm-platform.json"),
                "compiler": subprocess.check_output([str(runtime.javac), "-version"], text=True, stderr=subprocess.STDOUT, timeout=15).strip()}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    work = ROOT / ".tools/framework-plugin" / key
    check_space(work, 64 * 1024**2)
    work.mkdir(parents=True, exist_ok=True)
    plugin = work / "plugin/lib/frameworks.jar"
    receipt = work / "build.json"
    with cache_lock(work / "build.lock"):
        if plugin.is_file() and not plugin.is_symlink() and receipt.is_file() and not receipt.is_symlink():
            saved = json.loads(receipt.read_text())
            digest = sha256(plugin)
            if (saved.get("identity") == identity and saved.get("pluginSha256") == digest and saved.get("jarSha256") == digest
                    and saved.get("archiveVerification", {}).get("status") == "pass"):
                return plugin.parent.parent, saved
        with tempfile.TemporaryDirectory(prefix="compile-", dir=work) as directory:
            temporary = Path(directory)
            classes = temporary / "classes"
            compilation = compile_java(layout, sorted((SOURCE / "src").rglob("*.java")), classes, temporary / "javac.args", runtime=runtime)
            payloads = {path.relative_to(classes).as_posix(): path.read_bytes() for path in classes.rglob("*.class")}
            for path in sorted((SOURCE / "resources").rglob("*")):
                if path.is_file():
                    name = path.relative_to(SOURCE / "resources").as_posix()
                    data = path.read_bytes()
                    payloads[name] = render_descriptor(data, version) if name == "META-INF/plugin.xml" else data
            payloads["META-INF/LICENSE"] = (ROOT / "LICENSE").read_bytes()
            payloads["META-INF/NOTICE"] = (SOURCE / "NOTICE").read_bytes()
            if "dev/openpycharm/frameworks/FrameworkRunConfiguration.class" not in payloads:
                raise ValueError("Framework configuration class is missing")
            candidate = temporary / "frameworks.jar"
            with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in sorted(payloads.items()):
                    entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, data)
            verification = verify_archive(layout, runtime, candidate, temporary)
            if source_inputs() != identity["sources"]:
                raise ValueError("Framework build inputs changed during compilation; build again")
            plugin.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(plugin)
            digest = sha256(plugin)
            saved = {"schema": 1, "identity": identity, "pluginDirectory": str(plugin.parent.parent),
                     "pluginSha256": digest, "jarSha256": digest, "version": version, "compilation": compilation,
                     "targetPlatform": layout.platform, "executionPlatform": runtime.platform,
                     "nativeTargetRuntime": layout.platform == runtime.platform, "archiveVerification": verification,
                     "classes": sorted(name for name in payloads if name.endswith(".class")),
                     "limitations": ["Compiled independent plugin; native UI and installed-product acceptance are separate checks"]}
            receipt.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return plugin.parent.parent, saved


def run_command_tests(sdk: Path, plugin: Path, host_sdk: Path | None = None) -> dict:
    layout = sdk_layout(sdk)
    runtime = execution_layout(layout, host_sdk)
    test_work = ROOT / ".tools/framework-tests"
    check_space(test_work, 64 * 1024**2)
    test_work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="checks-", dir=test_work) as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        compile_java(layout, [ROOT / "tests/frameworks/FrameworkCommandTest.java", ROOT / "tests/frameworks/FrameworkProjectFilesTest.java",
                             ROOT / "tests/frameworks/FrameworkProjectSettingsTest.java"], classes, temporary / "javac.args",
                     [plugin / "lib/frameworks.jar"], runtime)
        cp = os.pathsep.join(map(str, [classes, plugin / "lib/frameworks.jar", *classpath(layout)]))
        report = None
        for class_name, key in (("FrameworkCommandTest", None), ("FrameworkProjectFilesTest", "templateTests"),
                                ("FrameworkProjectSettingsTest", "settingsTests")):
            completed = run_java(runtime, ["-classpath", cp, "dev.openpycharm.frameworks." + class_name], temporary)
            result = json.loads(completed.stdout)
            if result.get("status") != "pass":
                raise ValueError("Framework check returned no passing report: " + class_name)
            if key is None:
                report = result
            else:
                report[key] = result
        report.update(targetPlatform=layout.platform, executionPlatform=runtime.platform,
                      nativeTargetRuntime=layout.platform == runtime.platform, jarSha256=sha256(plugin / "lib/frameworks.jar"))
        return report


def build_native_probe(sdk: Path, plugin: Path, host_sdk: Path | None = None) -> Path:
    layout = sdk_layout(sdk)
    runtime = execution_layout(layout, host_sdk)
    sources = ROOT / "tests/frameworks/native"
    identity = {path.name: sha256(path) for path in sorted(sources.glob("*")) if path.is_file()}
    identity.update(frameworkPlugin=sha256(plugin / "lib/frameworks.jar"),
                    sdkReceipt=sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                    executionSdkReceipt=sha256(runtime.sdk_root.parent / ".openpycharm-platform.json"),
                    builder=sha256(Path(__file__)))
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output = ROOT / ".tools/framework-native-probe" / key
    check_space(output, 64 * 1024**2)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "lib/framework-probe.jar"
    with cache_lock(output / "build.lock"):
        with tempfile.TemporaryDirectory(prefix="probe-compile-", dir=output) as directory:
            temporary = Path(directory)
            classes = temporary / "classes"
            compile_java(layout, sorted(sources.glob("*.java")), classes, temporary / "javac.args", [plugin / "lib/frameworks.jar"], runtime)
            candidate = temporary / archive.name
            payloads = {path.relative_to(classes).as_posix(): path.read_bytes() for path in sorted(classes.rglob("*.class"))}
            payloads["META-INF/plugin.xml"] = (sources / "plugin.xml").read_bytes()
            with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as bundle:
                for name, data in sorted(payloads.items()):
                    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    bundle.writestr(info, data)
            archive.parent.mkdir(exist_ok=True)
            candidate.replace(archive)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--version", help="Concrete version; defaults to product/product.json")
    parser.add_argument("--host-sdk", type=Path, help="Authenticated native SDK for cross-platform classpath checks; not target runtime acceptance")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--build-native-probe", action="store_true")
    args = parser.parse_args()
    plugin, receipt = build_plugin(args.sdk, args.version, args.host_sdk)
    result = {"plugin": str(plugin), "build": receipt}
    if args.test:
        result["commandTests"] = run_command_tests(args.sdk, plugin, args.host_sdk)
    if args.build_native_probe:
        result["nativeProbe"] = str(build_native_probe(args.sdk, plugin, args.host_sdk))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
