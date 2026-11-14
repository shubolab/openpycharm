#!/usr/bin/env python3
"""Run real owned local-kernel checks using an explicit, dependency-ready Python.

Does not install dependencies, start a server, contact a registered kernel, or
launch an IDE. The JSON report distinguishes kernel evidence from UI acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True, help="Test-owned Python containing kernel dependencies")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    python = args.python.expanduser().absolute()
    if not python.is_file():
        parser.error("--python must name an existing interpreter")
    identity = subprocess.run([str(python), "-c", "import sys,json,importlib.metadata as m; print(json.dumps({'python':sys.executable,'version':sys.version,'packages':{n:m.version(n) for n in ['jupyter_client','ipykernel','pyzmq','tornado','psutil']}}))"],
                              capture_output=True, text=True, timeout=15, check=True)
    environment = dict(os.environ, OPENPYCHARM_NOTEBOOK_PYTHON=str(python))
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_notebook_kernel.py", "-v"]
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=180)
    inputs = [ROOT / "plugins/notebooks/resources/kernel_bridge.py", ROOT / "plugins/notebooks/kernel-requirements.txt",
              ROOT / "tests/test_notebook_kernel.py", Path(__file__)]
    report = {"schema": 1, "status": "pass" if completed.returncode == 0 else "fail",
              "observedAt": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "runtime": json.loads(identity.stdout), "command": command,
              "exitCode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr,
              "sources": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
              "observed": ["Selected Python executable and project cwd in actual ipykernel",
                           "Stateful execute-result, stdout, stderr, raw display data and Python traceback",
                           "Busy ping/rejection, KeyboardInterrupt, restart while busy and state reset",
                           "Per-message output cap, malformed and oversized request recovery",
                           "Normal shutdown, stdin EOF and POSIX SIGTERM remove the owned kernel PID",
                           "Unrelated test-owned process survives interrupt/restart/shutdown"],
              "limitations": ["No native notebook editor desktop acceptance is implied",
                              "Windows local kernel/process cleanup is unverified on this macOS host",
                              "No remote kernels, widget comms, interactive stdin, cell debugging or full PyCharm parity are claimed",
                              "Optional user-installed packages are external runtime dependencies, not bundled IDE implementation"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.output.absolute()), "exitCode": completed.returncode}))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
