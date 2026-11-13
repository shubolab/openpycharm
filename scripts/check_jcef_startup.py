#!/usr/bin/env python3
"""Check repaired JCEF initialization without starting an IDE or native CEF.

The actual repaired Holder is cold-loaded in a fresh helper JVM. The exact
patched getInstance method and Holder fields are also compiled with a controlled
constructor to exercise concurrency and failure paths without browser startup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from bootstrap import PIN_PATH, sha256, validate_cached
from platform_layout import detect_platform_layout, java_compiler_invocation
from source_patch import apply_source_patch

ROOT = Path(__file__).resolve().parent.parent
CONTROLS = ROOT / "product/patches/jcef-startup-controls"


def method_block(source: str, signature: str) -> str:
    begin = source.index(signature)
    opening = source.index("{", begin)
    depth = 1
    for index in range(opening + 1, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[begin:index + 1]
    raise ValueError("Unbalanced pinned JCEF method")


def control_source(source: str) -> tuple[str, dict]:
    method = method_block(source, "public static @NotNull JBCefApp getInstance()")
    holder = source.index("private static final class Holder {")
    fields = source[source.index("{", holder) + 1:source.index("static @Nullable JBCefApp init()", holder)]
    if "init()" in fields or "static boolean initialized;" not in fields or "Throwable initializationFailure;" not in fields:
        raise ValueError("Pinned repaired Holder fields do not match the reviewed control boundary")
    prefix = """package com.intellij.ui.jcef;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import org.jetbrains.annotations.*;
