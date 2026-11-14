#!/usr/bin/env python3
"""Build the bundled native frontend plugin from existing authenticated tools.

This builder never provisions tools, launches Node, starts an IDE or signs native
files. Output stays in this checkout's .tools; an explicit provision receipt may
be read from a sibling worktree's repository-owned cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from bootstrap import PIN_PATH, check_space, sha256
from build_framework_plugin import sdk_layout, execution_layout
from platform_layout import cache_lock, java_compiler_invocation
from provision_frontend_tools import load_pin, relative, verify_closure

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "plugins/frontend"
PIN = SOURCE / "tools.lock.json"
PLUGIN_ID = "dev.openpycharm.frontend"
VERSION = "0.1.0-dev.4"
BUNDLE_OWNER = "OpenPyCharm bundled frontend"
TARGETS = ("macos-arm64", "windows-x64")
JAVA_NAMES = (
    "FrontendNativeProcess", "FrontendBoundedOutput", "FrontendProcessLifetime",
    "FrontendProductLspProvider", "FrontendBundledRuntime", "FrontendProductScope",
    "FrontendProjectSettings", "FrontendSettingsLifecycle", "FrontendProjectConfigurable",
)
FORBIDDEN_CLASSES = ("FrontendLspProvider", "FrontendRuntime", "FrontendFixtureScope", "FrontendBuildScope")
READER = SOURCE / "product-build-support/VerifyFrontendProductArchive.java"
RESOURCES = SOURCE / "product-resources"


def no_links(path: Path, kind: str | None = None) -> Path:
    path = Path(path)
    if not path.is_absolute() or Path(os.path.abspath(path)) != path:
        raise ValueError("Frontend paths must be absolute and normalized")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError("Frontend paths cannot contain symlinks")
    if kind is not None:
        mode = path.lstat().st_mode
        if not (stat.S_ISREG(mode) if kind == "file" else stat.S_ISDIR(mode)):
            raise ValueError("Frontend input must be a regular " + kind)
    return path


def output_path(path: Path) -> Path:
    path = no_links(Path(os.path.abspath(path)))
    boundary = ROOT / ".tools"
    if path == boundary or not path.is_relative_to(boundary):
        raise ValueError("Frontend product output must stay below this checkout's .tools")
    return path


def cache_boundaries() -> list[Path]:
    boundaries = [ROOT / ".tools"]
    if ROOT.parent.name == "worktrees" and ROOT.parent.parent.name == ".tools":
        boundaries.append(ROOT.parents[2] / ".tools")
    return boundaries


def read_json(path: Path) -> dict:
    path = no_links(path, "file")
    if path.stat().st_size > 1_000_000:
        raise ValueError("Frontend metadata exceeds its size bound")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate frontend metadata key")
            result[key] = value
        return result
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("Frontend metadata must be an object")
    return value


def runtime_manifest(pin: dict, target: str) -> dict:
    if target not in TARGETS:
        raise ValueError("Unsupported frontend target")
    selected = [item for item in pin["artifacts"] if not item.get("target") or item["target"] == target]
    files = {}
    for item in selected:
        for name, record in item["payload"].items():
            relative(name)
            if name in files:
                raise ValueError("Frontend pinned runtime payload overlaps")
            files[name] = record
    node = [item for item in selected if item["id"].startswith("node-")]
    if len(node) != 1:
        raise ValueError("Frontend target needs exactly one pinned Node")
    entries = {"node": node[0]["nodeExecutable"], **pin["runtimeEntries"]}
    if any(relative(name) not in files for name in entries.values()):
        raise ValueError("Frontend entry is outside the authenticated payload")
    return {"files": files, "entries": entries}


def inspect_tree(root: Path, expected: dict, modes: dict | None = None) -> dict:
    """Authenticate every file, directory and POSIX mode without following links."""
    root = no_links(root, "directory")
    wanted_directories = set()
    for name in expected:
        relative(name)
        wanted_directories.update(parent.as_posix() for parent in Path(name).parents if parent.as_posix() != ".")
    found = {}; directories_found = set(); visited = 0
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(directory) / name; rel = path.relative_to(root).as_posix()
            visited += 1
            if visited > len(expected) + len(wanted_directories) + 1:
                raise ValueError("Frontend tree exceeds its exact payload bound")
            no_links(path)
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                directories_found.add(rel)
                if rel not in wanted_directories:
                    raise ValueError("Unexpected frontend payload directory: " + rel)
                continue
            if not stat.S_ISREG(mode) or rel not in expected:
                raise ValueError("Unexpected frontend payload file or special entry: " + rel)
            record = expected[rel]
            if path.stat().st_size != record["size"] or sha256(path) != record["sha256"]:
                raise ValueError("Frontend payload size/SHA-256 differs: " + rel)
            permissions = stat.S_IMODE(mode)
            if os.name != "nt" and modes is not None and permissions != modes[rel]:
                raise ValueError("Frontend payload mode differs: " + rel)
            found[rel] = {**record, "mode": permissions}
    if set(found) != set(expected) or directories_found != wanted_directories:
        raise ValueError("Frontend tree is missing pinned payload entries")
    return found


def authenticate_runtime(receipt: Path, target: str) -> dict:
    receipt = no_links(receipt, "file")
    if not any(receipt.is_relative_to(no_links(boundary)) and receipt != boundary for boundary in cache_boundaries()):
        raise ValueError("Explicit frontend receipt must be in a repository-owned .tools cache")
    pin = load_pin(); lock_sha = sha256(PIN); expected = runtime_manifest(pin, target)
    saved = read_json(receipt)
    keys = {"schema", "owner", "target", "runtimeRoot", "lockSha256", "files", "entries", "artifacts",
            "installationScriptsExecuted", "productionPackaged", "bundledPackageNotices"}
    selected = [item for item in pin["artifacts"] if not item.get("target") or item["target"] == target]
    if (set(saved) != keys or type(saved.get("schema")) is not int or saved["schema"] != 1
            or saved.get("owner") != "OpenPyCharm frontend M0" or saved.get("target") != target
            or saved.get("lockSha256") != lock_sha or saved.get("files") != expected["files"]
            or saved.get("entries") != expected["entries"] or saved.get("installationScriptsExecuted") is not False
            or saved.get("productionPackaged") is not False
            or saved.get("bundledPackageNotices") != len(pin["bundledClosure"]["packages"])
            or saved.get("artifacts") != [{key: item[key] for key in ("id", "sha256", "size")} for item in selected]):
        raise ValueError("Frontend provision receipt differs from the pinned identity/payload/legal closure")
    runtime = no_links(Path(saved["runtimeRoot"]), "directory")
    if receipt != runtime / "frontend-tools.json":
        raise ValueError("Frontend provision receipt and runtime root differ")
    records = {**expected["files"], "frontend-tools.json": {"size": receipt.stat().st_size, "sha256": sha256(receipt)}}
    modes = {name: 0o755 if name == expected["entries"]["node"] else 0o644 for name in records}
    # The provisioner writes its receipt under the ordinary umask. Its payload
    # modes, unlike the receipt's metadata mode, are explicitly normalized.
    modes["frontend-tools.json"] = stat.S_IMODE(receipt.stat().st_mode)
    inspected = inspect_tree(runtime, records, modes)
    verify_closure(runtime, pin)
    return {"root": runtime, "target": target, "manifest": expected, "lockSha256": lock_sha,
            "receiptSha256": records["frontend-tools.json"]["sha256"], "records": inspected,
            "bundledPackageNotices": saved["bundledPackageNotices"]}


def bundled_manifest(authenticated: dict) -> dict:
    return {"schema": 1, "target": authenticated["target"], "owner": BUNDLE_OWNER,
            "lockSha256": authenticated["lockSha256"], **authenticated["manifest"]}


def copy_runtime(authenticated: dict, destination: Path) -> dict:
    destination = output_path(destination)
    if destination.exists():
        raise ValueError("Frontend runtime staging destination must be new")
    records = authenticated["manifest"]["files"]; node = authenticated["manifest"]["entries"]["node"]
    check_space(destination, sum(record["size"] for record in records.values()) + 1_000_000)
    destination.mkdir(parents=True)
    for name, record in sorted(records.items()):
        source = no_links(authenticated["root"] / name, "file")
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o755 if name == node else 0o644)
    manifest = destination / "bundled-runtime.json"
    manifest.write_text(json.dumps(bundled_manifest(authenticated), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest.chmod(0o644)
    expected = {**records, "bundled-runtime.json": {"size": manifest.stat().st_size, "sha256": sha256(manifest)}}
    modes = {name: 0o755 if name == node else 0o644 for name in expected}
    return inspect_tree(destination, expected, modes)


def source_inputs() -> dict:
    files = [SOURCE / "src/dev/openpycharm/frontend" / (name + ".java") for name in JAVA_NAMES]
    no_links(RESOURCES, "directory")
    for directory, directories, names in os.walk(RESOURCES, followlinks=False):
        for name in directories:
            no_links(Path(directory) / name, "directory")
        files.extend(Path(directory) / name for name in names)
    files.extend([ROOT / "LICENSE", READER, PIN, PIN_PATH, Path(__file__), ROOT / "scripts/bootstrap.py",
                  ROOT / "scripts/build_framework_plugin.py", ROOT / "scripts/platform_layout.py",
                  ROOT / "scripts/provision_frontend_tools.py"])
    for path in files:
        no_links(path, "file")
        if not path.is_relative_to(ROOT):
            raise ValueError("Frontend build input escaped its source root")
    if not {"META-INF/plugin.xml", "META-INF/NOTICE"}.issubset({path.relative_to(RESOURCES).as_posix() for path in files if path.is_relative_to(RESOURCES)}):
        raise ValueError("Product frontend descriptor and accurate product NOTICE are required")
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(set(files))}


def render_descriptor(data: bytes, version: str) -> bytes:
    data = data.replace(b"@VERSION@", version.encode("utf-8")); descriptor = ET.fromstring(data)
    extensions = descriptor.find("extensions")
    provider = extensions.find("integrationProvider") if extensions is not None else None
    if (descriptor.tag != "idea-plugin" or descriptor.findtext("id") != PLUGIN_ID or descriptor.findtext("version") != version
            or {node.text for node in descriptor.findall("depends")} != {"com.intellij.modules.platform", "com.intellij.modules.lsp"}
            or extensions is None or extensions.get("defaultExtensionNs") != "com.intellij.platform.lsp" or provider is None
            or provider.get("implementation") != "dev.openpycharm.frontend.FrontendProductLspProvider"):
        raise ValueError("Product frontend descriptor identity/canonical LSP registration differs")
    return data


def validate_product(plugin: Path, saved: dict) -> None:
    records = saved.get("fileRecords", {})
    if (not records or saved.get("files") != {name: record["sha256"] for name, record in records.items()}
            or saved.get("jarSha256") != saved["files"].get("lib/frontend.jar")
            or saved.get("archiveVerification", {}).get("status") != "pass"
            or saved["archiveVerification"].get("sha256") != saved["jarSha256"]):
        raise ValueError("Frontend product receipt is incomplete or inconsistent")
    inspect_tree(plugin, records, {name: record["mode"] for name, record in records.items()})


def compile_product(layout, runtime, destination: Path, temporary: Path) -> dict:
    destination.mkdir()
    sources = [SOURCE / "src/dev/openpycharm/frontend" / (name + ".java") for name in JAVA_NAMES]
    cp = sorted(layout.lib.glob("*.jar"))
    arguments = ["--release", "21", "-encoding", "UTF-8", "-proc:none", "-classpath", os.pathsep.join(map(str, cp)),
                 "-d", str(destination), *map(str, sources)]
    invocation = java_compiler_invocation(runtime.javac, arguments, temporary / "javac.args")
    result = subprocess.run(invocation.command, cwd=invocation.cwd, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError("Frontend product compilation failed:\n" + result.stdout + result.stderr)
    return {"sdkClasspathJars": len(cp), "release": 21, "stdout": result.stdout, "stderr": result.stderr}


def verify_archive(layout, runtime, jar: Path, temporary: Path) -> dict:
    arguments = ["--add-opens=java.base/sun.nio.ch=ALL-UNNAMED", "--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED",
                 "--class-path", os.pathsep.join(str(layout.lib / name) for name in ("platform-loader.jar", "annotations.jar")),
                 str(READER), str(jar)]
    command = [str(runtime.java), *arguments]; cwd = None
    if os.name == "nt":
        argument_file = temporary / "reader.args"
        if any(any(char in value for char in "\r\n\0") for value in arguments):
            raise ValueError("Frontend Java arguments contain a line break or NUL")
        argument_file.write_text("\n".join('"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"' for value in arguments) + "\n", encoding="utf-8")
        command, cwd = [str(runtime.java), "@reader.args"], temporary
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError("Frontend product archive-reader failed:\n" + result.stdout + result.stderr)
    report = json.loads(result.stdout)
    if report.get("status") != "pass" or report.get("closed") is not True or report.get("sha256") != sha256(jar):
        raise ValueError("Frontend product archive-reader receipt differs")
    return report


def build(sdk: Path, runtime_receipt: Path, version: str = VERSION, host_sdk: Path | None = None) -> tuple[Path, dict]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-[A-Za-z0-9.-]+", version) is None:
        raise ValueError("Frontend product requires a concrete prerelease version")
    layout = sdk_layout(sdk); runtime = execution_layout(layout, host_sdk)
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    authenticated = authenticate_runtime(runtime_receipt, target); pin = load_pin()
    identity = {"pluginId": PLUGIN_ID, "version": version, "target": target, "sources": source_inputs(),
                "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "executionSdkReceiptSha256": sha256(runtime.sdk_root.parent / ".openpycharm-platform.json"),
                "toolchainLockSha256": authenticated["lockSha256"], "runtimeReceiptSha256": authenticated["receiptSha256"],
                "compiler": subprocess.check_output([str(runtime.javac), "-version"], text=True, stderr=subprocess.STDOUT, timeout=15).strip()}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    work = output_path(ROOT / ".tools/frontend-product-plugin" / key)
    check_space(work, sum(record["size"] for record in authenticated["manifest"]["files"].values()) + 64 * 1024**2)
    work.mkdir(parents=True, exist_ok=True); no_links(work / "build.lock")
    plugin = work / "plugin"; receipt = work / "build.json"
    with cache_lock(work / "build.lock"):
        no_links(plugin); no_links(receipt)
        if plugin.exists() or receipt.exists():
            saved = read_json(receipt)
            if saved.get("identity") != identity:
                raise ValueError("Existing frontend build receipt differs; cached output is never overwritten")
            validate_product(plugin, saved)
            return plugin, saved
        with tempfile.TemporaryDirectory(prefix="stage-", dir=work) as name:
            temporary = Path(name); staged = temporary / "plugin"; classes = temporary / "classes"
            compilation = compile_product(layout, runtime, classes, temporary)
            payloads = {path.relative_to(classes).as_posix(): path.read_bytes() for path in sorted(classes.rglob("*.class"))}
            for name in payloads:
                if any(name.startswith("dev/openpycharm/frontend/" + forbidden + suffix) for forbidden in FORBIDDEN_CLASSES for suffix in (".", "$")):
                    raise ValueError("Fixture-only frontend class leaked into the product")
            for path in sorted(RESOURCES.rglob("*")):
                if path.is_file():
                    name = path.relative_to(RESOURCES).as_posix()
                    payloads[name] = render_descriptor(path.read_bytes(), version) if name == "META-INF/plugin.xml" else path.read_bytes()
            payloads["META-INF/LICENSE"] = (ROOT / "LICENSE").read_bytes()
            payloads["META-INF/frontend-tools.lock.json"] = PIN.read_bytes()
            for item_target in TARGETS:
                payloads["META-INF/frontend-runtime-" + item_target + ".json"] = json.dumps(runtime_manifest(pin, item_target), sort_keys=True).encode()
            jar = staged / "lib/frontend.jar"; jar.parent.mkdir(parents=True)
            with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
                for entry_name, data in sorted(payloads.items()):
                    entry = zipfile.ZipInfo(entry_name, (1980, 1, 1, 0, 0, 0)); entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, data)
            jar.chmod(0o644); verification = verify_archive(layout, runtime, jar, temporary)
            runtime_records = copy_runtime(authenticated, staged / "runtime" / target)
            # Reauthenticate both source and copied data before publishing: the
            # provision cache is read-only even if a build fails midway.
            again = authenticate_runtime(runtime_receipt, target)
            if again["receiptSha256"] != authenticated["receiptSha256"] or source_inputs() != identity["sources"]:
                raise ValueError("Frontend sources/runtime changed while building")
            records = {"lib/frontend.jar": {"size": jar.stat().st_size, "sha256": sha256(jar), "mode": stat.S_IMODE(jar.stat().st_mode)}}
            records.update({"runtime/" + target + "/" + name: record for name, record in runtime_records.items()})
            saved = {"schema": 1, "identity": identity, "pluginId": PLUGIN_ID, "version": version, "target": target,
                     "pluginDirectory": str(plugin), "jarSha256": sha256(jar), "files": {name: record["sha256"] for name, record in records.items()},
                     "fileRecords": records, "payloadSha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())},
                     "classes": sorted(name for name in payloads if name.endswith(".class")), "compilation": compilation,
                     "archiveVerification": verification, "targetPlatform": layout.platform, "executionPlatform": runtime.platform,
                     "nativeTargetRuntime": layout.platform == runtime.platform, "toolchainLockSha256": authenticated["lockSha256"],
                     "runtimeReceiptSha256": authenticated["receiptSha256"], "bundledPackageNotices": authenticated["bundledPackageNotices"],
                     "runtimePayloadCount": len(authenticated["manifest"]["files"]), "runtimeBytes": sum(record["size"] for record in authenticated["manifest"]["files"].values()),
                     "installationScriptsExecuted": False, "nodeStarted": False, "nativeIdeStarted": False, "nativeFilesSignedByBuilder": False,
                     "limitations": ["Compile/archive/payload proof only; native product UI and Windows runtime acceptance remain separate.",
                                     "Nested Node bytes retain their original pin; re-signing Node requires a separately verified identity policy.",
                                     "POSIX mode validation is enforced on POSIX hosts; Windows has no equivalent executable permission bits."]}
            validate_product(staged, saved)
            pending = temporary / "build.json"
            pending.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
            staged.rename(plugin); pending.replace(receipt)
            return plugin, saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--host-sdk", type=Path)
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    try:
        plugin, report = build(args.sdk, args.runtime_receipt, args.version, args.host_sdk)
        print(json.dumps({"plugin": str(plugin), "build": report}, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
