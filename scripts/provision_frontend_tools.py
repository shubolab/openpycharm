#!/usr/bin/env python3
"""Explicitly provision pinned frontend M0 tools in this checkout's owned cache.

No npm/install scripts, shell commands, application modifications, or implicit
downloads from the compiler/provider. Archive bytes, extraction, bundled source
closure and every published legal text are authenticated before atomic publish.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

from platform_layout import cache_lock
from bootstrap import check_space

ROOT = Path(__file__).resolve().parent.parent
PIN = ROOT / "plugins/frontend/tools.lock.json"
DEFAULT_CACHE = ROOT / ".tools/frontend-m0-tools"
OWNER = "OpenPyCharm frontend M0"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular(path: Path) -> bool:
    return stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()


def owned(path: Path, boundary: Path = ROOT / ".tools") -> Path:
    path = Path(os.path.abspath(path))
    boundary = Path(os.path.abspath(boundary))
    if path == boundary or not path.is_relative_to(boundary):
        raise ValueError("Frontend cache/output must stay below this checkout's .tools")
    for component in [boundary, *reversed(path.relative_to(boundary).parents), path.relative_to(boundary)]:
        current = component if component.is_absolute() else boundary / component
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise ValueError("Frontend cache ancestors cannot contain symlinks")
    if path.resolve() != path:
        raise ValueError("Frontend cache cannot resolve through symlinks")
    return path


def relative(value: str) -> str:
    if (not isinstance(value, str) or not value or value != PurePosixPath(value).as_posix()
            or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(c in value for c in "\\:\x00\r\n") or any(ord(c) < 32 for c in value)):
        raise ValueError("Archive/receipt paths must be clean relative POSIX paths")
    return value


def validate_artifact(item: dict) -> None:
    if (not isinstance(item.get("size"), int) or isinstance(item["size"], bool) or not 0 < item["size"] <= 100_000_000
            or re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) is None):
        raise ValueError("Frontend artifact requires bounded exact size and SHA-256")
    endpoint = urllib.parse.urlsplit(item["url"])
    if (endpoint.scheme != "https" or endpoint.username is not None or endpoint.password is not None
            or endpoint.port not in {None, 443} or endpoint.query or endpoint.fragment):
        raise ValueError("Frontend artifacts require a clean pinned HTTPS endpoint")
    if item["id"].startswith("node-"):
        target = item.get("target")
        names = {"macos-arm64": "darwin-arm64.tar.xz", "windows-x64": "win-x64.zip"}
        expected = "/dist/v24.22.3/node-v24.22.3-" + names.get(target, "invalid")
        if endpoint.hostname != "nodejs.org" or endpoint.path != expected or item["version"] != "24.22.3":
            raise ValueError("Node artifact is outside its exact official version/target")
    else:
        name = item.get("package", item["id"])
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) is None:
            raise ValueError("Unexpected npm package name")
        expected = "/" + name + "/-/" + name + "-" + item["version"] + ".tgz"
        if endpoint.hostname != "registry.npmjs.org" or endpoint.path != expected or not item.get("integrity", "").startswith("sha512-"):
            raise ValueError("npm artifact is outside its exact official package/version")
    extraction = item["extract"]
    relative(extraction["prefix"]); relative(extraction["destination"])
    for path in extraction.get("files", []):
        relative(path)
    payload = item.get("payload")
    if payload is not None:
        if not isinstance(payload, dict) or not 0 < len(payload) <= 300:
            raise ValueError("Frontend artifact requires a bounded file manifest")
        for path, record in payload.items():
            relative(path)
            if (not path.startswith(extraction["destination"] + "/") or not isinstance(record.get("size"), int)
                    or isinstance(record["size"], bool) or not 0 <= record["size"] <= 160_000_000
                    or re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")) is None):
                raise ValueError("Invalid frontend pinned payload record")


def load_pin() -> dict:
    if not regular(PIN):
        raise ValueError("Frontend pin must be a regular tracked file")
    pin = json.loads(PIN.read_text())
    if pin.get("schemaVersion") != 1 or not isinstance(pin.get("artifacts"), list):
        raise ValueError("Unsupported frontend tools pin")
    items = pin["artifacts"]
    if len({x["id"] for x in items}) != len(items):
        raise ValueError("Duplicate frontend artifact identity")
    for item in items:
        validate_artifact(item)
        if not item.get("payload"):
            raise ValueError("Frontend pin must include each extracted payload hash")
    return pin


def authenticate(path: Path, item: dict) -> bytes:
    if not regular(path) or path.stat().st_size != item["size"]:
        raise ValueError("Frontend artifact size/type mismatch: " + item["id"])
    data = path.read_bytes()
    if digest(data) != item["sha256"]:
        raise ValueError("Frontend artifact SHA-256 mismatch: " + item["id"])
    if item.get("integrity") and "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode() != item["integrity"]:
        raise ValueError("Frontend npm integrity mismatch: " + item["id"])
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        response.close()
        raise ValueError("Pinned frontend download redirected; route requires explicit review")


def archive_path(cache: Path, item: dict) -> Path:
    name = PurePosixPath(urllib.parse.urlsplit(item["url"]).path).name
    return owned(cache / "archives" / (item["sha256"] + "-" + name))


def download(item: dict, destination: Path) -> None:
    validate_artifact(item)
    destination = owned(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(item["url"], headers={"User-Agent": "OpenPyCharm-frontend-M0-provisioner"})
    candidate = None
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200 or response.geturl() != item["url"]:
                raise ValueError("Frontend artifact response endpoint/status differs from its pin")
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != item["size"]:
                raise ValueError("Frontend response size differs from its pin")
            with tempfile.NamedTemporaryFile(prefix=".frontend-download-", dir=destination.parent, delete=False) as stream:
                candidate = Path(stream.name)
                remaining = item["size"] + 1
                while remaining:
                    block = response.read(min(1024 * 1024, remaining))
                    if not block:
                        break
                    stream.write(block); remaining -= len(block)
        authenticate(candidate, item)
        os.replace(candidate, destination)
    finally:
        if candidate is not None and candidate.exists():
            candidate.unlink()


def members(data: bytes, fmt: str):
    """Yield archive metadata and bytes; never call an archive extraction API."""
    if fmt == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                name = entry.filename.rstrip("/")
                relative(name)
                mode = entry.external_attr >> 16
                kind = "directory" if entry.is_dir() else "file" if stat.S_IFMT(mode) in {0, stat.S_IFREG} else "link-or-special"
                yield name, kind, entry.file_size, (lambda e=entry: archive.read(e))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz" if fmt == "tar.xz" else "r:gz") as archive:
            for entry in archive.getmembers():
                name = entry.name.rstrip("/")
                relative(name)
                kind = "directory" if entry.isdir() else "file" if entry.isfile() else "link-or-special"
                yield name, kind, entry.size, (lambda e=entry: archive.extractfile(e).read())


def extract(data: bytes, item: dict, stage: Path) -> dict:
    stage = owned(stage)
    config = item["extract"]; prefix = config["prefix"] + "/"; destination = config["destination"]
    wanted = set(config.get("files", [])); found = {}; seen = set(); total = 0
    for name, kind, size, read in members(data, item["format"]):
        if name in seen:
            raise ValueError("Duplicate frontend archive member")
        seen.add(name)
        if kind == "directory":
            continue
        if not name.startswith(prefix):
            raise ValueError("Frontend archive member escaped its pinned root")
        inner = relative(name[len(prefix):])
        selected = config.get("allRegularFiles", False) or inner in wanted
        if not selected:
            continue
        if kind != "file" or size < 0 or size > 160_000_000:
            raise ValueError("Selected frontend archive member is a link/special/oversized file")
        total += size
        if total > 160_000_000 or len(found) >= 300:
            raise ValueError("Frontend archive extraction exceeds its bound")
        content = read()
        if len(content) != size:
            raise ValueError("Frontend archive member size mismatch")
        rel = relative(destination + "/" + inner); target = stage / rel
        if target.exists() or target.is_symlink():
            raise ValueError("Frontend extracted payload collision")
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        target.chmod(0o755 if rel == item.get("nodeExecutable") else 0o644)
        found[inner] = {"path": rel, "size": size, "sha256": digest(content)}
    if wanted and set(found) != wanted:
        raise ValueError("Pinned frontend archive members are missing")
    if not found:
        raise ValueError("Frontend archive selected no files")
    if "expectedPackage" in item:
        package = json.loads((stage / destination / "package.json").read_text())
        expected = item["expectedPackage"]
        if package.get("name") != expected["name"] or package.get("version") != expected["version"]:
            raise ValueError("Extracted npm package identity differs from its pin")
        if expected.get("noRuntimeDependencies") and any(package.get(key) for key in ("dependencies", "optionalDependencies", "peerDependencies", "bundledDependencies")):
            raise ValueError("Unexpected unpinned external npm runtime dependency")
    for legal in item.get("legalFiles", []):
        actual = found[legal["path"].removeprefix(config["prefix"] + "/")]
        if actual["sha256"] != legal["sha256"] or actual["size"] != legal["size"]:
            raise ValueError("Bundled dependency legal text differs from its pin")
    records = {record["path"]: {k: record[k] for k in ("size", "sha256")} for record in found.values()}
    if item.get("payload") is not None and records != item["payload"]:
        raise ValueError("Extracted frontend file manifest differs from pinned archive payload")
    return records


def verify_closure(stage: Path, pin: dict) -> None:
    closure = pin["bundledClosure"]; path = stage / closure["sourceMapPath"]
    if digest(path.read_bytes()) != closure["sourceMapSha256"]:
        raise ValueError("Published CLI source-map closure differs from its pin")
    source_map = json.loads(path.read_text()); packages = {}
    for source in source_map["sources"]:
        match = re.search(r"node_modules/\.pnpm/([^/]+)/node_modules/((?:@[^/]+/)?[^/]+)/", source)
        if match:
            package, version = match[2], match[1].rsplit("@", 1)[1]
            if package in packages and packages[package] != version:
                raise ValueError("Multiple bundled versions need an explicit expanded lock")
            packages[package] = version
        elif "node_modules/" in source:
            raise ValueError("Unknown published bundle dependency path")
    notices = {x["package"]: x["version"] for x in pin["artifacts"] if x.get("purpose") == "bundled-cli-corresponding-notices-only"}
    if len(source_map["sources"]) != closure["sourceCount"] or packages != closure["packages"] or packages != notices:
        raise ValueError("Bundled CLI dependency/notice closure is incomplete")


def authenticate_runtime(receipt: Path) -> dict:
    receipt = owned(receipt)
    if not regular(receipt) or receipt.stat().st_size > 1_000_000:
        raise ValueError("Frontend runtime receipt must be a bounded regular file")
    report = json.loads(receipt.read_text()); root = owned(Path(report["runtimeRoot"]))
    if (report.get("owner") != OWNER or receipt != root / "frontend-tools.json"
            or report.get("lockSha256") != digest(PIN.read_bytes()) or not isinstance(report.get("files"), dict)):
        raise ValueError("Frontend runtime receipt identity/source differs")
    pin = load_pin()
    target = report.get("target")
    if target not in {"macos-arm64", "windows-x64"}:
        raise ValueError("Unexpected frontend runtime target")
    items = [x for x in pin["artifacts"] if not x.get("target") or x["target"] == target]
    expected = {name: record for item in items for name, record in item["payload"].items()}
    node = next(x for x in items if x["id"].startswith("node-"))
    if (report["files"] != expected or report["entries"] != {"node": node["nodeExecutable"], **pin["runtimeEntries"]}
            or report.get("installationScriptsExecuted") is not False
            or report.get("artifacts") != [{k: item[k] for k in ("id", "sha256", "size")} for item in items]
            or report.get("productionPackaged") is not False
            or report.get("bundledPackageNotices") != len(pin["bundledClosure"]["packages"])):
        raise ValueError("Frontend receipt differs from its pinned payload/entry closure")
    actual = set()
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            child = Path(parent) / name
            if child.is_symlink() or not (child.is_dir() or regular(child)):
                raise ValueError("Frontend runtime contains a symlink/special file")
        actual.update((Path(parent) / name).relative_to(root).as_posix() for name in files)
    if actual != set(expected) | {"frontend-tools.json"}:
        raise ValueError("Frontend runtime payload set differs from its receipt")
    for rel, record in expected.items():
        path = root / relative(rel)
        if not regular(path) or path.stat().st_size != record["size"] or digest(path.read_bytes()) != record["sha256"]:
            raise ValueError("Frontend runtime payload differs from receipt: " + rel)
    for key in ("node", "typescriptLanguageServer", "typescriptServer"):
        if relative(report["entries"][key]) not in expected:
            raise ValueError("Frontend runtime entry is not authenticated")
    return {**report, "receipt": str(receipt), "receiptSha256": digest(receipt.read_bytes())}


def provision(target: str, cache: Path = DEFAULT_CACHE, *, offline: bool = False) -> dict:
    if target not in {"macos-arm64", "windows-x64"}:
        raise ValueError("Frontend M0 supports pinned Mac arm64/Windows x64 tools only")
    cache = owned(cache); cache.mkdir(parents=True, exist_ok=True)
    pin = load_pin(); pin_sha = digest(PIN.read_bytes()); runtime = owned(cache / "runtime" / target / pin_sha)
    selected = [item for item in pin["artifacts"] if not item.get("target") or item["target"] == target]
    check_space(cache, sum(item["size"] + sum(record["size"] for record in item["payload"].values()) for item in selected))
    if (cache / "provision.lock").is_symlink():
        raise ValueError("Frontend cache lock cannot be a symlink")
    with cache_lock(cache / "provision.lock"):
        if runtime.exists():
            return authenticate_runtime(runtime / "frontend-tools.json")
        items = selected
        for item in items:
            archive = archive_path(cache, item)
            if not archive.exists():
                if offline:
                    raise ValueError("Pinned frontend artifact is missing; run explicit provision first: " + item["id"])
                download(item, archive)
            authenticate(archive, item)
        runtime.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".frontend-stage-", dir=runtime.parent) as directory:
            stage = Path(directory); files = {}
            for item in items:
                extracted = extract(authenticate(archive_path(cache, item), item), item, stage)
                if files.keys() & extracted.keys():
                    raise ValueError("Frontend artifact payload overlap")
                files.update(extracted)
            verify_closure(stage, pin)
            node = next(x for x in items if x["id"].startswith("node-"))
            report = {"schema": 1, "owner": OWNER, "target": target, "lockSha256": pin_sha,
                      "runtimeRoot": str(runtime), "entries": {"node": node["nodeExecutable"], **pin["runtimeEntries"]},
                      "files": files, "artifacts": [{k: x[k] for k in ("id", "sha256", "size")} for x in items],
                      "bundledPackageNotices": len(pin["bundledClosure"]["packages"]),
                      "installationScriptsExecuted": False, "productionPackaged": False}
            (stage / "frontend-tools.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
            os.replace(stage, runtime)
        return authenticate_runtime(runtime / "frontend-tools.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("macos-arm64", "windows-x64"), required=True)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(); report = provision(args.target, args.cache, offline=args.offline)
    print(json.dumps({k: report[k] for k in ("owner", "target", "receipt", "receiptSha256", "bundledPackageNotices", "installationScriptsExecuted")}, indent=2))


if __name__ == "__main__":
    main()
