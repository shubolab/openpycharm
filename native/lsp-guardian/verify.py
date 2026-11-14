#!/usr/bin/env python3
"""Offline prototype build/test receipt. Never launches IDEs or Node."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile

SOURCE = Path(__file__).resolve().parent
MODULE = "golang.org/x/sys"
VERSION = "v0.38.0"
SUM = "h1:3yZWxaJjBmCWXqhN1qh02AkOnCQ1poK6oF+a7xWL6Gc="


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*"))
            if p.is_file() and (p.suffix in (".go", ".py", ".java", ".json", ".txt", ".md") or p.name in ("go.mod", "go.sum"))
            and "__pycache__" not in p.parts}


def authenticate_go(root: Path, archive: Path, expected: str) -> int:
    if len(expected) != 64 or sha(archive) != expected:
        raise ValueError("Go distribution archive hash mismatch")
    members: set[Path] = set()

    def compare(name: str, data) -> None:
        relative = Path(name)
        if relative.parts[0] != "go" or any(p in ("..", "") for p in relative.parts):
            raise ValueError("unexpected Go archive path")
        target = root.joinpath(*relative.parts[1:])
        if target in members:
            raise ValueError("duplicate Go archive member")
        if target.is_symlink() or not target.is_file() or target.resolve().is_relative_to(root) is False:
            raise ValueError(f"Go archive member absent or symlink: {name}")
        if hashlib.file_digest(data, "sha256").hexdigest() != sha(target):
            raise ValueError(f"Go distribution differs from authenticated archive: {name}")
        members.add(target)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                if not member.is_dir():
                    with package.open(member) as data:
                        compare(member.filename, data)
    else:
        with tarfile.open(archive, "r:gz") as package:
            for member in package:
                if member.isfile():
                    with package.extractfile(member) as data:
                        compare(member.name, data)
                elif not member.isdir():
                    raise ValueError("unexpected nonregular Go archive entry")
    if len(members) < 1000:
        raise ValueError("incomplete Go distribution")
    # Extra files can affect Go's build/test tool selection too. In particular,
    # a reconstructed IDE SDK may add test2json to an otherwise original SDK.
    # This verifier accepts the unmodified archive closure only.
    entries = list(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("Go distribution contains a symlink")
    if {path for path in entries if path.is_file()} != members:
        raise ValueError("Go distribution contains unexpected files")
    return len(members)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go-root", type=Path, required=True)
    parser.add_argument("--go-archive", type=Path, required=True)
    parser.add_argument("--go-archive-sha256", required=True)
    parser.add_argument("--module-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new owned evidence directory")
    args = parser.parse_args()
    go_root, module_cache = args.go_root.resolve(strict=True), args.module_cache.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    suffix = ".exe" if sys.platform == "win32" else ""
    go = go_root/"bin"/("go"+suffix)
    if not go.is_file():
        raise ValueError("--go-root must contain an existing Go distribution; no downloads")
    go_archive = args.go_archive.resolve(strict=True)
    go_members = authenticate_go(go_root, go_archive, args.go_archive_sha256)
    source_before = inventory(SOURCE)
    cache = output/"cache/modules"
    module_dir = module_cache/f"{MODULE}@{VERSION}"
    shutil.copytree(module_dir, cache/f"{MODULE}@{VERSION}")
    downloads = module_cache/"cache/download"/MODULE/"@v"
    copied = cache/"cache/download"/MODULE/"@v"
    copied.mkdir(parents=True)
    for ext in ("mod", "info", "zip", "ziphash"):
        shutil.copyfile(downloads/f"{VERSION}.{ext}", copied/f"{VERSION}.{ext}")
    if (copied/f"{VERSION}.ziphash").read_text(encoding="utf-8").strip() != SUM:
        raise ValueError("cached x/sys hash does not match pinned go.sum")
    env = dict(os.environ, GOROOT=str(go_root), GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local",
               GOTELEMETRY="off", GOWORK="off", GOFLAGS="-mod=readonly", GOENV="off",
               GOCACHE=str(output/"cache/build"), GOMODCACHE=str(cache), CGO_ENABLED="0")
    # An ambient GOOS/GOARCH must not accidentally turn observed host tests into
    # a cross-build. Cross targets below are explicit and never executed.
    env.pop("GOOS", None); env.pop("GOARCH", None)
    commands: list[dict] = []

    def run(argv: list[str], name: str, extra: dict | None = None, timeout: int = 180) -> str:
        command_env = dict(env, **(extra or {}))
        completed = subprocess.run(argv, cwd=SOURCE, env=command_env, capture_output=True, timeout=timeout)
        (output/f"{name}.stdout").write_bytes(completed.stdout)
        (output/f"{name}.stderr").write_bytes(completed.stderr)
        commands.append({"name": name, "argv": argv, "exit": completed.returncode,
                         "stdoutSha256": hashlib.sha256(completed.stdout).hexdigest(),
                         "stderrSha256": hashlib.sha256(completed.stderr).hexdigest()})
        if completed.returncode:
            raise RuntimeError(f"{name} failed: {completed.stderr.decode('utf-8', errors='replace')[-4000:]}")
        return completed.stdout.decode("utf-8")

    run([sys.executable, str(SOURCE/"verify_test.py")], "verifier-controls")
    version = run([str(go), "version"], "go-version").strip()
    run([str(go), "mod", "verify"], "module-verify")
    run([str(go), "test", "-count=1", "./..."], "go-unit")
    run([str(go), "vet", "./..."], "go-vet")
    if sys.platform == "darwin":
        run([str(go), "test", "-race", "-count=1", "./..."], "go-race", {"CGO_ENABLED": "1"})
    guardian, child = output/("guardian"+suffix), output/("tiny-child"+suffix)
    for package, dest, name in ((".", guardian, "guardian-host"), ("./cmd/tiny-child", child, "child-host")):
        run([str(go), "build", "-trimpath", "-buildvcs=false", "-o", str(dest), package], name)
    run([sys.executable, "-W", "error::ResourceWarning", str(SOURCE/"integration_test.py")], "owned-integration",
        {"OPC_GUARDIAN_BINARY": str(guardian), "OPC_GUARDIAN_CHILD": str(child)}, timeout=120)
    binaries = {guardian.name: sha(guardian), child.name: sha(child)}
    if sys.platform != "win32":
        win = {"GOOS": "windows", "GOARCH": "amd64", "CGO_ENABLED": "0"}
        for package, dest, name in ((".", output/"guardian-windows-amd64.exe", "windows-guardian-cross"),
                                    ("./cmd/tiny-child", output/"tiny-child-windows-amd64.exe", "windows-child-cross")):
            run([str(go), "build", "-trimpath", "-buildvcs=false", "-o", str(dest), package], name, win)
            binaries[dest.name] = sha(dest)
        run([str(go), "test", "-c", "-o", str(output/"guardian-windows-tests.exe"), "."], "windows-tests-cross", win)
        binaries["guardian-windows-tests.exe"] = sha(output/"guardian-windows-tests.exe")
    source_after = inventory(SOURCE)
    if source_before != source_after:
        raise RuntimeError("prototype source changed during verification")
    receipt = {"schemaVersion": 1, "prototypeOnly": True, "host": platform.platform(),
               "hostIntegrationExecuted": True, "windowsRuntimeExecuted": sys.platform == "win32",
               "ideLaunched": False, "nodeLaunched": False, "externalNetwork": False,
               "toolchain": {"version": version, "goSha256": sha(go), "licenseSha256": sha(go_root/"LICENSE"),
                             "archiveSha256": args.go_archive_sha256, "archiveMembersMatched": go_members},
               "xSys": {"version": VERSION, "sum": SUM, "licenseSha256": sha(module_dir/"LICENSE")},
               "sources": source_before, "binaries": binaries, "commands": commands}
    (output/"receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"receipt": str(output/"receipt.json"), "binaries": binaries}, indent=2))


if __name__ == "__main__":
    main()
