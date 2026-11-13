"""Bind an assembled product to the exact source inputs used to create it.

This inventory includes packaging/repair scripts, product/plugin sources,
resources and pins, and the build requirements and notices. It never follows
source symlinks.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
import stat

from bootstrap import ROOT, sha256


def source_inputs(root: Path = ROOT) -> dict[str, str]:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source root must be a regular directory")
    root = root.resolve()
    paths = []
    for name in ("scripts", "product", "plugins"):
        directory = root / name
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Source {name} must be a regular directory")
        for parent, directories, files in os.walk(directory, followlinks=False):
            directories[:] = sorted(item for item in directories if item != "__pycache__")
            for item in directories:
                child = Path(parent) / item
                if child.is_symlink() or not stat.S_ISDIR(child.lstat().st_mode):
                    raise ValueError(f"Source symlink or special directory is not allowed: {child.relative_to(root)}")
            for item in sorted(files):
                if item == "__pycache__":
                    continue
                path = Path(parent) / item
                if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                    raise ValueError(f"Source symlink or special file is not allowed: {path.relative_to(root)}")
                paths.append(path)
    for name in ("requirements-build.txt", "LICENSE", "NOTICE"):
        path = root / name
        if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError(f"Required source input must be a regular file: {name}")
        paths.append(path)
    return {path.relative_to(root).as_posix(): sha256(path) for path in sorted(paths)}


def verify_source_inputs(manifest: dict, root: Path = ROOT) -> None:
    expected = manifest.get("sourceInputs") if isinstance(manifest, dict) else None
    if not isinstance(expected, dict) or not expected or any(
        not isinstance(name, str) or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for name, digest in expected.items()
    ):
        raise ValueError("Product manifest must contain a valid sourceInputs inventory")
    current = source_inputs(root)
    added = sorted(current.keys() - expected.keys())
    removed = sorted(expected.keys() - current.keys())
    changed = sorted(name for name in current.keys() & expected.keys() if current[name] != expected[name])
    if added or removed or changed:
        details = []
        for label, paths in (("added", added), ("removed", removed), ("changed", changed)):
            if paths:
                details.append(f"{label}: {', '.join(paths[:20])}" + (" …" if len(paths) > 20 else ""))
        raise ValueError("Product source inputs are stale; rebuild the product (" + "; ".join(details) + ")")


def verify_product_plugins(manifest: dict, contents: Path) -> list[dict]:
    """Authenticate declared plugin bytes before startup or installer creation."""
    entries = manifest.get("plugins", [])
    if not isinstance(entries, list):
        raise ValueError("Product plugins must be a list")
    seen_ids, seen_jars, verified = set(), set(), []
    for entry in entries:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) for key in ("id", "name", "version", "path", "jar", "jarSha256")):
            raise ValueError("Product plugin receipt is incomplete")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", entry["id"]) is None or re.fullmatch(r"[a-f0-9]{64}", entry["jarSha256"]) is None:
            raise ValueError("Invalid product plugin identity or digest")
        paths = {}
        for key in ("path", "jar"):
            raw, path = entry[key], PurePosixPath(entry[key])
            if (not raw or not path.parts or path.is_absolute() or path.as_posix() != raw or any(char in raw for char in "\\:\0")
                    or any(part in {".", ".."} for part in path.parts) or path.parts[0] != "third-party-plugins"):
                raise ValueError("Product plugin paths must stay below third-party-plugins")
            paths[key] = path
        if not paths["jar"].is_relative_to(paths["path"]) or paths["jar"].suffix != ".jar":
            raise ValueError("Product plugin JAR must belong to its declared plugin directory")
        if entry["id"] in seen_ids or entry["jar"] in seen_jars:
            raise ValueError("Duplicate product plugin receipt")
        seen_ids.add(entry["id"])
        seen_jars.add(entry["jar"])
        current = Path(contents)
        for index, part in enumerate(paths["jar"].parts):
            current /= part
            if current.is_symlink():
                raise ValueError("Product plugin paths cannot contain symlinks")
            mode = current.stat().st_mode if current.exists() else 0
            if index < len(paths["jar"].parts) - 1 and not stat.S_ISDIR(mode):
                raise ValueError("Product plugin parent must be a regular directory")
        if not stat.S_ISREG(mode) or current.stat().st_size > 128 * 1024**2:
            raise ValueError("Product plugin JAR must be a bounded regular file")
        if sha256(current) != entry["jarSha256"]:
            raise ValueError("Product plugin JAR digest differs from its build receipt")
        verify_plugin_payloads(entry, contents)
        verified.append({key: entry[key] for key in ("id", "version", "jar", "jarSha256")})
    return verified


def verify_plugin_payloads(entry: dict, contents: Path) -> None:
    """Bind separate driver binaries and corresponding source to the same receipt."""
    files = entry.get("files")
    if files is None:
        if entry["id"] == "dev.openpycharm.database":
            raise ValueError("Database plugin requires its complete driver/source payload receipt")
        return
    if not isinstance(files, dict) or not 1 <= len(files) <= 32:
        raise ValueError("Plugin payload receipt must be a bounded file map")
    directory = Path(contents) / entry["path"]
    primary = PurePosixPath(entry["jar"]).relative_to(PurePosixPath(entry["path"])).as_posix()
    if files.get(primary) != entry["jarSha256"]:
        raise ValueError("Plugin payload receipt must include the exact primary JAR")
    build_files = entry.get("build", {}).get("files") if isinstance(entry.get("build"), dict) else None
    if entry["id"] == "dev.openpycharm.database" and (files != build_files or len(files) != 5):
        raise ValueError("Database plugin driver/source files differ from its authenticated build receipt")
    for name, digest in files.items():
        if not isinstance(name, str) or not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("Invalid plugin payload name or digest")
        relative = PurePosixPath(name)
        if (not name or not relative.parts or relative.is_absolute() or relative.as_posix() != name
                or any(c in name for c in "\\:\0") or any(p in {".", ".."} for p in relative.parts)
                or relative.parts[0] not in {"lib", "legal"}):
            raise ValueError("Plugin payload paths must stay below lib/legal")
        current = directory
        for index, part in enumerate(relative.parts):
            current /= part
            if current.is_symlink():
                raise ValueError("Plugin payload paths cannot contain symlinks")
            mode = current.stat().st_mode if current.exists() else 0
            if index < len(relative.parts) - 1 and not stat.S_ISDIR(mode):
                raise ValueError("Plugin payload parent must be a regular directory")
        if not stat.S_ISREG(mode) or current.stat().st_size > 128 * 1024**2:
            raise ValueError("Plugin payload must be a bounded regular file")
        if sha256(current) != digest:
            raise ValueError("Plugin payload digest differs from its build receipt")
    actual = set()
    for parent, directories, names in os.walk(directory, followlinks=False):
        for name in directories + names:
            path = Path(parent) / name
            if path.is_symlink():
                raise ValueError("Plugin payload directories cannot contain symlinks")
            if name in names:
                actual.add(path.relative_to(directory).as_posix())
    if actual != set(files):
        raise ValueError("Plugin directory contains missing or unreceipted payload files")
