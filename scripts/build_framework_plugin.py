#!/usr/bin/env python3
"""Compile the independent framework plugin with the authenticated SDK's javac.

No Gradle resolution, SDK copying, proprietary plugin inputs or framework
package installation is required. Real framework processes are checked separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

from bootstrap import PIN_PATH, check_space, sha256, validate_cached
from platform_layout import cache_lock, detect_platform_layout, java_compiler_invocation

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "plugins/frameworks"
PLUGIN_ID = "dev.openpycharm.frameworks"


def sdk_layout(sdk: Path):
    layout = detect_platform_layout(sdk)
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    if layout.platform not in {"macos", "windows"}:
        raise ValueError("Select the pinned macOS or Windows OSS PyCharm SDK")
    if validate_cached(layout.sdk_root.parent, json.loads(PIN_PATH.read_text()), target) != layout.sdk_root:
        raise ValueError("Compile only against the authenticated open-source SDK")
    return layout


def classpath(layout) -> list[Path]:
    return sorted(layout.lib.glob("*.jar")) + sorted((layout.contents / "plugins/python-ce/lib").rglob("*.jar"))


def compile_java(layout, sources: list[Path], destination: Path, argument_file: Path, extra_classpath: list[Path] | None = None):
    destination.mkdir()
    arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath",
                 os.pathsep.join(map(str, classpath(layout) + (extra_classpath or []))),
                 "-d", str(destination), *map(str, sources)]
    invocation = java_compiler_invocation(layout.javac, arguments, argument_file)
    result = subprocess.run(invocation.command, cwd=invocation.cwd, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise ValueError("Framework Java compilation failed:\n" + result.stdout + result.stderr)
    return {"stdout": result.stdout, "stderr": result.stderr}


def build_plugin(sdk: Path) -> tuple[Path, dict]:
    layout = sdk_layout(sdk)
    source_files = sorted(path for path in SOURCE.rglob("*") if path.is_file()) + [ROOT / "LICENSE", Path(__file__).resolve()]
    if any(path.is_symlink() for path in source_files):
        raise ValueError("Plugin source symlinks are not supported")
    identity = {"pluginId": PLUGIN_ID, "sources": {path.relative_to(ROOT).as_posix(): sha256(path) for path in source_files},
                "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "compiler": subprocess.check_output([str(layout.javac), "-version"], text=True, stderr=subprocess.STDOUT, timeout=15).strip()}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    work = ROOT / ".tools/framework-plugin" / key
    check_space(work, 64 * 1024**2)
    work.mkdir(parents=True, exist_ok=True)
    plugin = work / "plugin/lib/frameworks.jar"
    receipt = work / "build.json"
    with cache_lock(work / "build.lock"):
        if plugin.is_file() and receipt.is_file():
            saved = json.loads(receipt.read_text())
            if saved.get("identity") == identity and saved.get("pluginSha256") == sha256(plugin):
                return plugin.parent.parent, saved
        with tempfile.TemporaryDirectory(prefix="compile-", dir=work) as directory:
            temporary = Path(directory)
            classes = temporary / "classes"
            compilation = compile_java(layout, sorted((SOURCE / "src").rglob("*.java")), classes, temporary / "javac.args")
            payloads = {path.relative_to(classes).as_posix(): path.read_bytes() for path in classes.rglob("*.class")}
            payloads.update({path.relative_to(SOURCE / "resources").as_posix(): path.read_bytes()
                             for path in (SOURCE / "resources").rglob("*") if path.is_file()})
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
            plugin.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(plugin)
            saved = {"schema": 1, "identity": identity, "pluginSha256": sha256(plugin), "compilation": compilation,
                     "classes": sorted(name for name in payloads if name.endswith(".class"))}
            receipt.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return plugin.parent.parent, saved


def run_command_tests(sdk: Path, plugin: Path) -> dict:
    layout = sdk_layout(sdk)
    with tempfile.TemporaryDirectory(prefix="framework-tests-", dir=plugin.parent) as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        compile_java(layout, [ROOT / "tests/frameworks/FrameworkCommandTest.java"], classes, temporary / "javac.args",
                     [plugin / "lib/frameworks.jar"])
        cp = os.pathsep.join(map(str, [classes, plugin / "lib/frameworks.jar", *classpath(layout)]))
        arguments = ["-classpath", cp, "dev.openpycharm.frameworks.FrameworkCommandTest"]
        command, cwd = [str(layout.java), *arguments], None
        if os.name == "nt":
            from native_probe import _write_java_arguments
            argument_file = temporary / "tests.args"
            _write_java_arguments(argument_file, arguments)
            command, cwd = [str(layout.java), "@" + argument_file.name], temporary
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=45)
        if result.returncode:
            raise ValueError("Framework argument checks failed:\n" + result.stdout + result.stderr)
        report = json.loads(result.stdout)
        if report.get("status") != "pass":
            raise ValueError("Framework argument checks returned no passing report")
        return report


def build_native_probe(sdk: Path, plugin: Path) -> Path:
    layout = sdk_layout(sdk)
    sources = ROOT / "tests/frameworks/native"
    identity = {path.name: sha256(path) for path in sorted(sources.glob("*")) if path.is_file()}
    identity["frameworkPlugin"] = sha256(plugin / "lib/frameworks.jar")
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output = plugin.parent / ("native-probe-" + key)
    output.mkdir(exist_ok=True)
    archive = output / "lib/framework-probe.jar"
    with tempfile.TemporaryDirectory(prefix="probe-compile-", dir=output) as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        compile_java(layout, [sources / "FrameworkProbe.java"], classes, temporary / "javac.args", [plugin / "lib/frameworks.jar"])
        archive.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(classes.rglob("*.class")):
                bundle.writestr(path.relative_to(classes).as_posix(), path.read_bytes())
            bundle.writestr("META-INF/plugin.xml", (sources / "plugin.xml").read_bytes())
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--build-native-probe", action="store_true")
    args = parser.parse_args()
    plugin, receipt = build_plugin(args.sdk)
    result = {"plugin": str(plugin), "build": receipt}
    if args.test:
        result["commandTests"] = run_command_tests(args.sdk, plugin)
    if args.build_native_probe:
        result["nativeProbe"] = str(build_native_probe(args.sdk, plugin))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
