#!/usr/bin/env python3
"""Owned subprocess tests. No IDE, Node, shell, or non-loopback connection."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest


GUARDIAN = Path(os.environ["OPC_GUARDIAN_BINARY"]).resolve(strict=True)
CHILD = Path(os.environ["OPC_GUARDIAN_CHILD"]).resolve(strict=True)


def wait_json(path: Path, timeout: float = 5) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            time.sleep(.005)
        except PermissionError:
            if sys.platform != "win32":
                raise
            time.sleep(.005)  # own atomic publisher may briefly hold sharing lock
    raise AssertionError(f"owned fixture did not publish {path.name}")


def alive(identity: dict) -> bool:
    pid = identity["pid"]
    assert isinstance(pid, int) and pid > 1
    if sys.platform == "win32":
        # Retained creation identity, never process names or broad PID scans.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.c_void_p] * 4
        handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return False
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            values = [ctypes.c_ulonglong() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
                raise ctypes.WinError(ctypes.get_last_error())
            if "created" in identity and values[0].value != identity["created"]:
                return False
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A killed orphan may briefly be a zombie awaiting the OS reaper. It cannot
    # execute or retain a pipe. This observes only fixture-recorded PIDs; it
    # never selects a process to terminate. A recycled PID can only fail a test.
    state = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="],
                           check=False, capture_output=True, text=True,
                           encoding="utf-8", timeout=2).stdout.strip()
    return bool(state) and not state.startswith("Z")


def assert_gone(test: unittest.TestCase, identities: list[dict]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not any(alive(value) for value in identities):
            return
        time.sleep(.01)
    test.fail(f"owned processes still executing: {[v for v in identities if alive(v)]}")


class Lease:
    def __init__(self) -> None:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(5)
        self.nonce = secrets.token_hex(32)
        self.connection: socket.socket | None = None

    def argv(self, directory: Path, mode: str, *args: str) -> list[str]:
        return [str(GUARDIAN), "--lease", f"127.0.0.1:{self.listener.getsockname()[1]}",
                "--nonce", self.nonce, "--", str(CHILD), str(directory), mode, *args]

    def accept(self, ack: bytes = b"OK\n") -> None:
        self.connection, address = self.listener.accept()
        assert address[0] == "127.0.0.1"
        self.connection.settimeout(5)
        expected = f"OPC-LSP-LEASE/1 {self.nonce}\n".encode("ascii")
        received = b""
        while len(received) < len(expected):
            part = self.connection.recv(len(expected)-len(received))
            if not part:
                raise AssertionError("lease greeting EOF")
            received += part
        assert received == expected
        self.listener.close()  # exactly one owned guardian, no replacement peer
        if ack:
            self.connection.sendall(ack)

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None
        self.listener.close()


class GuardianIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="opc-guardian-")
        self.directory = Path(self.temp.name).resolve()
        self.lease = Lease()
        self.processes: list[subprocess.Popen] = []
        self.sentinel = subprocess.Popen([str(CHILD), str(self.directory), "sentinel"],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, close_fds=True)
        self.processes.append(self.sentinel)
        self.sentinel_identity = wait_json(self.directory/"sentinel.json")

    def tearDown(self) -> None:
        self.lease.close()
        for p in reversed(self.processes):
            if p.poll() is None:
                p.kill()  # only an exact Popen we created, never fixture PID scanning
            try:
                p.communicate(timeout=6)
            except subprocess.TimeoutExpired:
                # Descendants have an independent 45s fixture lifetime. Report
                # a failure rather than signal a potentially recycled group.
                self.fail("owned fixture streams remained open after cleanup")
            for stream in (p.stdin, p.stdout, p.stderr):
                if stream and not stream.closed:
                    stream.close()
        self.temp.cleanup()

    def start(self, mode: str, *args: str, acknowledge: bool = True) -> subprocess.Popen:
        env = dict(os.environ, OPC_GUARDIAN_TEST="环境中文😀")
        p = subprocess.Popen(self.lease.argv(self.directory, mode, *args),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=self.directory, env=env, close_fds=True)
        self.processes.append(p)
        if acknowledge:
            self.lease.accept()
        return p

    def tree_identities(self) -> list[dict]:
        wait_json(self.directory/"ready.json")
        values = [wait_json(self.directory/f"{name}.json") for name in ("root", "child", "grandchild")]
        if sys.platform != "win32":
            anchor = values[0]["ppid"]
            self.assertGreater(anchor, 1)
            self.assertTrue(all(v["pgid"] == anchor for v in values))
            self.assertNotEqual(self.sentinel_identity["pgid"], anchor)
            values.append({"pid": anchor})
        return values

    def sentinel_survived(self) -> None:
        self.assertIsNone(self.sentinel.poll(), "unrelated owned sentinel was terminated")
        self.assertTrue(alive(self.sentinel_identity))

    def test_bytes_arguments_environment_directory_status(self) -> None:
        args = ("", "中文😀", 'quoted"argument', "tail\\", "with space", "line\nline")
        p = self.start("echo", *args)
        payload = bytes(range(256))*128 + 'Content-Length: 22\r\n\r\n{"text":"中文😀"}\r\n'.encode()
        stdout, stderr = p.communicate(payload, timeout=6)
        self.assertEqual(p.returncode, 7)
        self.assertEqual(stdout, payload)
        self.assertEqual(stderr, "separate stderr 中文😀\r\n".encode())
        record = wait_json(self.directory/"args.json")
        self.assertEqual(record, {"args": list(args), "cwd": str(self.directory), "env": "环境中文😀"})
        self.sentinel_survived()

    def test_normal_lease_close_cleans_root_child_grandchild(self) -> None:
        p = self.start("tree")
        identities = self.tree_identities()
        self.lease.close()
        p.communicate(timeout=6)
        assert_gone(self, identities)
        self.sentinel_survived()

    def test_natural_launcher_exit_cannot_leave_children_or_pipes(self) -> None:
        p = self.start("orphan")
        identities = self.tree_identities()
        stdout, stderr = p.communicate(timeout=6)
        self.assertEqual((p.returncode, stdout, stderr), (0, b"", b""))
        assert_gone(self, identities)
        self.sentinel_survived()

    def test_abrupt_guardian_death_cleans_private_group(self) -> None:
        p = self.start("tree")
        identities = self.tree_identities()
        p.kill()
        p.communicate(timeout=6)
        assert_gone(self, identities)
        self.sentinel_survived()

    def test_stdin_backpressure_does_not_block_lease_death(self) -> None:
        p = self.start("blocked")
        root = wait_json(self.directory/"root.json")
        finished = threading.Event()
        def write_blocked() -> None:
            try:
                p.stdin.write(b"x"*(4*1024*1024))
                p.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            finally:
                finished.set()
        writer = threading.Thread(target=write_blocked, daemon=True)
        writer.start()
        self.assertFalse(finished.wait(.15), "fixture did not create real stdin backpressure")
        self.lease.close()
        p.wait(timeout=6)
        self.assertTrue(finished.wait(2))
        writer.join(2)
        p.stdin.close(); p.stdin = None
        p.communicate(timeout=2)
        assert_gone(self, [root])
        self.sentinel_survived()

    def test_stdout_backpressure_does_not_block_lease_death(self) -> None:
        p = self.start("blocked-output")
        root = wait_json(self.directory/"root.json")
        # stdout is deliberately undrained until after the lease cleanup wait.
        time.sleep(.15)
        self.lease.close()
        p.wait(timeout=6)
        p.communicate(timeout=2)
        assert_gone(self, [root])
        self.sentinel_survived()

    def test_rejected_acknowledgement_never_starts_target(self) -> None:
        p = self.start("blocked", acknowledge=False)
        self.lease.accept(b"NO\n")
        stdout, stderr = p.communicate(timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(stdout, b"")
        self.assertIn(b"acknowledgement rejected", stderr)
        self.assertFalse((self.directory/"root.json").exists())
        self.sentinel_survived()

    def test_closed_lease_before_acknowledgement_never_starts_target(self) -> None:
        p = self.start("blocked", acknowledge=False)
        self.lease.accept(b"")
        self.lease.close()
        p.communicate(timeout=5)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.directory/"root.json").exists())
        self.sentinel_survived()

    def test_unexpected_lease_byte_cancels(self) -> None:
        p = self.start("tree")
        identities = self.tree_identities()
        self.lease.connection.sendall(b"unexpected")
        p.communicate(timeout=6)
        assert_gone(self, identities)
        self.sentinel_survived()

    def test_ide_proxy_kernel_death_closes_lease(self) -> None:
        self.lease.close()
        proxy = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--ide-proxy", str(self.directory)],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 close_fds=True, env=os.environ.copy())
        self.processes.append(proxy)
        guardian = wait_json(self.directory/"guardian.json")
        identities = self.tree_identities()
        proxy.kill()  # no finally/atexit/shutdown-hook execution
        proxy.communicate(timeout=5)
        assert_gone(self, identities + [guardian])
        self.sentinel_survived()


def ide_proxy(directory: Path) -> None:
    lease = Lease()
    with (directory/"proxy.stdout").open("wb") as stdout, (directory/"proxy.stderr").open("wb") as stderr:
        p = subprocess.Popen(lease.argv(directory, "tree"), stdin=subprocess.PIPE,
                             stdout=stdout, stderr=stderr, close_fds=True)
        lease.accept()
        (directory/"guardian.json").write_text(json.dumps({"pid": p.pid}), encoding="utf-8")
        time.sleep(45)  # parent deliberately kills this process, without hooks


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--ide-proxy":
        ide_proxy(Path(sys.argv[2]))
    else:
        unittest.main(verbosity=2)
