#!/usr/bin/env python3
"""Compile/prepare an actual-platform SQL completion probe; only --run starts an IDE."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import uuid
import zipfile

from bootstrap import check_space, sha256
from build_framework_plugin import sdk_layout, execution_layout, compile_java, run_java, classpath
from native_probe import app_layout, prepare_profile
from platform_layout import cache_lock
from provenance import verify_product_plugins
from runtime_smoke import WindowsJob, WINDOWS_CREATE_SUSPENDED, WINDOWS_CREATE_NEW_PROCESS_GROUP, stop_owned

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tests/database/native-completion"
EXPECTED = {
    "source-table": 'SELECT * FROM "main"."products";',
    "source-alias": 'SELECT p."name" FROM main.products p;',
    "source-quoted": 'SELECT p."列 名" FROM main.products p;',
    "console-table": 'SELECT * FROM "main"."products";',
    "console-alias": 'SELECT p."name" FROM main.products p;',
    "console-quoted": 'SELECT p."列 名" FROM main.products p;',
}


def build_probe(sdk: Path, production_jar: Path) -> tuple[Path, dict]:
    layout = sdk_layout(sdk)
    runtime = execution_layout(layout)
    identity = {"sources": {p.name: sha256(p) for p in sorted(SOURCE.glob("*")) if p.is_file()},
                "productionJarSha256": sha256(production_jar), "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "builderSha256": sha256(Path(__file__))}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    work = ROOT / ".tools/database-completion-native-probe" / key
    check_space(work, 64 * 1024**2)
    work.mkdir(parents=True, exist_ok=True)
    jar = work / "plugin/lib/database-completion-probe.jar"
    with cache_lock(work / "build.lock"):
        with tempfile.TemporaryDirectory(prefix="compile-", dir=work) as directory:
            temporary = Path(directory)
            compilation = compile_java(layout, [SOURCE / "DatabaseCompletionNativeProbe.java"], temporary / "classes", temporary / "javac.args", [production_jar], runtime)
            payloads = {p.relative_to(temporary / "classes").as_posix(): p.read_bytes() for p in (temporary / "classes").rglob("*.class")}
            if any(not name.startswith("dev/openpycharm/database/nativeprobe/") for name in payloads):
                raise ValueError("Native probe must never package replacement production classes")
            payloads["META-INF/plugin.xml"] = (SOURCE / "plugin.xml").read_bytes()
            jar.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in sorted(payloads.items()):
                    entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, data)
            arguments = ["--add-opens=java.base/sun.nio.ch=ALL-UNNAMED", "--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED", "-classpath",
                         os.pathsep.join(str(layout.lib / n) for n in ("platform-loader.jar", "annotations.jar")),
                         str(SOURCE / "VerifyDatabaseCompletionProbe.java"), str(jar)]
            verified = json.loads(run_java(runtime, arguments, temporary, timeout=60).stdout)
            if verified.get("status") != "pass" or verified.get("closed") is not True or verified.get("sha256") != sha256(jar):
                raise ValueError("Actual IntelliJ probe archive verification failed")
    report = {"identity": identity, "pluginSha256": sha256(jar), "compilation": compilation, "archiveVerification": verified,
              "classes": sorted(n for n in payloads if n.endswith(".class")), "nativeApplicationLaunched": False}
    (work / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    return jar.parent.parent, report


def assess(native: dict, invocation: str, production_hash: str) -> dict:
    if native.get("invocationId") != invocation or native.get("plugin", {}).get("jarSha256") != production_hash:
        raise ValueError("Native report does not bind this invocation and actual Database JAR")
    if (native.get("status") != "pass" or native.get("nativeBasicActionGatePassed") is not True
            or native.get("projectTrusted") is not True or native.get("ownedConnectionDisconnected") is not True
            or native.get("cleanupFailure") or native.get("heartbeatTicks", 0) < 2):
        raise ValueError("Actual native Basic action/lookup/insertion gate did not pass")
    for flag in ("artificialSnapshotInjected", "lookupCreatedByProbe", "observerContributedItems", "projectTrustBypassed"):
        if native.get(flag) is not False:
            raise ValueError("A probe bypass invalidates native acceptance: " + flag)
    cases = [c for c in native.get("cases", []) if c.get("handlerDiagnostic") is not True]
    if len(cases) != len(EXPECTED) or {c.get("name") for c in cases} != set(EXPECTED):
        raise ValueError("Both real SQL source and console table/alias/quoted cases are required")
    for case in cases:
        if (case.get("nativeEntryPoint") != "ActionUtil.invokeAction:CodeCompletion" or case.get("nativePopupShown") is not True
                or case.get("nativeSelectionMethod") != "LookupImpl.finishLookup" or case.get("nativeInsertionMatched") is not True
                or case.get("observedLookupClass") != "com.intellij.codeInsight.lookup.impl.LookupImpl"
                or case.get("after") != EXPECTED[case["name"]] or not case.get("observedItems")):
            raise ValueError("Missing real Basic lookup/selection evidence for " + str(case.get("name")))
    return {"status": "pass", "actualNativeBasicLookupAndInsertion": True, "keyboardInputTested": False,
            "scope": "Native action/API integration in an owned actual IDE; not full product or keyboard acceptance"}


def prepare(sdk: Path, workspace: Path, app: Path) -> dict:
    workspace = workspace.absolute()
    if workspace.exists() or workspace.is_symlink() or not workspace.resolve().is_relative_to((ROOT / ".tools").resolve()):
        raise ValueError("Choose a new owned workspace below this checkout's .tools; existing profiles are never reused")
    target = app_layout(app)
    layout = sdk_layout(sdk)
    if workspace.resolve().is_relative_to(target.sdk_root) or workspace.resolve().is_relative_to(layout.sdk_root):
        raise ValueError("Probe workspace must be outside SDK/product")
    manifest = json.loads((target.contents / "openpycharm-build.json").read_text())
    verify_product_plugins(manifest, target.contents)
    entry = next((e for e in manifest.get("plugins", []) if e["id"] == "dev.openpycharm.database"), None)
    if entry is None:
        raise ValueError("Select an actual product containing its receipted Database plugin")
    production = target.contents / entry["jar"]
    plugin, built = build_probe(sdk, production)
    workspace.mkdir(parents=True)
    project = workspace / "project"
    project.mkdir()
    idea = project / ".idea"
    idea.mkdir()
    (idea / "modules.xml").write_text('<project version="4"><component name="ProjectModuleManager"><modules><module fileurl="file://$PROJECT_DIR$/completion-probe.iml" filepath="$PROJECT_DIR$/completion-probe.iml"/></modules></component></project>\n')
    (project / "completion-probe.iml").write_text('<module type="PYTHON_MODULE" version="4"><component name="NewModuleRootManager"><content url="file://$MODULE_DIR$"/><orderEntry type="inheritedJdk"/><orderEntry type="sourceFolder" forTests="false"/></component></module>\n')
    database = project / "owned-completion.sqlite"
    with sqlite3.connect(database) as connection:
        connection.executescript('''CREATE TABLE products(id INTEGER, name TEXT, "列 名" TEXT); INSERT INTO products VALUES(1,'产品','中文列');
CREATE TABLE orders(id INTEGER,product_id INTEGER);
CREATE TABLE "订单 表"("编号" INTEGER,"商品 名" TEXT);
CREATE TABLE "odd""table"("col""umn" TEXT);
CREATE VIEW available_products AS SELECT * FROM products;
''')
    source = project / "completion-probe.sql"
    source.write_text("SELECT * FROM pro;\n", encoding="utf-8")
    properties = prepare_profile(workspace / "profile", [target.sdk_root, layout.sdk_root, project])
    result = {"schema": 1, "workspace": str(workspace), "project": str(project), "database": str(database), "source": str(source),
              "profile": str(workspace / "profile"), "properties": str(properties), "application": str(target.sdk_root),
              "pluginDirectory": str(plugin), "probeBuild": built, "productionJarSha256": sha256(production),
              "productManifestSha256": sha256(target.contents / "openpycharm-build.json"), "productionSourceCommit": manifest.get("sourceCommit"),
              "nativeApplicationLaunched": False, "projectTrustBypassed": False,
              "limitations": ["Compile/preparation only. Root must explicitly run the native gate in its exclusive desktop phase.",
                              "Passive observers add no candidates; direct-handler diagnostic cannot satisfy the native action gate."]}
    (workspace / "prepared.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def run(prepared: dict, timeout: int) -> dict:
    app = app_layout(Path(prepared["application"]))
    workspace = Path(prepared["workspace"])
    report = workspace / "native-report.json"
    invocation = uuid.uuid4().hex
    options = workspace / "probe.vmoptions"
    original = app.contents / ("bin/pycharm.vmoptions" if app.platform == "macos" else "bin/pycharm64.exe.vmoptions")
    flags = {"plugin.path": prepared["pluginDirectory"], "openpycharm.database.completion.report": str(report),
             "openpycharm.database.completion.root": str(workspace), "openpycharm.database.completion.project": prepared["project"],
             "openpycharm.database.completion.database": prepared["database"], "openpycharm.database.completion.source": prepared["source"],
             "openpycharm.database.completion.invocation": invocation, "openpycharm.database.completion.expected.jar": prepared["productionJarSha256"]}
    options.write_text(original.read_text() + "\n" + "\n".join(f"-D{k}={v}" for k, v in flags.items()) + "\n")
    environment = dict(os.environ, OPENPYCHARM_PROPERTIES=prepared["properties"], OPENPYCHARM_VM_OPTIONS=str(options))
    executable = app.contents / ("MacOS/pycharm" if app.platform == "macos" else "bin/pycharm64.exe")
    result = {**prepared, "invocationId": invocation, "nativeApplicationLaunched": False}
    process = job = None
    resumed = False
    with (workspace / "launch.log").open("wb") as log:
        try:
            windows = app.platform == "windows"
            job = WindowsJob() if windows else None
            kwargs = {"creationflags": WINDOWS_CREATE_SUSPENDED | WINDOWS_CREATE_NEW_PROCESS_GROUP} if windows else {"start_new_session": True}
            process = subprocess.Popen([str(executable), prepared["project"]], env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **kwargs)
            result["ownedPid"] = process.pid
            result["nativeApplicationLaunched"] = True
            if job is not None:
                job.assign_and_resume(process)
                resumed = True
            deadline = time.monotonic() + timeout
            while process.poll() is None and not report.is_file() and time.monotonic() < deadline:
                time.sleep(.25)
            if not report.is_file():
                dump = subprocess.run([str(app.jcmd), str(process.pid), "Thread.print", "-l"], capture_output=True, text=True, timeout=15)
                (workspace / "external-timeout-threads.txt").write_text(dump.stdout + dump.stderr)
                raise ValueError("No native report before timeout; retain ordinary trust state and owned-process evidence")
            native = json.loads(report.read_text())
            result["native"] = native
            result["assessment"] = assess(native, invocation, prepared["productionJarSha256"])
        except Exception as error:
            result["assessment"] = {"status": "fail", "error": str(error)}
        finally:
            try:
                if process is not None:
                    if job is not None and not resumed and process.poll() is None:
                        process.kill()
                    result["cleanup"] = stop_owned(process, job)
                    result["ownedProcessExit"] = process.returncode
                elif job is not None:
                    job.stop()
            except Exception as error:
                result["cleanup"] = {"status": "fail", "error": str(error), "ownedPid": None if process is None else process.pid}
                result["assessment"] = {"status": "fail", "error": "Owned process cleanup failed; retain exact PID/logs"}
    (workspace / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="Explicitly start a new owned IDE; default is compile/preparation only")
    parser.add_argument("--timeout", type=int, default=210)
    args = parser.parse_args()
    if not 60 <= args.timeout <= 300:
        parser.error("Use native timeout 60..300 seconds")
    prepared = prepare(args.sdk, args.workspace, args.app)
    if not args.run:
        print(json.dumps({"prepared": str(Path(prepared["workspace"]) / "prepared.json"), "nativeApplicationLaunched": False,
                          "probeJarSha256": prepared["probeBuild"]["pluginSha256"], "productionJarSha256": prepared["productionJarSha256"]}))
        return 0
    result = run(prepared, args.timeout)
    print(json.dumps({"result": str(Path(prepared["workspace"]) / "result.json"), "assessment": result["assessment"]}))
    return 0 if result["assessment"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
