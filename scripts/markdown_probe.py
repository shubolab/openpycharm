#!/usr/bin/env python3
"""Observe actual cold Markdown/JCEF startup in an isolated owned native app."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import zipfile

from bootstrap import PIN_PATH, sha256, validate_cached
from framework_probe import assess_packaged_startup
from native_probe import app_layout, prepare_profile
from platform_layout import java_compiler_invocation, detect_platform_layout
from provenance import verify_source_inputs, verify_product_plugins
from runtime_smoke import WindowsJob, WINDOWS_CREATE_NEW_PROCESS_GROUP, WINDOWS_CREATE_SUSPENDED, log_observation, stop_owned

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "tests/markdown"


def build_probe(sdk: Path) -> tuple[Path, dict]:
    layout = detect_platform_layout(sdk)
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    if validate_cached(layout.sdk_root.parent, json.loads(PIN_PATH.read_text()), target) != layout.sdk_root:
        raise ValueError("Use the authenticated pinned OSS SDK")
    identity = {"sources": {p.name: sha256(p) for p in sorted(SOURCES.glob("*")) if p.is_file()},
                "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json")}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output = ROOT / ".tools/markdown-probe" / key
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compile-", dir=output) as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        classes.mkdir()
        classpath = sorted(layout.lib.rglob("*.jar")) + sorted((layout.contents / "plugins/markdown").rglob("*.jar"))
        args = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath", os.pathsep.join(map(str, classpath)),
                "-d", str(classes), str(SOURCES / "MarkdownStartupProbe.java")]
        compiler = java_compiler_invocation(layout.javac, args, temporary / "javac.args")
        result = subprocess.run(compiler.command, cwd=compiler.cwd, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise ValueError("Compiling Markdown startup probe failed:\n" + result.stdout + result.stderr)
        jar = output / "lib/markdown-probe.jar"
        jar.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(classes.rglob("*.class")):
                archive.writestr(path.relative_to(classes).as_posix(), path.read_bytes())
            archive.writestr("META-INF/plugin.xml", (SOURCES / "plugin.xml").read_bytes())
    return output, {"identity": identity, "jarSha256": sha256(jar)}


def assess(native: dict, nonce: str) -> dict:
    required = ("httpSettingsColdBefore", "migrationServiceColdBefore", "jcefStartedAfterConstruction",
                "httpSettingsCreatedAfter", "migrationServiceCreatedAfter", "nativeBrowserRendered")
    if (native.get("invocationId") != nonce or native.get("status") != "pass" or native.get("failure") or native.get("cleanupFailure")
            or not all(native.get(key) is True for key in required)
            or native.get("panelClass") != "org.intellij.plugins.markdown.ui.preview.jcef.MarkdownJCEFHtmlPanel"
            or nonce not in native.get("renderedText", "") or "Markdown preview 中文" not in native.get("renderedText", "")):
        raise ValueError("Native cold Markdown construction/rendering proof is incomplete: " + str(native.get("failure", native.get("cleanupFailure"))))
    return {"status": "pass", "scope": "Cold actual Markdown panel, proxy/migration service creation and native DOM rendering"}


def run_probe(app: Path, sdk: Path, profile: Path) -> dict:
    layout = app_layout(app)
    manifest = json.loads((layout.contents / "openpycharm-build.json").read_text())
    verify_source_inputs(manifest)
    verified_plugins = verify_product_plugins(manifest, layout.contents)
    repair = next((fix for fix in manifest.get("platformRepairs", {}).get("fixes", []) if fix["name"] == "jcef-startup"), None)
    if not repair or repair.get("startupControls", {}).get("status") != "pass":
        raise ValueError("The candidate does not include the source-replayed JCEF repair and passing build controls")
    with zipfile.ZipFile(layout.contents / repair["jar"]) as archive:
        if any(hashlib.sha256(archive.read(name)).hexdigest() != digest for name, digest in repair["classSha256"].items()):
            raise ValueError("Candidate JCEF class bytes differ from its compiled repair receipt")
    profile = profile.resolve()
    if profile.exists():
        raise ValueError("Choose a new isolated Markdown probe profile")
    properties = prepare_profile(profile, [app, sdk])
    home = profile / "home"
    home.mkdir()
    plugin, build = build_probe(sdk)
    nonce = uuid.uuid4().hex
    report = profile / "markdown-native.json"
    result = {"schema": 1, "application": str(app.resolve()), "sourceCommit": manifest.get("sourceCommit"),
              "profile": str(profile), "isolatedJvmHome": str(home), "invocationId": nonce,
              "verifiedPluginJars": verified_plugins, "testPlugin": build, "repair": repair,
              "limitations": ["Actual API panel construction/rendering; restoring an existing README project and final installed desktop flow remain separate gates"]}
    with tempfile.TemporaryDirectory(prefix="markdown-vm-", dir=profile) as directory:
        vmoptions = Path(directory) / "markdown.vmoptions"
        original = layout.contents / ("bin/pycharm.vmoptions" if layout.platform == "macos" else "bin/pycharm64.exe.vmoptions")
        flags = {"user.home": home.as_posix(), "plugin.path": plugin.as_posix(),
                 "openpycharm.markdown.probe.report": report.as_posix(), "openpycharm.markdown.probe.root": profile.as_posix(),
                 "openpycharm.markdown.probe.nonce": nonce}
        if any(any(char in value for char in "\0\r\n") for value in flags.values()):
            raise ValueError("Invalid native probe VM property")
        vmoptions.write_text(original.read_text() + "\n" + "\n".join(f"-D{key}={value}" for key, value in flags.items()) + "\n")
        environment = dict(os.environ, OPENPYCHARM_PROPERTIES=str(properties), OPENPYCHARM_VM_OPTIONS=str(vmoptions))
        executable = layout.contents / ("MacOS/pycharm" if layout.platform == "macos" else "bin/pycharm64.exe")
        process, job, resumed = None, None, False
        with (profile / "markdown-launch.log").open("wb") as log:
            try:
                windows = layout.platform == "windows"
                job = WindowsJob() if windows else None
                options = {"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP} if windows else {"start_new_session": True}
                process = subprocess.Popen([str(executable)], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **options)
                result["ownedPid"] = process.pid
                if job is not None:
                    job.assign_and_resume(process); resumed = True
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline and process.poll() is None and not report.is_file():
                    time.sleep(0.2)
                if not report.is_file():
                    raise ValueError("Native Markdown probe produced no report before timeout/process exit")
                native = json.loads(report.read_text())
                result["native"] = native
                result["assessment"] = assess(native, nonce)
                process.wait(timeout=20)
                result["nativeGracefulExit"] = process.returncode
                if process.returncode != 0:
                    raise ValueError("Native Markdown process did not exit normally")
            except Exception as error:
                result["assessment"] = {"status": "fail", "error": str(error)}
            finally:
                if process is not None:
                    if job is not None and not resumed and process.poll() is None:
                        process.kill()
                    try:
                        result["cleanup"] = stop_owned(process, job)
                    except Exception as error:
                        result["cleanupFailure"] = str(error)
                        result["assessment"] = {"status": "fail", "error": "Owned Markdown process cleanup failed: " + str(error)}
                elif job is not None:
                    job.stop()
    log = profile / "log/idea.log"
    if log.is_file():
        observation = log_observation(log.read_text(errors="replace"), profile, profile, manifest["upstreamBuild"], manifest["plugins"])
        result["logObservation"] = observation
        try:
            assess_packaged_startup(observation, manifest)
        except ValueError as error:
            result["assessment"] = {"status": "fail", "error": str(error)}
    else:
        result["assessment"] = {"status": "fail", "error": "Native IDEA log is missing"}
    (profile / "markdown-startup.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(args.app, args.sdk, args.profile)
    print(json.dumps({"assessment": result["assessment"], "profile": result["profile"], "ownedPid": result.get("ownedPid")}))
    if result["assessment"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