import com.intellij.util.ExceptionUtil;
public final class JBCefApp {
  public static final AtomicInteger factoryCalls = new AtomicInteger();
  private static final AtomicBoolean ourInitialized = new AtomicBoolean(false);
  public static Supplier<JBCefApp> factory;
  public static boolean testMode;
  public final int id;
  public JBCefApp(int id) { this.id = id; }
  public static void reset(boolean mode) {
    Holder.INSTANCE = null; Holder.initialized = false; Holder.initializationFailure = null;
    ourInitialized.set(false); factoryCalls.set(0); testMode = mode; factory = null;
  }
  public static boolean wasAttempted() { return Holder.initialized && ourInitialized.get(); }
  private static final class RegistryManager {
    private static final RegistryManager INSTANCE = new RegistryManager();
    static RegistryManager getInstance() { return INSTANCE; }
    boolean is(String key) { return testMode; }
  }
"""
    suffix = """
    static @Nullable JBCefApp init() {
      ourInitialized.set(true);
      factoryCalls.incrementAndGet();
      if (StackWalker.getInstance().walk(frames -> frames.anyMatch(frame -> frame.getMethodName().equals("<clinit>")))) {
        throw new AssertionError("Constructor invoked during class initialization");
      }
      return factory.get();
    }
  }
}
"""
    rendered = prefix + method + "\nprivate static final class Holder {" + fields + suffix
    hashes = {"getInstanceSha256": hashlib.sha256(method.encode()).hexdigest(),
              "holderFieldsSha256": hashlib.sha256(fields.encode()).hexdigest()}
    return rendered, hashes


def run_java(layout, arguments: list[str], directory: Path, *, checked: bool = True) -> subprocess.CompletedProcess:
    # Source launchers and Java classpaths need a native argument file on Windows.
    command, cwd = [str(layout.java), *arguments], None
    if os.name == "nt":
        from native_probe import _write_java_arguments
        argument_file = directory / "jcef-java.args"
        _write_java_arguments(argument_file, arguments)
        command, cwd = [str(layout.java), "@" + argument_file.name], directory
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=45)
    if checked and result.returncode:
        raise ValueError("JCEF initialization control failed:\n" + result.stdout + result.stderr)
    return result


def verify(sdk: Path, repair: dict, pin_path: Path) -> dict:
    layout = detect_platform_layout(sdk)
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    artifact = Path(repair["patchJar"])
    if (not artifact.is_relative_to(ROOT / ".tools") or artifact.is_symlink()
            or sha256(artifact) != repair["patchedJarSha256"]):
        raise ValueError("JCEF controls require the owned verified repair artifact")
    original = layout.sdk_root / pin["upstreamJar"]["path"]
    if sha256(original) != pin["upstreamJar"]["sha256"]:
        raise ValueError("JCEF control original SDK JAR differs from its pin")
    record = pin["sources"][0]
    saved = ROOT / ".tools" / ("platform-jcef-startup-" + ("macos-arm64" if layout.platform == "macos" else "windows-x64")) / "source" / pin["upstream"]["commit"] / record["path"]
    if not saved.is_file() or sha256(saved) != record["upstreamSha256"]:
        # Standalone patch CLI uses the shorter cache name.
        saved = ROOT / ".tools/platform-jcef-startup/source" / pin["upstream"]["commit"] / record["path"]
    if not saved.is_file() or sha256(saved) != record["upstreamSha256"]:
        raise ValueError("The authenticated public JCEF source cache is missing")
    work = ROOT / ".tools/jcef-startup-controls"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-", dir=work) as name:
        temporary = Path(name)
        source_root = temporary / "source"
        source = source_root / record["path"]
        source.parent.mkdir(parents=True)
        source.write_bytes(saved.read_bytes())
        apply_source_patch(pin_path.parent / pin["patchFile"], source_root, pin["patchSha256"])
        if sha256(source) != record["patchedSha256"]:
            raise ValueError("JCEF control source replay differs from the patched pin")
        source_text = source.read_text(encoding="utf-8")
        control, fragment_hashes = control_source(source_text)
        fixture = temporary / "fixture/com/intellij/ui/jcef/JBCefApp.java"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(control, encoding="utf-8")
        libraries = sorted(layout.lib.rglob("*.jar"))
        sdk_classpath = os.pathsep.join(map(str, libraries))
        classes = temporary / "classes"
        classes.mkdir()
        arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath", sdk_classpath,
                     "-d", str(classes), str(fixture), str(CONTROLS / "HolderLifecycleProbe.java")]
        compiler = java_compiler_invocation(layout.javac, arguments, temporary / "javac.args")
        compiled = subprocess.run(compiler.command, cwd=compiler.cwd, text=True, capture_output=True, timeout=60)
        if compiled.returncode:
            raise ValueError("Compiling source-derived JCEF controls failed:\n" + compiled.stdout + compiled.stderr)
        home = temporary / "home"
        home.mkdir()
        common = ["-Djava.awt.headless=true", "-Duser.home=" + str(home), "--class-path"]
        lifecycle = run_java(layout, [*common, os.pathsep.join([str(classes), sdk_classpath]),
                                      "com.intellij.ui.jcef.HolderLifecycleProbe"], temporary)
        lifecycle_report = json.loads(lifecycle.stdout)
        # Red control: add the rejected non-null fast path ahead of the same
        # source-derived method. It must expose the test-mode premature publish.
        unsafe_source = control.replace("public static @NotNull JBCefApp getInstance() {",
                                        "public static @NotNull JBCefApp getInstance() {\n    if (Holder.INSTANCE != null) return Holder.INSTANCE;", 1)
        unsafe_fixture = temporary / "unsafe/com/intellij/ui/jcef/JBCefApp.java"
        unsafe_fixture.parent.mkdir(parents=True)
        unsafe_fixture.write_text(unsafe_source, encoding="utf-8")
        unsafe_classes = temporary / "unsafe-classes"
        unsafe_classes.mkdir()
        unsafe_arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath", sdk_classpath,
                            "-d", str(unsafe_classes), str(unsafe_fixture), str(CONTROLS / "HolderLifecycleProbe.java")]
        unsafe_compiler = java_compiler_invocation(layout.javac, unsafe_arguments, temporary / "unsafe-javac.args")
        unsafe_compiled = subprocess.run(unsafe_compiler.command, cwd=unsafe_compiler.cwd, text=True, capture_output=True, timeout=60)
        if unsafe_compiled.returncode:
            raise ValueError("Compiling the unsafe-publication negative control failed:\n" + unsafe_compiled.stderr)
        unsafe_result = run_java(layout, [*common, os.pathsep.join([str(unsafe_classes), sdk_classpath]),
                                         "com.intellij.ui.jcef.HolderLifecycleProbe"], temporary, checked=False)
        if unsafe_result.returncode == 0 or "Reader observed premature test-mode publication" not in unsafe_result.stderr:
            raise ValueError("The lifecycle regression did not reject unsafe test-mode publication")
        probe = str(CONTROLS / "HolderColdLoadProbe.java")
        cold_arguments = ["--add-opens", "java.base/jdk.internal.misc=ALL-UNNAMED", *common]
        cold = run_java(layout, [*cold_arguments, os.pathsep.join([str(artifact), sdk_classpath]), probe], temporary)
        cold_report = json.loads(cold.stdout)
        baseline = run_java(layout, [*cold_arguments, sdk_classpath, probe], temporary, checked=False)
        if baseline.returncode == 0 or not any(token in baseline.stderr for token in ("JBCefApp$Holder.<clinit>", "Holder initialized JCEF/application state")):
            raise ValueError("The original SDK did not fail the expected cold Holder control")
    if lifecycle_report.get("status") != "pass" or cold_report.get("status") != "pass":
        raise ValueError("Incomplete JCEF initialization control report")
    return {"status": "pass", "actualPatchedHolder": cold_report, "lifecycle": lifecycle_report,
            "originalSdkNegativeControl": {"exitCode": baseline.returncode, "expectedColdInitFailure": True},
            "unsafePublicationNegativeControl": {"exitCode": unsafe_result.returncode, "expectedPrematurePublicationFailure": True},
            "sourceFragments": fragment_hashes,
            "helperSha256": {path.name: sha256(path) for path in sorted(CONTROLS.glob("*.java"))},
            "limitations": ["Helper JVMs do not start an IDE or native CEF; restored Markdown preview remains a native runtime gate"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--pin", type=Path, required=True)
    args = parser.parse_args()
    layout = detect_platform_layout(args.sdk)
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    if validate_cached(layout.sdk_root.parent, json.loads(PIN_PATH.read_text()), target) != layout.sdk_root:
        raise ValueError("Use the authenticated source SDK")
    result = verify(layout.sdk_root, json.loads(args.metadata.read_text()), args.pin)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
