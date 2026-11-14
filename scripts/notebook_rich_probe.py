#!/usr/bin/env python3
"""Exercise real kernel rich MIME -> packaged Java renderer -> native headless Swing.

Starts only a test-owned selected interpreter/kernel, never an IDE or browser.
Matplotlib/pandas/Pillow are test producers installed separately, not IDE payloads.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

from bootstrap import check_space, sha256
import build_notebook_plugin as builder

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "tests/notebooks/NotebookRichKernelTest.java", ROOT / "tests/notebooks/NotebookRichOutputTest.java"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--host-sdk", type=Path)
    parser.add_argument("--python", type=Path, required=True, help="Owned Python with kernel and rich test producer packages")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notebook", type=Path, required=True, help="Owned path for the actual executed notebook")
    args = parser.parse_args()
    python = args.python.expanduser().absolute()
    notebook = args.notebook.expanduser().absolute()
    if not python.is_file():
        parser.error("Select an existing test-owned Python interpreter")
    if not notebook.resolve().is_relative_to((ROOT / ".tools").resolve()):
        parser.error("Capture the executed notebook only below this worktree's .tools directory")
    identity = subprocess.run([str(python), "-c", "import sys,json,importlib.metadata as m; print(json.dumps({'python':sys.executable,'version':sys.version,'packages':{n:m.version(n) for n in ['jupyter_client','ipykernel','pandas','matplotlib','Pillow','numpy']}}))"],
                              capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
    layout = builder.sdk_layout(args.sdk)
    runtime = builder.execution_layout(layout, args.host_sdk)
    plugin, receipt = builder.build_plugin(args.sdk, host_sdk=args.host_sdk)
    archive = plugin / "lib/notebooks.jar"
    work = ROOT / ".tools/notebook-rich-tests"
    check_space(work, 64 * 1024**2)
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rich-", dir=work) as directory:
        temporary = Path(directory)
        classes = temporary / "classes"
        compilation = builder.compile_java(layout, SOURCES, classes, temporary / "javac.args", [archive], runtime)
        cp = os.pathsep.join(map(str, [classes, archive, *builder.classpath(layout)]))
        arguments = ["-Djava.awt.headless=true", "--add-modules", "jdk.httpserver",
                     "-Didea.home.path=" + str(runtime.contents), "-Didea.system.path=" + str(temporary / "system"),
                     "-Didea.config.path=" + str(temporary / "config"), "-Didea.plugins.path=" + str(temporary / "plugins"),
                     "-Didea.log.path=" + str(temporary / "log"), "-classpath", cp,
                     "dev.openpycharm.notebooks.NotebookRichKernelTest", str(python), str(temporary), str(notebook)]
        failure = None
        try:
            completed = builder.run_java(runtime, arguments, temporary, timeout=150)
            checks = json.loads(completed.stdout)
            if checks.get("status") != "pass":
                raise ValueError("Rich kernel test did not return a passing report")
            stderr = completed.stderr
        except (ValueError, json.JSONDecodeError) as error:
            failure, checks, stderr = str(error), {}, ""
        current = builder.source_inputs() == receipt["identity"]["sources"]
        report = {"schema": 1, "status": "pass" if failure is None and current else "fail",
                  "observedAt": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                  "targetPlatform": layout.platform, "executionPlatform": runtime.platform,
                  "nativeTargetRuntime": layout.platform == runtime.platform,
                  "runtime": json.loads(identity.stdout), "checks": checks, "compilation": compilation,
                  "stderr": stderr, "failure": failure, "jarSha256": sha256(archive), "pluginDirectory": str(plugin),
                  "sourceInputsStillCurrent": current, "sdkReceiptSha256": receipt["identity"]["sdkReceiptSha256"],
                  "notebook": str(notebook), "notebookSha256": sha256(notebook) if notebook.is_file() else None,
                  "sources": {str(path.relative_to(ROOT)): sha256(path) for path in [*SOURCES, Path(__file__)]},
                  "pluginSources": receipt["identity"]["sources"],
                  "observed": ["The exact selected Python kernel produced actual Matplotlib PNG, Pillow JPEG, pandas HTML and IPython Markdown",
                               "Packaged Java display_id bindings applied real PNG and DataFrame updates before nbformat save/reopen",
                               "Actual native headless Swing image painting, JTable and styled JTextPane controls consumed the reopened MIME data",
                               "Unknown MIME/metadata, large integers and stored notebook trust metadata survived round trip; owned kernel exited"],
                  "unknown": ["No installed IDE, native window, project-trust click, save/undo desktop interaction or demo capture was exercised",
                              "Windows rendering/runtime/installer behavior remains unverified",
                              "Static HTML is intentionally restricted; scripts, external resources, SVG, widgets, MathJax and Markdown attachment images are not rendered"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.output.absolute()), "jarSha256": report["jarSha256"]}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
