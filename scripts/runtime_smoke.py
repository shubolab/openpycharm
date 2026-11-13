#!/usr/bin/env python3
"""Check a real native product startup with an isolated profile.

The normal project trust flow remains active. A startup receipt proves only
the observed launch, identities, paths, loaded plugins and log window. It does
not replace Run/Test/Debug or other native UI acceptance.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import time

from bootstrap import ROOT, sha256

# Win32 CreateProcess flags. CREATE_SUSPENDED is deliberately not accessed
# through subprocess: Python 3.12's module does not export that constant.
# https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags
WINDOWS_CREATE_SUSPENDED = 0x00000004
WINDOWS_CREATE_NEW_PROCESS_GROUP = 0x00000200


class WindowsJob:
    """Own a suspended launcher and its descendants in a kill-on-close job."""

    def __init__(self) -> None:
        import ctypes as ct
        from ctypes import wintypes as wt

        class BasicLimits(ct.Structure):
            _fields_ = [("processTime", ct.c_int64), ("jobTime", ct.c_int64),
                        ("flags", wt.DWORD), ("minimumWorkingSet", ct.c_size_t),
                        ("maximumWorkingSet", ct.c_size_t), ("activeProcessLimit", wt.DWORD),
                        ("affinity", ct.c_size_t), ("priorityClass", wt.DWORD),
                        ("schedulingClass", wt.DWORD)]

        class IoCounters(ct.Structure):
            _fields_ = [(name, ct.c_uint64) for name in
                        ("readOperations", "writeOperations", "otherOperations",
                         "readBytes", "writeBytes", "otherBytes")]

        class ExtendedLimits(ct.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                        ("processMemory", ct.c_size_t), ("jobMemory", ct.c_size_t),
                        ("peakProcessMemory", ct.c_size_t), ("peakJobMemory", ct.c_size_t)]

        class ThreadEntry(ct.Structure):
            _fields_ = [("size", wt.DWORD), ("usage", wt.DWORD), ("threadId", wt.DWORD),
                        ("ownerPid", wt.DWORD), ("basePriority", wt.LONG),
                        ("deltaPriority", wt.LONG), ("flags", wt.DWORD)]

        self.ct, self.wt, self.ThreadEntry = ct, wt, ThreadEntry
        kernel = self.kernel = ct.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ct.c_void_p, wt.LPCWSTR], wt.HANDLE),
            "SetInformationJobObject": ([wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD], wt.BOOL),
            "AssignProcessToJobObject": ([wt.HANDLE, wt.HANDLE], wt.BOOL),
            "OpenProcess": ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            "TerminateJobObject": ([wt.HANDLE, wt.UINT], wt.BOOL),
            "CloseHandle": ([wt.HANDLE], wt.BOOL),
            "CreateToolhelp32Snapshot": ([wt.DWORD, wt.DWORD], wt.HANDLE),
            "Thread32First": ([wt.HANDLE, ct.POINTER(ThreadEntry)], wt.BOOL),
            "Thread32Next": ([wt.HANDLE, ct.POINTER(ThreadEntry)], wt.BOOL),
            "OpenThread": ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            "ResumeThread": ([wt.HANDLE], wt.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(kernel, name)
            function.argtypes, function.restype = arguments, result
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ct.WinError(ct.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, 9, ct.byref(limits), ct.sizeof(limits)):
            kernel.CloseHandle(self.handle)
            raise ct.WinError(ct.get_last_error())

    def assign_and_resume(self, process: subprocess.Popen) -> None:
        ct, kernel = self.ct, self.kernel
        handle = kernel.OpenProcess(0x0101, False, process.pid)  # SET_QUOTA | TERMINATE
        if not handle:
            raise ct.WinError(ct.get_last_error())
        try:
            if not kernel.AssignProcessToJobObject(self.handle, handle):
                raise ct.WinError(ct.get_last_error())
        finally:
            kernel.CloseHandle(handle)
        snapshot = kernel.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ct.c_void_p(-1).value:
            raise ct.WinError(ct.get_last_error())
        threads = []
        try:
            entry = self.ThreadEntry()
            entry.size = ct.sizeof(entry)
            available = kernel.Thread32First(snapshot, ct.byref(entry))
            while available:
                if entry.ownerPid == process.pid:
                    threads.append(entry.threadId)
                available = kernel.Thread32Next(snapshot, ct.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        if len(threads) != 1:
            raise ValueError("Expected one suspended launcher thread before execution")
        thread = kernel.OpenThread(0x0002, False, threads[0])  # THREAD_SUSPEND_RESUME
        if not thread:
            raise ct.WinError(ct.get_last_error())
        try:
            if kernel.ResumeThread(thread) != 1:
                raise ValueError("Owned launcher thread was not suspended exactly once")
        finally:
            kernel.CloseHandle(thread)

    def stop(self) -> None:
        if self.handle:
            self.kernel.TerminateJobObject(self.handle, 0)
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def stop_owned(process: subprocess.Popen, job: WindowsJob | None) -> dict:
    if job is not None:
        job.stop()
        process.wait(timeout=15)
        return {"mode": "owned-windows-job", "pid": process.pid, "exitCode": process.returncode}
    # start_new_session makes this process the leader of its own process group.
    # Signals target that owned group, never an application name or unrelated PID.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)
    return {"mode": "owned-posix-session", "pid": process.pid, "exitCode": process.returncode}


def log_observation(text: str, profile: Path, project: Path, build: str) -> dict:
    def normalized(value: str) -> str:
        value = value.replace("\\", "/")
        return value.casefold() if platform.system() == "Windows" else value

    plugin_lines = [line for line in text.splitlines() if "Loaded bundled plugins:" in line]
    plugins = {name: any(re.search(r"(?:plugins: |, )" + re.escape(name) + r" \(", line)
                         for line in plugin_lines)
               for name in ("Python Community Edition", "Git", "Terminal")}
    paths = {}
    for name in ("config", "system", "plugins", "log"):
        matches = re.findall(r"^\s*idea\." + name + r"\.path=(.+)$", text, re.MULTILINE)
        paths[name] = any(normalized(value.split(" -> ", 1)[0].strip()) == normalized(str(profile / name))
                          for value in matches)
    severity = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ \[\s*\d+\]\s+(ERROR|SEVERE|WARN)\s+-")
    levels = [(line, match.group(1)) for line in text.splitlines() if (match := severity.search(line))]
    errors = [line for line, level in levels if level in {"ERROR", "SEVERE"}]
    warnings = [line for line, level in levels if level == "WARN"]
    identity = bool(re.search(r"IDE: OpenPyCharm \(build #PC-" + re.escape(build) + r"(?:,|\))", text))
    vendor = any(re.search(r"-Didea\.vendor\.name=OpenPyCharm(?=[,\]\s]|$)", line)
                 for line in text.splitlines() if "JVM options:" in line)
    project_requested = normalized(str(project)) in normalized(text)
    project_opened = bool(re.search(r"Project " + re.escape(project.name) + r" was added to the list of open projects", text))
    return {"ideStarted": "IDE STARTED" in text, "productIdentity": identity,
            "vendorIdentity": vendor, "isolatedPaths": paths, "loadedPlugins": plugins,
            "projectOpenRequested": project_requested, "projectOpenedInLog": project_opened,
            "errorCount": len(errors), "errors": errors[:50],
            "warningCount": len(warnings), "warnings": warnings[:20]}


def startup_ready(observation: dict) -> bool:
    return (all(observation.get(key, False) for key in
                ("ideStarted", "productIdentity", "vendorIdentity", "projectOpenRequested"))
            and all(observation.get("isolatedPaths", {}).get(name, False)
                    for name in ("config", "system", "plugins", "log"))
            and all(observation.get("loadedPlugins", {}).get(name, False)
                    for name in ("Python Community Edition", "Git", "Terminal"))
            and observation.get("errorCount", 1) == 0)


def run_smoke(app: Path, profile: Path | None = None, *, timeout: int = 120, observe: int = 10) -> dict:
    if platform.system() not in ("Darwin", "Windows"):
        raise ValueError("Native startup smoke currently supports macOS and Windows")
    if not 10 <= timeout <= 300 or not 1 <= observe <= 60:
        raise ValueError("Use a 10–300 second timeout and 1–60 second observation window")
    app = app.resolve()
    contents = app / "Contents" if platform.system() == "Darwin" else app
    manifest = json.loads((contents / "openpycharm-build.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "OpenPyCharm" or manifest.get("upstreamProduct") != "PC":
        raise ValueError("Only the assembled OpenPyCharm product may be smoke tested")
    executable = contents / ("MacOS/pycharm" if platform.system() == "Darwin" else "bin/pycharm64.exe")
    if not executable.is_file():
        raise ValueError("Native product launcher is missing")
    if profile is None:
        (ROOT / "build").mkdir(exist_ok=True)
        profile = Path(tempfile.mkdtemp(prefix="runtime-smoke-", dir=ROOT / "build"))
    else:
        profile = profile.resolve()
        if profile.exists() or profile.is_symlink():
            raise ValueError("Choose a new profile directory so old logs and running instances cannot be reused")
        if profile.is_relative_to(app) or app.is_relative_to(profile):
            raise ValueError("The test profile and application must be separate")
        profile.mkdir(parents=True)
    project = profile / "project" / "hello-python"
    shutil.copytree(ROOT / "fixtures/hello-python", project,
                    ignore=shutil.ignore_patterns(".idea", ".venv", "__pycache__", "*.pyc", ".pytest_cache"))
    properties = profile / "idea.properties"
    for name in ("config", "system", "plugins", "log"):
        (profile / name).mkdir()
    properties.write_text("\n".join(f"idea.{name}.path={(profile / name).as_posix()}"
                                    for name in ("config", "system", "plugins", "log")) +
                          "\nidea.initially.ask.config=never\nintellij.startup.wizard=false\n", encoding="utf-8")
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"JAVA_HOME", "JDK_HOME", "IDEA_JDK", "IDEA_PROPERTIES", "IDEA_VM_OPTIONS",
                                  "PYCHARM_PROPERTIES", "PYCHARM_VM_OPTIONS", "OPENPYCHARM_VM_OPTIONS",
                                  "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS"}}
    environment["OPENPYCHARM_PROPERTIES"] = str(properties)
    command = [str(executable), str(project)]
    windows = platform.system() == "Windows"
    job = None
    process = None
    receipt = {"schema": 1, "status": "failed", "application": str(app), "profile": str(profile),
               "target": manifest.get("target"), "version": manifest.get("version"),
               "productManifestSha256": sha256(contents / "openpycharm-build.json"),
               "command": command, "projectTrustBypassed": False,
               "limitations": ["Project trust and first-run dialogs remain normal and may await user input",
                               "Startup logs do not establish Run/Test/Debug or other native UI acceptance"]}
    started = time.monotonic()
    ready_at = None
    log_path = profile / "log/idea.log"
    try:
        job = WindowsJob() if windows else None
        with (profile / "launcher-output.log").open("wb") as output:
            options = ({"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP}
                       if windows else {"start_new_session": True})
            process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, **options)
            receipt["pid"] = process.pid
            if job is not None:
                job.assign_and_resume(process)
            while time.monotonic() - started < timeout:
                if process.poll() is not None:
                    raise ValueError(f"Owned native launcher exited before startup verification: {process.returncode}")
                text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
                observation = log_observation(text, profile, project, manifest["upstreamBuild"])
                receipt["observation"] = observation
                if observation["errorCount"]:
                    raise ValueError("Native startup log contains ERROR or SEVERE entries")
                if startup_ready(observation):
                    ready_at = ready_at or time.monotonic()
                    if time.monotonic() - ready_at >= observe:
                        receipt["status"] = "passed-startup"
                        break
                time.sleep(0.5)
            else:
                raise ValueError("Timed out waiting for native identity, plugin and isolated-path startup evidence")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        receipt["failure"] = str(error)
    finally:
        if process is not None:
            # If job assignment failed, the launcher is still suspended; kill
            # that owned process before closing the possibly empty job.
            if job is not None and process.poll() is None and "observation" not in receipt:
                process.kill()
            try:
                receipt["cleanup"] = stop_owned(process, job)
            except (OSError, subprocess.SubprocessError) as error:
                receipt["status"] = "failed"
                receipt["cleanupFailure"] = str(error)
        elif job is not None:
            job.stop()
        receipt["elapsedSeconds"] = round(time.monotonic() - started, 2)
        if log_path.is_file():
            receipt["logSha256"] = sha256(log_path)
            final_observation = log_observation(log_path.read_text(encoding="utf-8", errors="replace"),
                                                profile, project, manifest["upstreamBuild"])
            receipt["finalObservation"] = final_observation
            if final_observation["errorCount"]:
                receipt["status"] = "failed"
                receipt["failure"] = "Native log contains ERROR or SEVERE entries"
        (profile / "startup.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if receipt["status"] != "passed-startup":
        raise ValueError(f"Native startup failed; see {profile / 'startup.json'}: {receipt.get('failure', receipt.get('cleanupFailure'))}")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--observe", type=int, default=10)
    args = parser.parse_args()
    try:
        result = run_smoke(args.app, args.profile, timeout=args.timeout, observe=args.observe)
        print(json.dumps({key: result[key] for key in ("status", "application", "profile", "pid", "elapsedSeconds")}))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Runtime smoke failed: {error}\n")


if __name__ == "__main__":
    main()
