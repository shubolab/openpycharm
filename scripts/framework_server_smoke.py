#!/usr/bin/env python3
"""Exercise compiled framework defaults against real local framework servers.

This validates the command model and selected interpreter, environment, working
directory and owned-process cleanup. It does not simulate native Run/Debug UI.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from build_framework_plugin import ROOT, build_plugin, run_command_tests
from runtime_smoke import WindowsJob, WINDOWS_CREATE_SUSPENDED, WINDOWS_CREATE_NEW_PROCESS_GROUP, stop_owned


def local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def server_arguments(command: dict, port: int) -> list[str]:
    args = list(command["arguments"])
    if command["framework"] == "django":
        args[args.index("127.0.0.1:8000")] = f"127.0.0.1:{port}"
    else:
        args[args.index("--port") + 1] = str(port)
    return args


def run_servers(sdk: Path, python: Path, output: Path, projects: Path | None = None) -> dict:
    # Preserve a virtualenv interpreter symlink: resolving it would select the
    # base interpreter and change the environment being tested.
    python = python.absolute()
    if not python.is_file():
        raise ValueError("Select an existing Python/venv executable")
    projects = (projects if projects is not None else ROOT / "fixtures/frameworks").resolve()
    if not all((projects / name).is_dir() for name in ("django", "flask", "fastapi")):
        raise ValueError("Select a project root containing django, flask and fastapi directories")
    output = output.resolve()
    if output.exists():
        raise ValueError("Choose a new framework smoke evidence directory")
    output.mkdir(parents=True)
    interpreter = json.loads(subprocess.check_output([str(python), "-c",
        "import json,sys;print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'basePrefix':sys.base_prefix,'version':sys.version}))"], text=True))
    plugin, build = build_plugin(sdk)
    model = run_command_tests(sdk, plugin)
    report = {"schema": 1, "status": "pass", "interpreter": interpreter, "projects": str(projects), "pluginBuild": build,
              "commandModel": model, "servers": [],
              "limitations": ["Real framework command execution, not native IDE Run/Debug acceptance",
                              "Reloaders are disabled; browser debugger and remote SDKs are outside this check"]}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for entry in model["commands"]:
        name = entry["framework"]
        port = local_port()
        marker = f"{name}-" + uuid.uuid4().hex
        cwd = projects / name
        arguments = server_arguments(entry, port)
        command = [str(python), *(["-m", entry["scriptName"]] if entry["moduleMode"] else [str(cwd / entry["scriptName"])]), *arguments]
        result = {"framework": name, "command": command, "cwd": str(cwd), "marker": marker, "port": port}
        process, job, resumed = None, None, False
        with (output / f"{name}.log").open("wb") as log:
            try:
                windows = platform.system() == "Windows"
                job = WindowsJob() if windows else None
                options = ({"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP}
                           if windows else {"start_new_session": True})
                environment = dict(os.environ, OPENPYCHARM_FRAMEWORK_PROBE=marker, PYTHONUNBUFFERED="1")
                process = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, **options)
                result["ownedPid"] = process.pid
                if job is not None:
                    job.assign_and_resume(process)
                    resumed = True
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise ValueError(f"{name} exited before serving HTTP: {process.returncode}")
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/", timeout=1) as response:
                            body = json.load(response)
                            if response.status != 200 or body != {"framework": name, "marker": marker}:
                                raise ValueError(f"Unexpected {name} HTTP response: {body}")
                            result.update(status="pass", httpStatus=response.status, response=body)
                            break
                    except (urllib.error.URLError, TimeoutError, ConnectionError):
                        time.sleep(0.1)
                else:
                    raise ValueError(f"{name} did not serve its local route before timeout")
            except Exception as error:
                report["status"] = "fail"
                result.update(status="fail", error=str(error))
            finally:
                if process is not None:
                    if job is not None and not resumed and process.poll() is None:
                        process.kill()
                    try:
                        result["cleanup"] = stop_owned(process, job)
                    except Exception as error:
                        report["status"] = "fail"
                        result["cleanupFailure"] = str(error)
                elif job is not None:
                    job.stop()
                report["servers"].append(result)
    (output / "framework-servers.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--projects", type=Path, help="Generated project root; defaults to the checked-in fixtures")
    args = parser.parse_args()
    result = run_servers(args.sdk, args.python, args.output, args.projects)
    print(json.dumps({"status": result["status"], "servers": [{"framework": item["framework"], "status": item["status"]} for item in result["servers"]]}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
