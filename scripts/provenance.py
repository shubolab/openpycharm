"""Bind an assembled product to the exact source inputs used to create it.

This inventory includes packaging/repair scripts, product resources and pins,
and the build requirements and notices. It never follows source symlinks.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat

from bootstrap import ROOT, sha256


def source_inputs(root: Path = ROOT) -> dict[str, str]:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source root must be a regular directory")
    root = root.resolve()
    paths = []
    for name in ("scripts", "product"):
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
