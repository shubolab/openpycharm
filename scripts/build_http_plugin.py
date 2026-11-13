#!/usr/bin/env python3
"""Compile the independently packaged native HTTP plugin without Gradle.

Uses only the authenticated OSS SDK and already cached, hash-pinned Kotlin
compiler artifacts. Never downloads dependencies or modifies the SDK/product.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

from bootstrap import PIN_PATH, validate_cached
from platform_layout import cache_lock, detect_platform_layout, java_compiler_invocation

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins/http-client"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compiler_classpath(caches: list[Path] | None = None) -> tuple[list[Path], dict]:
    pin = json.loads((PLUGIN / "compiler.lock.json").read_text(encoding="utf-8"))
    roots = caches or [Path.home() / ".gradle/caches/modules-2/files-2.1", ROOT / ".tools/kotlin"]
    artifacts = []
    for item in pin["artifacts"]:
        matches = []
        for root in roots:
            if root.is_dir():
                matches.extend(root.rglob(item["name"]))
        valid = [path.resolve() for path in matches if path.is_file() and path.stat().st_size == item["size"] and sha(path) == item["sha256"]]
        if not valid:
            raise ValueError(f"Missing authenticated cached compiler artifact {item['name']}; supply --compiler-cache. The builder does not download dependencies.")
        artifacts.append(sorted(set(valid))[0])
    return artifacts, pin


def run_java(java: Path, arguments: list[str], directory: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    command, cwd = [str(java), *arguments], None
    if os.name == "nt":
        argument_file = directory / "java.args"
        if any(any(character in argument for character in "\r\n\0") for argument in arguments):
            raise ValueError("Java arguments cannot contain line breaks or NUL")
        argument_file.write_text("\n".join('"' + argument.replace("\\", "\\\\").replace('"', '\\"') + '"' for argument in arguments) + "\n", encoding="utf-8")
        command, cwd = [str(java), "@" + argument_file.name], directory
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError("Java compiler/probe failed:\n" + result.stdout + result.stderr)
    return result


def authenticated_layout(sdk: Path):
    layout = detect_platform_layout(sdk)
    if layout.platform not in {"macos", "windows"}:
        raise ValueError("The HTTP plugin currently targets the pinned macOS/Windows SDKs")
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    if validate_cached(layout.sdk_root.parent, json.loads(PIN_PATH.read_text(encoding="utf-8")), target) != layout.sdk_root:
        raise ValueError("Use the authenticated OSS SDK")
    return layout


def compile_kotlin(layout, sources: list[Path], classes: Path, compilers: list[Path], directory: Path):
    classpath = os.pathsep.join(str(path) for path in sorted(layout.lib.glob("*.jar")))
    arguments = ["-Xmx1200m", "-cp", os.pathsep.join(map(str, compilers)), "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
                 "-no-stdlib", "-no-reflect", "-jvm-target", "21", "-module-name", "openpycharm-http",
                 "-classpath", classpath, "-d", str(classes), *map(str, sources)]
    return run_java(layout.java, arguments, directory)


def verify_archive(layout, jar: Path, directory: Path) -> dict:
    arguments = ["--add-opens=java.base/sun.nio.ch=ALL-UNNAMED", "--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED",
                 "--class-path", os.pathsep.join(str(layout.lib / name) for name in ("platform-loader.jar", "annotations.jar")),
                 str(ROOT / "tests/http_client/VerifyHttpArchive.java"), str(jar)]
    completed = run_java(layout.java, arguments, directory, timeout=60)
    report = json.loads(completed.stdout)
    if report.get("status") != "pass" or not report.get("closed") or report.get("sha256") != sha(jar):
        raise ValueError("Incomplete actual IntelliJ archive-reader verification")
    return report


def build(sdk: Path, output: Path, version: str, caches: list[Path] | None = None) -> dict:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Use a concrete HTTP plugin release version")
    layout = authenticated_layout(sdk)
    output = output.resolve()
    if not output.is_relative_to((ROOT / "build").resolve()) or output.is_relative_to(layout.sdk_root):
        raise ValueError("HTTP plugin output must be an owned directory below build")
    compilers, pin = compiler_classpath(caches)
    sources = sorted((PLUGIN / "src/main/kotlin").rglob("*.kt"))
    resources = sorted((PLUGIN / "src/main/resources").rglob("*"))
    resources = [path for path in resources if path.is_file()]
    if not sources:
        raise ValueError("No HTTP plugin sources")
    identity = {"version": version, "sdkReceiptSha256": sha(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "sources": {str(path.relative_to(ROOT)): sha(path) for path in sources + resources + [PLUGIN / "NOTICE", PLUGIN / "upstream.json", PLUGIN / "compiler.lock.json", Path(__file__), ROOT / "tests/http_client/VerifyHttpArchive.java"]},
                "compiler": pin}
    jar = output / "plugin/lib/openpycharm-http.jar"
    receipt = output / "build.json"
    output.mkdir(parents=True, exist_ok=True)
    with cache_lock(output / "build.lock"):
        if jar.is_file() and receipt.is_file():
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            if saved.get("identity") == identity and saved.get("jarSha256") == sha(jar):
                return saved
        with tempfile.TemporaryDirectory(prefix="compile-", dir=output) as name:
            temporary = Path(name)
            classes = temporary / "classes"
            classes.mkdir()
            result = compile_kotlin(layout, sources, classes, compilers, temporary)
            payloads = {path.relative_to(classes).as_posix(): path.read_bytes() for path in classes.rglob("*") if path.is_file()}
            for path in resources:
                data = path.read_bytes()
                if path.name == "plugin.xml":
                    data = data.replace(b"@VERSION@", version.encode("utf-8"))
                payloads[path.relative_to(PLUGIN / "src/main/resources").as_posix()] = data
            payloads["META-INF/NOTICE"] = (PLUGIN / "NOTICE").read_bytes()
            payloads["META-INF/openpycharm-http-upstream.json"] = (PLUGIN / "upstream.json").read_bytes()
            candidate = temporary / jar.name
            with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
                for entry, data in sorted(payloads.items()):
                    info = zipfile.ZipInfo(entry, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, data)
            jar.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(jar)
            saved = {"schema": 1, "pluginDirectory": str(jar.parent.parent), "jarSha256": sha(jar), "identity": identity,
                     "classCount": sum(name.endswith(".class") for name in payloads), "compilerWarnings": result.stderr[-6000:],
                     "archiveVerification": verify_archive(layout, jar, temporary),
                     "limitations": ["Compiled native plugin; actual native UI acceptance is recorded separately"]}
            receipt.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
            return saved


def protocol_tests(sdk: Path, output: Path, caches: list[Path] | None = None) -> dict:
    layout = authenticated_layout(sdk)
    compilers, _ = compiler_classpath(caches)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="protocol-", dir=output) as name:
        temporary = Path(name)
        classes = temporary / "classes"
        classes.mkdir()
        source = PLUGIN / "src/main/kotlin/dev/openpycharm/http"
        compile_kotlin(layout, [source / "HttpRequestDocument.kt", source / "HttpRequestCall.kt", ROOT / "tests/http_client/HttpProtocolProbe.kt"], classes, compilers, temporary)
        classpath = os.pathsep.join([str(classes), str(compilers[1])])
        completed = run_java(layout.java, ["--add-modules", "jdk.httpserver", "-cp", classpath, "dev.openpycharm.http.HttpProtocolProbeKt"], temporary, timeout=45)
        result = json.loads(completed.stdout)
        if result.get("status") != "pass" or not result.get("serverOwnedClosed"):
            raise ValueError("Incomplete HTTP protocol test report")
        plugin_jar = output.resolve() / "plugin/lib/openpycharm-http.jar"
        presentation_classes = temporary / "presentation-classes"
        presentation_classes.mkdir()
        java_sources = [ROOT / "tests/http_client/HttpPresentationProbe.java", ROOT / "tests/http_client/HttpLexerProbe.java"]
        compiler_arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath",
                              os.pathsep.join([str(plugin_jar), *map(str, sorted(layout.lib.glob("*.jar")))]),
                              "-d", str(presentation_classes), *map(str, java_sources)]
        invocation = java_compiler_invocation(layout.javac, compiler_arguments, temporary / "presentation-javac.args")
        compiled = subprocess.run(invocation.command, cwd=invocation.cwd, capture_output=True, text=True, timeout=60)
        if compiled.returncode:
            raise ValueError("Compiling response presentation/save controls failed:\n" + compiled.stdout + compiled.stderr)
        presented = run_java(layout.java, ["-cp", os.pathsep.join([str(presentation_classes), str(plugin_jar), str(layout.lib / "*")]),
                                           "dev.openpycharm.http.HttpPresentationProbe", str(temporary)], temporary, timeout=30)
        result["responsePresentationAndRawSave"] = json.loads(presented.stdout)
        if result["responsePresentationAndRawSave"].get("status") != "pass":
            raise ValueError("Response presentation/raw-save controls failed")
        lexed = run_java(layout.java, ["-cp", os.pathsep.join([str(presentation_classes), str(plugin_jar), str(layout.lib / "*")]),
                                      "dev.openpycharm.http.HttpLexerProbe"], temporary, timeout=30)
        result["nativeLexerRestartRestore"] = json.loads(lexed.stdout)
        if result["nativeLexerRestartRestore"].get("status") != "pass":
            raise ValueError("Native lexer restart/restore controls failed")
        (output / "protocol-tests.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/http-client")
    parser.add_argument("--version", default=json.loads((ROOT / "product/product.json").read_text())["version"])
    parser.add_argument("--compiler-cache", type=Path, action="append")
    parser.add_argument("--test", action="store_true", help="Run real loopback HTTP protocol controls after compilation")
    args = parser.parse_args()
    try:
        result = build(args.sdk, args.output, args.version, args.compiler_cache)
        if args.test:
            result = {**result, "protocolTests": protocol_tests(args.sdk, args.output, args.compiler_cache)}
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
