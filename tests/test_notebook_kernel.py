"""Independent bridge protocol tests; real kernels require an explicit test Python.

OPENPYCHARM_NOTEBOOK_PYTHON=/path/to/test/venv/python python3 -m unittest discover -s tests -p test_notebook_kernel.py -v
No dependency is installed by these tests and no pre-existing kernel is contacted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "plugins/notebooks/resources/kernel_bridge.py"
RUNTIME = os.environ.get("OPENPYCHARM_NOTEBOOK_PYTHON")


class BridgeSession:
    def __init__(self, cwd: Path):
        self.process = subprocess.Popen([RUNTIME, "-u", str(BRIDGE), "--cwd", str(cwd)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8")
        self.events = queue.Queue()
        self.errors = []
        self.received = []
        self.saved = []

        def read():
            for line in self.process.stdout:
                try:
                    self.events.put(json.loads(line))
                except json.JSONDecodeError:
                    self.events.put({"event": "invalid_json", "line": line})
            self.events.put({"event": "eof"})

        def read_errors():
            # Retain bounded startup diagnostics, not potentially unbounded user output.
            for line in self.process.stderr:
                if sum(map(len, self.errors)) < 32768:
                    self.errors.append(line)

        self.reader = threading.Thread(target=read, daemon=True)
        self.error_reader = threading.Thread(target=read_errors, daemon=True)
        self.reader.start()
        self.error_reader.start()
        self.ready = self.wait(lambda item: item.get("event") == "ready", timeout=40)

    def send(self, request_id, op, **fields):
        self.process.stdin.write(json.dumps({"id": request_id, "op": op, **fields}) + "\n")
        self.process.stdin.flush()

    def wait(self, predicate, timeout=20):
        for index, event in enumerate(self.saved):
            if predicate(event):
                return self.saved.pop(index)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            self.received.append(event)
            if predicate(event):
                return event
            if event.get("event") in ("eof", "invalid_json"):
                raise AssertionError(f"Bridge stopped or broke protocol: {event}; stderr={''.join(self.errors)}")
            self.saved.append(event)
        raise AssertionError(f"No expected bridge event; events={self.received[-12:]}; stderr={''.join(self.errors)}")

    def done(self, request_id, timeout=20):
        return self.wait(lambda item: item.get("id") == request_id and item.get("event") == "done", timeout)

    def execute(self, request_id, code, timeout=20):
        self.send(request_id, "execute", code=code)
        done = self.done(request_id, timeout)
        return done, [event for event in self.received if event.get("id") == request_id]

    def close(self):
        if self.process.poll() is None:
            try:
                self.send("test-shutdown", "shutdown")
                self.done("test-shutdown", timeout=15)
            except (AssertionError, BrokenPipeError):
                pass
            self.process.stdin.close()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                # Only this test's bridge is terminated; never scan/kill kernels.
                self.process.terminate()
                self.process.wait(timeout=15)
        if not self.process.stdin.closed:
            self.process.stdin.close()
        self.reader.join(timeout=3)
        self.error_reader.join(timeout=3)
        self.process.stdout.close()
        self.process.stderr.close()


def process_exists(pid):
    # psutil is a transitive runtime dependency, and its PID lookup is read-only
    # on every platform (unlike Windows os.kill(pid, 0)).
    result = subprocess.run([RUNTIME, "-c", "import psutil,sys; print(int(psutil.pid_exists(int(sys.argv[1]))))", str(pid)],
                            capture_output=True, text=True, timeout=10, check=True)
    return result.stdout.strip() == "1"


class NotebookKernelProtocolTests(unittest.TestCase):
    def test_missing_cwd_returns_structured_error_without_jupyter(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(BRIDGE), "--cwd", str(Path(directory) / "missing")],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[0]["event"], "error")
        self.assertEqual(events[0]["content"]["ename"], "InvalidWorkingDirectory")
        self.assertEqual(events[-1]["status"], "error")



    def test_missing_dependencies_returns_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            # -S deliberately hides third-party site-packages without altering
            # any interpreter or installed dependency.
            result = subprocess.run([sys.executable, "-S", str(BRIDGE), "--cwd", directory],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[0]["event"], "error")
        self.assertIn("pip install jupyter_client==8.6.3 ipykernel==6.29.5", events[0]["content"]["evalue"])
        self.assertIn("pip install", result.stderr)


@unittest.skipUnless(RUNTIME, "Set OPENPYCHARM_NOTEBOOK_PYTHON to a test-owned Python with kernel dependencies")
class NotebookKernelIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="openpycharm-kernel-test-")
        self.cwd = Path(self.directory.name)
        self.session = BridgeSession(self.cwd)

    def tearDown(self):
        self.session.close()
        self.directory.cleanup()

    def test_selected_interpreter_state_outputs_error_and_no_stdin(self):
        self.assertEqual(Path(self.session.ready["python"]), Path(RUNTIME))
        code = "import sys, os, json\nprint(json.dumps({'python':sys.executable,'cwd':os.getcwd()}))\nprint('stderr-value',file=sys.stderr)\nfrom IPython.display import display\ndisplay({'text/plain':'plain-value','text/html':'<b>raw-html-value</b>'},raw=True)\nshared_value=41\nshared_value+1"
        done, events = self.session.execute("outputs", code)
        self.assertEqual(done["status"], "ok")
        self.assertEqual(done["execution_count"], 1)
        streams = [event["content"] for event in events if event["event"] == "stream"]
        identity = json.loads(next(item["text"].splitlines()[0] for item in streams if item["name"] == "stdout"))
        self.assertEqual(identity["python"], RUNTIME)
        self.assertEqual(Path(identity["cwd"]).resolve(), self.cwd.resolve())
        self.assertTrue(any(item["name"] == "stderr" and "stderr-value" in item["text"] for item in streams))
        display = next(event["content"] for event in events if event["event"] == "display_data")
        self.assertEqual(display["data"]["text/plain"], "plain-value")
        self.assertEqual(display["data"]["text/html"], "<b>raw-html-value</b>")
        self.assertEqual(next(event["content"]["data"]["text/plain"] for event in events if event["event"] == "execute_result"), "42")
        done, events = self.session.execute("state", "shared_value + 2")
        self.assertEqual(done["status"], "ok")
        self.assertEqual(next(event["content"]["data"]["text/plain"] for event in events if event["event"] == "execute_result"), "43")
        done, events = self.session.execute("error", "raise ValueError('real-kernel-failure')")
        self.assertEqual(done["status"], "error")
        error = next(event["content"] for event in events if event["event"] == "error")
        self.assertEqual(error["ename"], "ValueError")
        self.assertEqual(error["evalue"], "real-kernel-failure")
        self.assertTrue(error["traceback"])
        done, events = self.session.execute("stdin", "input('no stdin: ')")
        self.assertEqual(done["status"], "error")
        self.assertEqual(next(event["content"]["ename"] for event in events if event["event"] == "error"), "StdinNotImplementedError")

    def test_interrupt_busy_restart_and_owned_cleanup(self):
        original_pid = self.session.ready["kernel_pid"]
        # This unrelated, test-owned Python must survive all kernel controls.
        sentinel = subprocess.Popen([RUNTIME, "-c", "import time; time.sleep(90)"])
        try:
            self.session.send("long", "execute", code="import time\nowned_state=123\nwhile True: time.sleep(0.05)")
            self.session.wait(lambda item: item.get("id") == "long" and item.get("event") == "execute_input")
            self.session.send("overlap", "execute", code="2+2")
            self.assertEqual(self.session.done("overlap")["status"], "error")
            self.session.send("ping-busy", "ping")
            pong = self.session.wait(lambda item: item.get("id") == "ping-busy" and item.get("event") == "pong", timeout=3)
            self.assertTrue(pong["busy"])
            self.session.send("interrupt", "interrupt")
            self.assertEqual(self.session.done("interrupt", timeout=3)["status"], "ok")
            self.assertEqual(self.session.done("long", timeout=10)["status"], "error")
            self.assertTrue(any(item.get("id") == "long" and item.get("event") == "error" and item["content"].get("ename") == "KeyboardInterrupt" for item in self.session.received))
            self.session.send("restart", "restart")
            restarted = self.session.done("restart", timeout=40)
            self.assertEqual(restarted["status"], "ok")
            self.assertNotEqual(restarted["kernel_pid"], original_pid)
            self.assertFalse(process_exists(original_pid))
            done, events = self.session.execute("reset", "owned_state")
            self.assertEqual(done["status"], "error")
            self.assertEqual(next(event["content"]["ename"] for event in events if event["event"] == "error"), "NameError")
            new_pid = restarted["kernel_pid"]
            self.session.close()
            self.assertEqual(self.session.process.returncode, 0)
            self.assertFalse(process_exists(new_pid))
            self.assertIsNone(sentinel.poll())
        finally:
            sentinel.terminate()
            sentinel.wait(timeout=10)

    def test_restart_while_busy_and_stdin_eof_shutdown(self):
        old_pid = self.session.ready["kernel_pid"]
        self.session.send("pending", "execute", code="import time\nwhile True: time.sleep(0.05)")
        self.session.wait(lambda item: item.get("id") == "pending" and item.get("event") == "execute_input")
        self.session.send("restart-busy", "restart")
        self.assertEqual(self.session.done("pending")["status"], "aborted")
        restarted = self.session.done("restart-busy", timeout=40)
        self.assertEqual(restarted["status"], "ok")
        self.assertFalse(process_exists(old_pid))
        done, _ = self.session.execute("after-restart", "6*7")
        self.assertEqual(done["status"], "ok")
        self.session.process.stdin.close()
        self.session.process.wait(timeout=15)
        self.assertEqual(self.session.process.returncode, 0)
        self.assertFalse(process_exists(restarted["kernel_pid"]))

    @unittest.skipIf(os.name == "nt", "Windows shutdown uses the stdin EOF path; signal delivery is platform-specific")
    def test_sigterm_during_execution_stops_owned_kernel(self):
        pid = self.session.ready["kernel_pid"]
        self.session.send("term-pending", "execute", code="import time\nwhile True: time.sleep(0.05)")
        self.session.wait(lambda item: item.get("id") == "term-pending" and item.get("event") == "execute_input")
        self.session.process.terminate()
        self.session.process.wait(timeout=15)
        self.assertEqual(self.session.process.returncode, 0)
        self.assertFalse(process_exists(pid))

    def test_closed_parent_stdout_does_not_prevent_owned_cleanup(self):
        process = subprocess.Popen([RUNTIME, "-u", str(BRIDGE), "--cwd", str(self.cwd)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8")
        ready_queue = queue.Queue()
        reader = threading.Thread(target=lambda: ready_queue.put(process.stdout.readline()), daemon=True)
        reader.start()
        pid = None
        try:
            ready = json.loads(ready_queue.get(timeout=40))
            self.assertEqual(ready["event"], "ready")
            pid = ready["kernel_pid"]
            reader.join(timeout=2)
            process.stdout.close()
            process.stdin.write(json.dumps({"id": "broken-output", "op": "ping"}) + "\n")
            process.stdin.flush()
            # Keep stdin open briefly so the ping reaches the closed output pipe.
            time.sleep(0.1)
            process.stdin.close()
            process.wait(timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr.read())
            self.assertFalse(process_exists(pid))
        finally:
            if process.poll() is None:
                if not process.stdin.closed:
                    process.stdin.close()
                process.wait(timeout=15)
            if not process.stdout.closed:
                process.stdout.close()
            process.stderr.close()

    def test_output_limit_and_invalid_input_keep_protocol_usable(self):
        self.session.process.stdin.write("{not-json}\n")
        self.session.process.stdin.flush()
        invalid = self.session.wait(lambda item: item.get("id") is None and item.get("event") == "error")
        self.assertEqual(invalid["content"]["ename"], "InvalidRequest")
        self.session.process.stdin.write(" " * (1024 * 1024 + 20) + "\n")
        self.session.process.stdin.flush()
        too_big = self.session.wait(lambda item: item.get("id") is None and item.get("event") == "error")
        self.assertIn("exceeds 1 MiB", too_big["content"]["evalue"])
        done, events = self.session.execute("large", "print('x' * (2 * 1024 * 1024))")
        self.assertEqual(done["status"], "error")
        self.assertTrue(done["output_limited"])
        self.assertTrue(any(item["event"] == "output_limit" for item in events))
        self.assertLess(sum(len(json.dumps(item)) for item in events), 1024 * 1024)
        done, _ = self.session.execute("after-limit", "2+2")
        self.assertEqual(done["status"], "ok")


if __name__ == "__main__":
    unittest.main()
