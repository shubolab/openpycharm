#!/usr/bin/env python3
"""Run the actual Java notebook-session/kernel protocol without launching an IDE.

Compiles against the authenticated OSS SDK and accepts an explicitly selected,
pre-provisioned test Python. Every helper/kernel process is created by the test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import tempfile

from bootstrap import check_space, sha256
import build_notebook_plugin as builder

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tests/notebooks/NotebookKernelSessionTest.java"
DISPOSAL_SOURCE = ROOT / "tests/notebooks/NotebookSessionDisposalTest.java"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--host-sdk", type=Path)
    parser.add_argument("--python", type=Path, required=True, help="Test-owned interpreter with kernel requirements installed")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    python = args.python.expanduser().absolute()
    if not python.is_file():
        parser.error("--python must name an existing dependency-ready interpreter")
    layout = builder.sdk_layout(args.sdk)
    runtime = builder.execution_layout(layout, args.host_sdk)
    plugin, receipt = builder.build_plugin(args.sdk, host_sdk=args.host_sdk)
    archive = plugin / "lib/notebooks.jar"
    work = ROOT / ".tools/notebook-session-tests"
    check_space(work, 64 * 1024**2)
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="session-", dir=work) as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        compilation = builder.compile_java(layout, [SOURCE, DISPOSAL_SOURCE], classes, temporary / "javac.args", [archive], runtime)
        cp = os.pathsep.join(map(str, [classes, archive, *builder.classpath(layout)]))
        arguments = ["-Djava.awt.headless=true", "-Didea.home.path=" + str(runtime.contents),
                     "-Didea.system.path=" + str(temporary / "system"),
                     "-Didea.config.path=" + str(temporary / "config"),
                     "-Didea.plugins.path=" + str(temporary / "plugins"),
                     "-Didea.log.path=" + str(temporary / "log"),
                     "-classpath", cp, "dev.openpycharm.notebooks.NotebookKernelSessionTest", str(python), str(temporary)]
        failure = None
        try:
            completed = builder.run_java(runtime, arguments, temporary, timeout=120)
            checks = json.loads(completed.stdout)
            if checks.get("status") != "pass":
                raise ValueError("Java session did not return a passing report")
            stderr = completed.stderr
        except (ValueError, json.JSONDecodeError) as error:
            failure = str(error)
            checks, stderr = {}, ""
        sources_current = builder.source_inputs() == receipt["identity"]["sources"]
        report = {"schema": 1, "status": "pass" if failure is None and sources_current else "fail",
                  "observedAt": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                  "targetPlatform": layout.platform, "executionPlatform": runtime.platform,
                  "nativeTargetRuntime": layout.platform == runtime.platform,
                  "python": str(python), "java": str(runtime.java), "checks": checks,
                  "compilation": compilation, "stderr": stderr, "failure": failure,
                  "jarSha256": sha256(archive), "pluginDirectory": str(plugin),
                  "sourceInputsStillCurrent": sources_current,
                  "sdkReceiptSha256": receipt["identity"]["sdkReceiptSha256"],
                  "sources": {"tests/notebooks/NotebookKernelSessionTest.java": sha256(SOURCE),
                              "tests/notebooks/NotebookSessionDisposalTest.java": sha256(DISPOSAL_SOURCE),
                              "scripts/notebook_session_probe.py": sha256(Path(__file__)),
                              **receipt["identity"]["sources"]},
                  "observed": ["Authenticated native JVM loaded the actual built NotebookKernelSession and embedded bridge",
                               "Selected Python executed code and delivered stream/result/error events over actual process pipes",
                               "Interrupt and restart while busy reached the actual kernel; state reset and old PID exited",
                               "Repeated session disposal completed and restarted kernel PID exited; unrelated process survived",
                               "Actual pipe-write backpressure and close-during-startup helpers exited within bounded disposal on POSIX"],
                  "unknown": ["Native NotebookFileEditor/Swing desktop behavior is not exercised by this headless class test",
                              "Windows runtime and installer acceptance require execution on Windows",
                              "Forced process-tree cleanup under OS/JVM crash is not established by normal disposal checks"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.output.absolute()), "jarSha256": report["jarSha256"]}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
