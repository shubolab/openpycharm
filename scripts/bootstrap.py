#!/usr/bin/env python3
"""Authenticate and unpack the pinned open-source PyCharm distribution.

Installed PyCharm is a read-only reference, never a distribution input. Cached
SDKs are reused only after checking their receipt, product identity and complete
tree digest. This script writes only inside its selected cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PIN_PATH = ROOT / "product/platform.lock.json"
RESERVE_BYTES = 20 * 1024**3
RECEIPT_NAME = ".openpycharm-platform.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_space(path: Path, additional_bytes: int) -> None:
    while not path.exists():
        path = path.parent
    free = shutil.disk_usage(path).free
    if free - additional_bytes < RESERVE_BYTES:
        raise ValueError("Bootstrap requires at least 20 GiB free after extraction")


def tree_digest(root: Path) -> str:
    """Bind all files, executable permissions and symlink targets, without following links."""
    digest = hashlib.sha256()
    for parent, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        for name in sorted(directories + files):
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                record = [relative, "link", os.readlink(path)]
            elif stat.S_ISREG(mode):
                record = [relative, "file", stat.S_IMODE(mode), sha256(path)]
            elif stat.S_ISDIR(mode):
                record = [relative, "directory", stat.S_IMODE(mode)]
            else:
                raise ValueError(f"Unexpected special file in SDK: {relative}")
            digest.update(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def product_info(sdk: Path, target: str) -> Path:
    return sdk / ("Contents/Resources/product-info.json" if target == "macos-arm64" else "product-info.json")


def validate_identity(sdk: Path, pin: dict, target: str) -> dict:
    info_path = product_info(sdk, target)
    if info_path.is_symlink() or not info_path.is_file():
        raise ValueError("Pinned SDK has no regular product-info.json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    for key in ("productCode", "version", "buildNumber"):
        if info.get(key) != pin[key]:
            raise ValueError(f"Wrong OSS SDK {key}: {info.get(key)!r}; expected {pin[key]!r}")
    expected_os, expected_arch = ("macOS", "aarch64") if target == "macos-arm64" else ("Windows", "amd64")
    launches = info.get("launch", [])
    if not any(item.get("os") == expected_os and item.get("arch") == expected_arch for item in launches):
        raise ValueError("SDK launch architecture does not match the selected target")
    if "PythonCore" not in info.get("bundledPlugins", []):
        raise ValueError("The OSS Python language plugin is missing")
    if "Pythonid" in info.get("bundledPlugins", []):
        raise ValueError("Commercial Python plugin cannot be a product input")
    return info


def validate_cached(destination: Path, pin: dict, target: str) -> Path:
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Cached SDK root must be a regular directory")
    receipt_path = destination / RECEIPT_NAME
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("Existing SDK lacks a bootstrap receipt; choose a new cache")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected = {"schema": 1, "target": target, "pinSha256": sha256(PIN_PATH), "archiveSha256": pin["targets"][target]["sha256"]}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("Cached SDK receipt differs from the authenticated pin")
    sdk = destination / ("PyCharm.app" if target == "macos-arm64" else "pycharm")
    if sdk.is_symlink():
        raise ValueError("Cached SDK cannot be a symlink")
    validate_identity(sdk, pin, target)
    if receipt.get("treeSha256") != tree_digest(sdk):
        raise ValueError("Cached SDK files have changed; choose a new cache")
    return sdk


def authenticate_archive(archive: Path, asset: dict) -> None:
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("Installer archive must be a regular file")
    if archive.stat().st_size != asset["size"] or sha256(archive) != asset["sha256"]:
        raise ValueError(f"Installer size or SHA-256 mismatch: {archive}")


def acquire_archive(cache: Path, asset: dict) -> Path:
    downloads = cache / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / asset["name"]
    if archive.exists():
        try:
            authenticate_archive(archive, asset)
            return archive
        except ValueError:
            # Never truncate a suspicious completed file. Partial curl output
            # belongs at .partial and is authenticated before atomic rename.
            raise ValueError(f"Existing archive failed authentication: {archive}") from None
    partial = archive.with_name(archive.name + ".partial")
    if partial.is_symlink():
        raise ValueError("Download partial must not be a symlink")
    subprocess.run([
        "curl", "--fail", "--location", "--retry", "3", "--connect-timeout", "15",
        "--max-time", "1800", "--continue-at", "-", "--output", str(partial), asset["url"],
    ], check=True)
    authenticate_archive(partial, asset)
    partial.replace(archive)
    return archive


def extract_windows(archive: Path, staging: Path) -> Path:
    unpacked = staging / "unpacked"
    unpacked.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if sum(item.file_size for item in members) > 10 * 1024**3:
            raise ValueError("SDK zip exceeds the extraction budget")
        for item in members:
            name = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (name.is_absolute() or ".." in name.parts or "\\" in item.filename
                    or ":" in item.filename or stat.S_ISLNK(mode)):
                raise ValueError(f"Unsafe SDK zip member: {item.filename}")
        bundle.extractall(unpacked)
    candidates = [path.parent for path in unpacked.rglob("product-info.json") if (path.parent / "bin").is_dir()]
    if len(candidates) != 1:
        raise ValueError("SDK zip must contain one product root")
    sdk = staging / "pycharm"
    candidates[0].rename(sdk)
    shutil.rmtree(unpacked)
    return sdk


def extract_mac(archive: Path, staging: Path) -> Path:
    if platform.system() != "Darwin":
        raise ValueError("DMG extraction requires macOS")
    mountpoint = Path(tempfile.mkdtemp(prefix="openpycharm-mount-", dir=staging.parent))
    mounted = False
    try:
        subprocess.run(["hdiutil", "attach", str(archive), "-readonly", "-nobrowse", "-mountpoint", str(mountpoint), "-quiet"], check=True)
        mounted = True
        apps = list(mountpoint.glob("*.app"))
        if len(apps) != 1 or apps[0].is_symlink():
            raise ValueError("Pinned DMG must contain one application bundle")
        sdk = staging / "PyCharm.app"
        subprocess.run(["ditto", str(apps[0]), str(sdk)], check=True)
        return sdk
    finally:
        if mounted:
            subprocess.run(["hdiutil", "detach", str(mountpoint), "-quiet"], check=True)
        mountpoint.rmdir()


def bootstrap(target: str, cache: Path, archive: Path | None = None) -> Path:
    pin = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    asset = pin["targets"][target]
    cache = cache.resolve()
    destination = cache / "platform" / f"pycharm-{pin['version']}-{target}"
    if destination.exists() or destination.is_symlink():
        return validate_cached(destination, pin, target)
    check_space(cache, asset["size"] + 6 * 1024**3)
    archive = archive.resolve() if archive is not None else acquire_archive(cache, asset)
    authenticate_archive(archive, asset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=destination.name + ".", dir=destination.parent))
    try:
        sdk = extract_mac(archive, staging) if target == "macos-arm64" else extract_windows(archive, staging)
        validate_identity(sdk, pin, target)
        receipt = {
            "schema": 1, "target": target, "pinSha256": sha256(PIN_PATH),
            "archiveSha256": asset["sha256"], "treeSha256": tree_digest(sdk),
            "source": pin["source"], "sourceCommit": pin["sourceCommit"],
            "productCode": pin["productCode"], "version": pin["version"], "buildNumber": pin["buildNumber"],
        }
        (staging / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        staging.rename(destination)
        return destination / sdk.name
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("macos-arm64", "windows-x64"), required=True)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded pinned installer")
    parser.add_argument("--cache", type=Path, default=ROOT / ".tools", help="SDK/download cache root")
    args = parser.parse_args()
    try:
        print(bootstrap(args.target, args.cache, args.archive))
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Bootstrap failed: {error}\n")


if __name__ == "__main__":
    main()
