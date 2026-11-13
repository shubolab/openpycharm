#!/usr/bin/env python3
"""Exercise pinned real Node/TLS stdio against a new owned fixture, without an IDE.

This proves server protocol behavior only. It cannot prove PC module/service
loading, native editor integration, or UI parity. Tools must already be explicitly
provisioned; this script never downloads packages or executes install scripts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
import uuid

from provision_frontend_tools import DEFAULT_CACHE, OWNER, PIN, ROOT, authenticate_runtime, digest, owned
from runtime_smoke import WindowsJob, WINDOWS_CREATE_NEW_PROCESS_GROUP, WINDOWS_CREATE_SUSPENDED

FIXTURE_PARENT = ROOT / ".tools/frontend-m0-fixtures"


def position(text: str, offset: int) -> dict:
    if offset < 0 or offset > len(text):
        raise ValueError("Position outside document")
    prefix = text[:offset]; line = prefix.count("\n"); column = prefix.rsplit("\n", 1)[-1]
    return {"line": line, "character": len(column.encode("utf-16-le")) // 2}


def child_environment(state: Path, node: Path) -> dict[str, str]:
    # Language analysis does not need the IDE's Git/npm/service credentials.
    # This private child's environment never changes user-selected service auth.
    environment = {"PATH": str(node.parent), "HOME": str(state / "home"), "USERPROFILE": str(state / "home"),
                   "TMPDIR": str(state / "tmp"), "TMP": str(state / "tmp"), "TEMP": str(state / "tmp"),
                   "XDG_CACHE_HOME": str(state / "cache"), "NPM_CONFIG_CACHE": str(state / "cache/npm"),
                   "NODE_OPTIONS": "", "NODE_PATH": "", "TSS_LOG": ""}
    for key in ("SystemRoot", "WINDIR", "COMSPEC"):
        if key in os.environ:
            environment[key] = os.environ[key]
    return environment


def prepare_fixture(tools: dict) -> tuple[Path, str]:
    parent = owned(FIXTURE_PARENT); parent.mkdir(parents=True, exist_ok=True)
    nonce = uuid.uuid4().hex; root = parent / ("fixture-" + nonce); root.mkdir()
    state = root / ".m0-runtime"
    for directory in ("home", "tmp", "cache/npm", "log"):
        (state / directory).mkdir(parents=True, exist_ok=True)
    files = {
        "package.json": json.dumps({"name": "openpycharm-frontend-m0-fixture", "private": True, "type": "module"}) + "\n",
        "tsconfig.json": json.dumps({"compilerOptions": {"target": "ES2022", "module": "NodeNext", "moduleResolution": "NodeNext",
                                                         "strict": True, "noEmit": True, "allowJs": True, "checkJs": True, "types": []},
                                    "include": ["*.ts", "*.js"]}) + "\n",
        "quote.ts": "export interface Quote { total: number; }\nexport function makeQuote(total: number): Quote { return { total }; }\n",
        "receipt.js": "/** @returns {{id: number, note: string}} */\nexport function makeReceipt() { return { id: 9, note: 'ok' }; }\n",
        "main.ts": "export const diskOnly = 1;\n",
        "main.js": "export const diskOnlyJs = 2;\n",
    }
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    marker = {"schema": 1, "owner": OWNER, "nonce": nonce, "fixtureRoot": root.as_posix(),
              "toolsReceipt": tools["receipt"], "toolsReceiptSha256": tools["receiptSha256"], "lockSha256": tools["lockSha256"]}
    (root / ".openpycharm-frontend-m0.json").write_text(json.dumps(marker, indent=2) + "\n")
    return root, nonce


class Client:
    def __init__(self, tools: dict, root: Path):
        self.root = root; self.events = []; self.responses = {}; self.counter = 0
        self.messages = queue.Queue(); self.read_error = None; self.closed = False
        runtime = Path(tools["runtimeRoot"]); entries = tools["entries"]
        self.node = runtime / entries["node"]
        self.command = [str(self.node), str(runtime / entries["typescriptLanguageServer"]), "--stdio", "--log-level", "2"]
        self.stderr = (root / ".m0-runtime/log/tls-stderr.log").open("wb")
        self.job = WindowsJob() if os.name == "nt" else None
        options = {"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP} if self.job else {"start_new_session": True}
        self.process = subprocess.Popen(self.command, cwd=root, env=child_environment(root / ".m0-runtime", self.node),
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, **options)
        if self.job:
            try:
                self.job.assign_and_resume(self.process)
            except BaseException:
                self.process.kill(); self.process.wait(timeout=5); self.job.stop(); self.stderr.close(); raise
        self.reader = threading.Thread(target=self._read, name="frontend-m0-stdio", daemon=True); self.reader.start()

    def _read(self):
        try:
            while True:
                headers = {}
                while True:
                    line = self.process.stdout.readline(4097)
                    if not line:
                        self.messages.put(None); return
                    if len(line) > 4096:
                        raise ValueError("Oversized LSP header")
                    if line in (b"\r\n", b"\n"):
                        break
                    key, value = line.decode("ascii").strip().split(":", 1)
                    if key.lower() in headers:
                        raise ValueError("Duplicate LSP framing header")
                    headers[key.lower()] = value.strip()
                length = int(headers["content-length"])
                if not 0 < length <= 8_000_000:
                    raise ValueError("LSP payload exceeds bound")
                body = self.process.stdout.read(length)
                if len(body) != length:
                    raise ValueError("Truncated LSP payload")
                self.messages.put(json.loads(body))
        except BaseException as error:
            self.read_error = error; self.messages.put(None)

    def send(self, message: dict):
        data = json.dumps({"jsonrpc": "2.0", **message}, ensure_ascii=False).encode("utf-8")
        self.process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data); self.process.stdin.flush()

    def notify(self, method: str, params=None):
        self.send({"method": method, **({"params": params} if params is not None else {})})

    def _receive(self, deadline: float):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Real LSP response deadline exceeded")
        message = self.messages.get(timeout=remaining)
        if message is None:
            raise RuntimeError("Real LSP stream closed: " + str(self.read_error))
        if "method" in message:
            method = message["method"]
            if "id" in message:
                if method == "workspace/configuration":
                    value = [{"tabSize": 2, "insertSpaces": True} if item.get("section") == "formattingOptions" else {}
                             for item in message.get("params", {}).get("items", [])]
                elif method == "workspace/workspaceFolders":
                    value = [{"uri": self.root.as_uri(), "name": self.root.name}]
                elif method == "workspace/applyEdit":
                    value = {"applied": False, "failureReason": "Read-only protocol control never applies workspace edits"}
                else:
                    value = None
                self.send({"id": message["id"], "result": value})
            self.events.append(message)
        elif "id" in message:
            self.responses[message["id"]] = message

    def call(self, method: str, params=None, timeout: float = 25):
        self.counter += 1; identity = self.counter
        self.send({"id": identity, "method": method, **({"params": params} if params is not None else {})})
        deadline = time.monotonic() + timeout
        while identity not in self.responses:
            self._receive(deadline)
        response = self.responses.pop(identity)
        if "error" in response:
            raise ValueError("Real server request failed: " + method + ": " + str(response["error"]))
        return response.get("result")

    def diagnostics(self, uri: str, *, contains: int | None = None, excludes: set[int] | None = None, since: int = 0):
        deadline = time.monotonic() + 30
        while True:
            for event in self.events[since:]:
                if event.get("method") == "textDocument/publishDiagnostics" and event.get("params", {}).get("uri") == uri:
                    codes = {entry.get("code") for entry in event["params"]["diagnostics"]}
                    if (contains is None or contains in codes) and not codes.intersection(excludes or set()):
                        return event["params"]
            self._receive(deadline)

    def group_members(self) -> list[int]:
        if os.name == "nt":
            return []
        output = subprocess.run(["/bin/ps", "-axo", "pid=,pgid=,state="], capture_output=True, text=True, timeout=5).stdout
        return [int(parts[0]) for line in output.splitlines() if len(parts := line.split()) == 3
                and int(parts[1]) == self.process.pid and not parts[2].startswith("Z")]

    def close(self) -> dict:
        if self.closed:
            return {"alreadyClosed": True}
        self.closed = True; observed = self.group_members(); graceful = False; signals = []
        try:
            if self.process.poll() is None:
                try:
                    self.call("shutdown", timeout=10); self.notify("exit"); self.process.wait(timeout=10); graceful = self.process.returncode == 0
                except (Exception, BrokenPipeError):
                    pass
            if self.job:
                self.job.stop()
            else:
                grace_deadline = time.monotonic() + 2
                while self.group_members() and time.monotonic() < grace_deadline:
                    time.sleep(0.05)
                if self.group_members():
                    try:
                        os.killpg(self.process.pid, signal.SIGTERM)
                        signals.append("SIGTERM")
                    except ProcessLookupError:
                        pass  # An owned process may exit between ps and killpg.
                deadline = time.monotonic() + 5
                while self.group_members() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if self.group_members():
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                        signals.append("SIGKILL")
                    except ProcessLookupError:
                        pass
            self.process.wait(timeout=5)
        finally:
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.stdout:
                self.process.stdout.close()
            self.stderr.close(); self.reader.join(timeout=2)
        remaining = self.group_members()
        if remaining:
            raise ValueError("Owned real server process group did not terminate")
        return {"ownedPid": self.process.pid, "observedOwnedGroupPids": observed, "remainingOwnedGroupPids": remaining,
                "groupObservationScope": "Windows assigned Job closure; group census unavailable" if self.job else "Live owned POSIX process-group members; transient zombies are not running processes",
                "forcedOwnedSignals": signals, "windowsJobAssigned": self.job is not None,
                "gracefulProtocolExit": graceful, "processReturnCode": self.process.returncode}


def locations(value):
    if isinstance(value, dict):
        value = [value]
    return value or []


def run(receipt: Path) -> dict:
    tools = authenticate_runtime(receipt)
    expected_target = "windows-x64" if os.name == "nt" else "macos-arm64"
    if tools["target"] != expected_target:
        raise ValueError("Real protocol control needs a native target Node executable")
    root, nonce = prepare_fixture(tools); client = None
    report = {"schema": 1, "owner": OWNER, "fixtureRoot": str(root), "nonce": nonce,
              "scope": "Real Node/TypeScript Language Server protocol, no IDE/native editor/UI acceptance",
              "nativeIdeStarted": False, "toolsReceiptSha256": tools["receiptSha256"], "lockSha256": tools["lockSha256"],
              "target": tools["target"], "checks": {}}
    disk_hashes = {name: digest((root / name).read_bytes()) for name in ("main.ts", "main.js", "quote.ts", "receipt.js")}
    try:
        client = Client(tools, root); report["ownedPid"] = client.process.pid
        node_version = subprocess.run([str(client.node), "--version"], env=child_environment(root / ".m0-runtime", client.node),
                                      capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        if node_version != "v24.22.3":
            raise ValueError("Pinned Node version mismatch")
        report["nodeVersion"] = node_version
        tls_version = subprocess.run([str(client.node), client.command[1], "--version"], env=child_environment(root / ".m0-runtime", client.node),
                                     capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        if tls_version != "6.1.0":
            raise ValueError("Pinned TypeScript Language Server version mismatch")
        report["typescriptLanguageServerVersion"] = tls_version
        init = client.call("initialize", {"processId": os.getpid(), "rootUri": root.as_uri(),
            "workspaceFolders": [{"uri": root.as_uri(), "name": root.name}],
            "capabilities": {"general": {"positionEncodings": ["utf-16"]}, "workspace": {"configuration": True, "workspaceFolders": True},
                             "textDocument": {"publishDiagnostics": {"versionSupport": True}, "completion": {"completionItem": {"snippetSupport": False}}}},
            "initializationOptions": {"hostInfo": "OpenPyCharm frontend M0 protocol control", "disableAutomaticTypingAcquisition": True,
                                      "tsserver": {"path": str(Path(tools["runtimeRoot"]) / tools["entries"]["typescriptServer"]),
                                                   "logDirectory": str(root / ".m0-runtime/log")}}})
        capabilities = init["capabilities"]
        report["initializeServerInfo"] = init.get("serverInfo")
        if not capabilities.get("completionProvider") or not capabilities.get("definitionProvider"):
            raise ValueError("Real server did not advertise required capabilities")
        sync = capabilities.get("textDocumentSync")
        if (sync.get("change") if isinstance(sync, dict) else sync) != 2:
            raise ValueError("Real server did not negotiate incremental text synchronization")
        if capabilities.get("positionEncoding", "utf-16") != "utf-16":
            raise ValueError("Real server selected a non-UTF-16 position encoding")
        client.notify("initialized", {}); report["checks"]["realInitializeIncrementalUtf16"] = True
        ts = 'import { makeQuote } from "./quote.js";\nconst label = "😀 中文"; const quote = makeQuote(7);\nquote.total;\nconst broken: number = "wrong";\n'
        uri = (root / "main.ts").as_uri()
        client.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "typescript", "version": 1, "text": ts}})
        initial = client.diagnostics(uri, contains=2322); report["checks"]["unsavedTypeScriptDiagnostics"] = True
        offset = ts.index("quote.total") + len("quote.")
        completed = client.call("textDocument/completion", {"textDocument": {"uri": uri}, "position": position(ts, offset)})
        items = completed.get("items", []) if isinstance(completed, dict) else completed
        if "total" not in {item["label"] for item in items or []}:
            raise ValueError("Real TypeScript completion did not contain the interface property")
        report["checks"]["unsavedTypeScriptCompletion"] = True
        definition_offset = ts.rindex("makeQuote") + 2
        utf16_position = position(ts, definition_offset)
        codepoint_column = definition_offset - ts.rfind("\n", 0, definition_offset) - 1
        if utf16_position["character"] != codepoint_column + 1:
            raise ValueError("Fixture did not exercise a surrogate pair before definition position")
        definitions = client.call("textDocument/definition", {"textDocument": {"uri": uri}, "position": utf16_position})
        if not any(location.get("uri", location.get("targetUri")) == (root / "quote.ts").as_uri() for location in locations(definitions)):
            raise ValueError("Real UTF-16 definition did not resolve the cross-file export")
        report["checks"]["utf16CrossFileDefinition"] = True; report["definitionPosition"] = utf16_position
        bad = ts.index("makeQuote(7)") + len("makeQuote("); anchor = len(client.events)
        client.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2},
                      "contentChanges": [{"range": {"start": position(ts, bad), "end": position(ts, bad + 1)}, "text": '"bad"'}]})
        ts = ts[:bad] + '"bad"' + ts[bad + 1:]
        changed = client.diagnostics(uri, contains=2345, since=anchor)
        report["checks"]["utf16IncrementalUnsavedChange"] = True
        anchor = len(client.events); repaired = ts.replace('"bad"', "11").replace('const broken: number = "wrong";', "const broken: number = 42;")
        client.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 3}, "contentChanges": [{"text": repaired}]})
        fixed = client.diagnostics(uri, excludes={2322, 2345}, since=anchor)
        report["checks"]["unsavedDiagnosticRecovery"] = True
        js = 'import { makeReceipt } from "./receipt.js";\nconst label = "😀"; const receipt = makeReceipt();\nreceipt.id;\n'
        js_uri = (root / "main.js").as_uri()
        client.notify("textDocument/didOpen", {"textDocument": {"uri": js_uri, "languageId": "javascript", "version": 1, "text": js}})
        js_completion = client.call("textDocument/completion", {"textDocument": {"uri": js_uri}, "position": position(js, js.index("receipt.id") + len("receipt."))})
        js_items = js_completion.get("items", []) if isinstance(js_completion, dict) else js_completion
        if not {"id", "note"}.issubset({item["label"] for item in js_items or []}):
            raise ValueError("Real JavaScript completion did not resolve the JSDoc export")
        js_definition = client.call("textDocument/definition", {"textDocument": {"uri": js_uri}, "position": position(js, js.rindex("makeReceipt") + 2)})
        if not any(location.get("uri", location.get("targetUri")) == (root / "receipt.js").as_uri() for location in locations(js_definition)):
            raise ValueError("Real JavaScript definition did not resolve its source")
        report["checks"]["unsavedJavaScriptCompletionDefinition"] = True
        versions = [event["params"] for event in client.events if event.get("method") == "$/typescriptVersion"]
        if not any(event.get("version") == "6.0.3" and event.get("source") == "user-setting" for event in versions):
            raise ValueError("Real server did not confirm the explicitly pinned TypeScript SDK")
        report["typescriptVersionNotifications"] = versions
        if any(digest((root / name).read_bytes()) != value for name, value in disk_hashes.items()):
            raise ValueError("Protocol control modified on-disk source while claiming unsaved edits")
        report["checks"]["fixtureSourceFilesUnchanged"] = True
        report["diagnosticCodes"] = {"initial": [d.get("code") for d in initial["diagnostics"]],
                                     "utf16Change": [d.get("code") for d in changed["diagnostics"]],
                                     "repaired": [d.get("code") for d in fixed["diagnostics"]]}
        client.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        client.notify("textDocument/didClose", {"textDocument": {"uri": js_uri}})
        report["status"] = "pass"
    except BaseException as error:
        report["status"] = "fail"; report["failure"] = type(error).__name__ + ": " + str(error)
    finally:
        if client:
            try:
                report["cleanup"] = client.close()
                if not report["cleanup"].get("gracefulProtocolExit"):
                    report["status"] = "fail"; report["cleanupFailure"] = "Server needed forced cleanup instead of normal shutdown/exit"
                if report["cleanup"].get("forcedOwnedSignals"):
                    report["status"] = "fail"; report["cleanupFailure"] = "An owned child required forced termination after protocol exit"
            except BaseException as error:
                report["status"] = "fail"; report["cleanupFailure"] = str(error)
        try:
            after = authenticate_runtime(receipt)
            if after["receiptSha256"] != tools["receiptSha256"]:
                raise ValueError("Pinned frontend tool receipt changed during the real protocol control")
            if any(digest((root / name).read_bytes()) != value for name, value in disk_hashes.items()):
                raise ValueError("Owned fixture source changed during server cleanup")
            report["checks"]["pinnedToolsAndSourcesUnchangedAfterExit"] = True
        except BaseException as error:
            report["status"] = "fail"; report["postExitAuthenticationFailure"] = str(error)
        (root / ".m0-runtime/protocol-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(); report = run(args.receipt)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
