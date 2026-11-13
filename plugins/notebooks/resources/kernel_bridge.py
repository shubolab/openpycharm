#!/usr/bin/env python3
"""OpenPyCharm's independent local Jupyter kernel bridge (JSON lines, protocol 1).

Run with the project's selected interpreter: python -u kernel_bridge.py --cwd DIR.
This file contains no Jupyter implementation code; it uses its public client API.
Only the kernel created by this process can be interrupted, restarted or stopped.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
from queue import Empty
import signal
import subprocess
import sys
import tempfile
import threading
from typing import Any

PROTOCOL = 1
MAX_REQUEST_BYTES = 1024 * 1024
MAX_EVENT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_protocol_open = True
EVENT_TYPES = {"status", "execute_input", "stream", "display_data", "execute_result", "error", "clear_output", "update_display_data"}


def emit(request_id: str | None, event: str, **fields: Any) -> None:
    """The asyncio thread is the sole writer; a closed parent pipe is harmless."""
    global _protocol_open
    if not _protocol_open:
        return
    data = memoryview((json.dumps({"id": request_id, "event": event, **fields}, ensure_ascii=False) + "\n").encode("utf-8"))
    try:
        while data:
            written = os.write(sys.stdout.fileno(), data)
            data = data[written:]
    except (BrokenPipeError, OSError):
        # Closing the editor may close stdout before stdin. Cleanup must still
        # reach this bridge's owned kernel even when no reply can be delivered.
        _protocol_open = False


def failure(request_id: str | None, message: str, name: str = "BridgeError") -> None:
    emit(request_id, "error", content={"ename": name, "evalue": message, "traceback": []})
    emit(request_id, "done", status="error", message=message)


class Bridge:
    def __init__(self, cwd: Path, runtime: Path):
        if importlib.util.find_spec("ipykernel") is None:
            raise ModuleNotFoundError("No module named ipykernel")
        from jupyter_client import AsyncKernelManager
        from jupyter_client.kernelspec import KernelSpec, KernelSpecManager

        class SelectedInterpreterSpec(KernelSpecManager):
            # Avoid the user's registered kernels, config and remote provisioners.
            def get_kernel_spec(self, kernel_name: str) -> KernelSpec:
                return KernelSpec(argv=[sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                                  display_name="OpenPyCharm selected Python", language="python",
                                  metadata={"kernel_provisioner": {"provisioner_name": "local-provisioner"}})

        self.cwd = cwd
        self.runtime = runtime
        self.manager = AsyncKernelManager(kernel_name="openpycharm-selected-python",
                                         kernel_spec_manager=SelectedInterpreterSpec(),
                                         connection_file=str(runtime / "connection.json"),
                                         ip="127.0.0.1", autorestart=False)
        self.client: Any = None
        self.active: asyncio.Task | None = None
        self.active_id: str | None = None
        self.stopping = False

    async def start(self) -> None:
        # Kernel bootstrap diagnostics never share the JSON stdout stream.
        await self.manager.start_kernel(cwd=str(self.cwd), stdin=subprocess.DEVNULL,
                                        stdout=sys.stderr, stderr=sys.stderr)
        self.client = self.manager.client()
        self.client.start_channels()
        await self.client.wait_for_ready(timeout=30)

    def pid(self) -> int | None:
        provisioner = self.manager.provisioner
        return getattr(provisioner, "pid", None)

    def info(self) -> dict[str, Any]:
        return {"protocol": PROTOCOL, "python": sys.executable, "kernel_pid": self.pid(),
                "cwd": str(self.cwd), "jupyter_client": importlib.metadata.version("jupyter_client"),
                "ipykernel": importlib.metadata.version("ipykernel")}

    async def cancel_active(self, reason: str) -> None:
        task = self.active
        if task is not None and not task.done():
            request_id = self.active_id
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            emit(request_id, "done", status="aborted", message=reason)
        self.active = None
        self.active_id = None

    async def close(self) -> None:
        if self.stopping:
            return
        self.stopping = True
        await self.cancel_active("Kernel session closed")
        if self.client is not None:
            self.client.stop_channels()
        # This manager owns exactly one local provisioner/kernel. No name scans,
        # external server shutdown, taskkill, pkill or unrelated PIDs are used.
        with suppress(Exception):
            if await self.manager.is_alive():
                await asyncio.wait_for(self.manager.shutdown_kernel(now=True), timeout=10)
        with suppress(Exception):
            await self.manager.cleanup_resources()

    async def execute(self, request_id: str, code: str) -> None:
        output_bytes = 0
        limited = False
        reply: dict[str, Any] | None = None
        idle = False
        try:
            msg_id = self.client.execute(code, store_history=True, allow_stdin=False, stop_on_error=True)
            while not idle:
                try:
                    message = await self.client.get_iopub_msg(timeout=0.25)
                except Empty:
                    if not await self.manager.is_alive():
                        failure(request_id, "The owned Python kernel exited", "KernelExited")
                        return
                    continue
                if message.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                event = message.get("msg_type", message.get("header", {}).get("msg_type"))
                content = message.get("content", {})
                if event == "status" and content.get("execution_state") == "idle":
                    idle = True
                if event in EVENT_TYPES:
                    size = len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
                    if size > MAX_EVENT_BYTES or output_bytes + size > MAX_OUTPUT_BYTES:
                        if not limited:
                            limited = True
                            emit(request_id, "output_limit", content={"text": "Output limit reached; kernel interrupted", "bytes": MAX_OUTPUT_BYTES})
                            await self.manager.interrupt_kernel()
                    elif not limited or event == "status":
                        output_bytes += size
                        emit(request_id, event, content=content)
            # Jupyter shell replies and idle arrive on separate sockets. Require
            # both before reporting completion, filtering stale request replies.
            deadline = asyncio.get_running_loop().time() + 10
            while reply is None and asyncio.get_running_loop().time() < deadline:
                try:
                    message = await self.client.get_shell_msg(timeout=0.25)
                except Empty:
                    continue
                if message.get("parent_header", {}).get("msg_id") == msg_id:
                    reply = message.get("content", {})
            if reply is None:
                failure(request_id, "Kernel became idle without an execute reply", "KernelProtocolError")
                return
            emit(request_id, "done", status="error" if limited else reply.get("status", "error"),
                 execution_count=reply.get("execution_count"), output_limited=limited)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failure(request_id, str(exc), type(exc).__name__)
        finally:
            if self.active is asyncio.current_task():
                self.active = None
                self.active_id = None

    async def request(self, value: Any) -> bool:
        request_id = value.get("id") if isinstance(value, dict) else None
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            failure(None, "Request id must be a non-empty string of at most 128 characters", "InvalidRequest")
            return True
        op = value.get("op")
        try:
            if op == "execute":
                code = value.get("code")
                if not isinstance(code, str) or len(code.encode("utf-8")) > MAX_REQUEST_BYTES // 2:
                    failure(request_id, "Code must be a string of at most 512 KiB", "InvalidRequest")
                elif self.active is not None and not self.active.done():
                    failure(request_id, "A cell is already executing", "KernelBusy")
                elif not await self.manager.is_alive():
                    failure(request_id, "Kernel has exited; restart it before executing", "KernelExited")
                else:
                    self.active_id = request_id
                    self.active = asyncio.create_task(self.execute(request_id, code))
            elif op == "interrupt":
                await self.manager.interrupt_kernel()
                emit(request_id, "done", status="ok")
            elif op == "restart":
                await self.cancel_active("Kernel restarted")
                self.client.stop_channels()
                await self.manager.restart_kernel(now=True)
                self.client = self.manager.client()
                self.client.start_channels()
                await self.client.wait_for_ready(timeout=30)
                emit(request_id, "done", status="ok", **self.info())
            elif op == "ping":
                emit(request_id, "pong", alive=await self.manager.is_alive(), busy=self.active is not None, **self.info())
            elif op == "shutdown":
                await self.close()
                emit(request_id, "done", status="ok")
                return False
            else:
                failure(request_id, "Unknown operation", "InvalidRequest")
        except Exception as exc:
            failure(request_id, str(exc), type(exc).__name__)
        return True


async def run(cwd: Path, runtime: Path) -> int:
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()

    def enqueue(value: Any) -> None:
        if queue.full():
            failure(None, "Too many pending requests", "InvalidRequest")
        else:
            queue.put_nowait(value)

    def read_stdin() -> None:
        # Raw os.read avoids a blocked daemon owning BufferedReader's lock at
        # interpreter exit when SIGTERM arrives with the stdin pipe still open.
        buffer = bytearray()
        oversized = False

        def dispatch() -> None:
            if oversized:
                value: Any = {"_invalid": "Request exceeds 1 MiB"}
            else:
                try:
                    value = json.loads(buffer)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    value = {"_invalid": "Request must be UTF-8 JSON"}
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(enqueue, value)

        while True:
            try:
                chunk = os.read(sys.stdin.fileno(), 65536)
            except OSError:
                chunk = b""
            if not chunk:
                if buffer or oversized:
                    dispatch()
                with suppress(RuntimeError):
                    loop.call_soon_threadsafe(stopping.set)
                return
            for part in chunk.splitlines(keepends=True):
                if not oversized:
                    if len(buffer) + len(part) > MAX_REQUEST_BYTES:
                        buffer.clear()
                        oversized = True
                    else:
                        buffer.extend(part)
                if part.endswith(b"\n"):
                    dispatch()
                    buffer.clear()
                    oversized = False

    bridge: Bridge | None = None
    try:
        bridge = Bridge(cwd, runtime)
        await bridge.start()
        emit(None, "ready", **bridge.info())
        threading.Thread(target=read_stdin, name="openpycharm-notebook-input", daemon=True).start()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, stopping.set)
        while not stopping.is_set():
            request_task = asyncio.create_task(queue.get())
            stop_task = asyncio.create_task(stopping.wait())
            done, pending = await asyncio.wait((request_task, stop_task), return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if stop_task in done:
                break
            value = request_task.result()
            if isinstance(value, dict) and "_invalid" in value:
                failure(None, value["_invalid"], "InvalidRequest")
            elif not await bridge.request(value):
                return 0
        return 0
    except Exception as exc:
        message = str(exc)
        if isinstance(exc, (ImportError, ModuleNotFoundError)):
            message += (". Install notebook dependencies into the selected Python: "
                        "python -m pip install jupyter_client==8.6.3 ipykernel==6.29.5")
        print(message, file=sys.stderr, flush=True)
        failure(None, message, type(exc).__name__)
        return 1
    finally:
        if bridge is not None:
            await bridge.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True, type=Path)
    args = parser.parse_args()
    cwd = args.cwd.expanduser().absolute()
    if not cwd.is_dir():
        failure(None, "Notebook working directory does not exist", "InvalidWorkingDirectory")
        return 2
    # Connection keys and all ephemeral bridge state live in an owned directory,
    # never in ~/.jupyter or a reference IDE installation.
    with tempfile.TemporaryDirectory(prefix="openpycharm-notebook-") as directory:
        runtime = Path(directory)
        os.chmod(runtime, 0o700)
        os.environ["IPYTHONDIR"] = str(runtime / "ipython")
        os.environ["JUPYTER_RUNTIME_DIR"] = str(runtime)
        os.environ["JUPYTER_CONFIG_DIR"] = str(runtime / "config")
        return asyncio.run(run(cwd, runtime))


if __name__ == "__main__":
    raise SystemExit(main())
