#!/usr/bin/env python3
"""Fetch the seven hash-pinned compiler artifacts from Maven Central.

This explicit provisioning step writes only to this checkout's owned .tools
cache. The compiler and product builders remain offline and fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request

from platform_layout import cache_lock

ROOT = Path(__file__).resolve().parent.parent
PIN = ROOT / "plugins/http-client/compiler.lock.json"
CENTRAL = "https://repo.maven.apache.org/maven2/"
RESERVE = 20 * 1024**3


def validate_endpoint(candidate: str, pinned: str) -> None:
    """Allow only the pinned artifact at the authenticated primary HTTPS origin.

    URL spelling may normalize host case or the default HTTPS port. Artifact
    paths and origins must not change; no alternate CDN is implicitly trusted.
    """
    try:
        actual, expected = urllib.parse.urlsplit(candidate), urllib.parse.urlsplit(pinned)
        allowed = (actual.scheme == "https" and actual.hostname == expected.hostname
                   and actual.port in {None, 443} and actual.username is None and actual.password is None
                   and actual.path == expected.path and not actual.query and not actual.fragment)
    except (TypeError, ValueError):
        allowed = False
    if not allowed:
        raise ValueError(f"Maven compiler endpoint rejected: {candidate!r}; expected pinned HTTPS origin/path {pinned!r}")


class PinnedArtifactRedirect(urllib.request.HTTPRedirectHandler):
    """Check every redirect before urllib opens its destination."""
    max_redirections = 3
    max_repeats = 1

    def __init__(self, pinned: str):
        self.pinned = pinned
        self.hops = []

    def redirect_request(self, request, response, code, message, headers, newurl):
        try:
            validate_endpoint(newurl, self.pinned)
        except ValueError as error:
            response.close()
            raise ValueError(f"Maven compiler redirect rejected before following HTTP {code}: "
                             f"{request.full_url!r} -> {newurl!r}; no alternate host/path is authorized") from error
        self.hops.append({"status": code, "source": request.full_url, "destination": newurl})
        return super().redirect_request(request, response, code, message, headers, newurl)


def artifact_url(item: dict) -> str:
    for key in ("group", "artifact", "version"):
        if not isinstance(item.get(key), str) or re.fullmatch(r"[A-Za-z0-9_.-]+", item[key]) is None:
            raise ValueError("Invalid compiler coordinate")
    name = f"{item['artifact']}-{item['version']}.jar"
    if item.get("name") != name or type(item.get("size")) is not int or not 0 < item["size"] <= 128 * 1024**2:
        raise ValueError("Invalid compiler artifact name or size")
    if not isinstance(item.get("sha256"), str) or re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) is None:
        raise ValueError("Invalid compiler artifact SHA-256")
    url = CENTRAL + "/".join((item["group"].replace(".", "/"), item["artifact"], item["version"], name))
    if item.get("url") != url:
        raise ValueError("Compiler artifact must use its pinned Maven Central URL")
    return url


def authenticate(path: Path, item: dict) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != item["size"]:
        raise ValueError(f"Compiler cache size/type mismatch: {path.name}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _digest(stream)
    if digest != item["sha256"]:
        raise ValueError(f"Compiler cache SHA-256 mismatch: {path.name}")


def _digest(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def download(item: dict, destination: Path) -> dict:
    url = artifact_url(item)
    deadline = time.monotonic() + 180
    request = urllib.request.Request(url, headers={"User-Agent": "OpenPyCharm-pinned-build/1"})
    redirects = PinnedArtifactRedirect(url)
    opener = urllib.request.build_opener(redirects)
    # An incomplete/tampered response never replaces the authenticated cache.
    with tempfile.TemporaryDirectory(prefix="download-", dir=destination.parent) as directory:
        candidate = Path(directory) / item["name"]
        with opener.open(request, timeout=30) as response, candidate.open("wb") as output:
            final_url = response.geturl()
            validate_endpoint(final_url, url)
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != item["size"]:
                raise ValueError("Compiler download Content-Length differs from pin")
            received = 0
            while True:
                if time.monotonic() > deadline:
                    raise ValueError("Compiler download exceeded its 180-second deadline")
                block = response.read(min(1024 * 1024, item["size"] + 1 - received))
                if not block:
                    break
                received += len(block)
                if received > item["size"]:
                    raise ValueError("Compiler download exceeds pinned size")
                output.write(block)
        authenticate(candidate, item)
        candidate.replace(destination)
    return {"name": item["name"], "requestedUrl": url, "finalUrl": final_url, "redirects": redirects.hops}


def provision(cache: Path = ROOT / ".tools/kotlin") -> dict:
    cache = Path(cache)
    if cache.is_symlink() or not cache.resolve().is_relative_to((ROOT / ".tools").resolve()):
        raise ValueError("Compiler cache must be owned below this checkout's .tools")
    # Reject symlink components before creating or opening any cache files.
    relative = cache.absolute().relative_to(ROOT.absolute())
    current = ROOT
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Compiler cache directories cannot be symlinks")
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    items = pin["artifacts"]
    if len(items) != 7 or len({item["name"] for item in items}) != 7:
        raise ValueError("Expected seven distinct pinned compiler artifacts")
    for item in items:
        artifact_url(item)
    existing = cache
    while not existing.exists():
        existing = existing.parent
    if shutil.disk_usage(existing).free < RESERVE + sum(item["size"] for item in items):
        raise ValueError("Compiler provisioning must retain 20 GiB free")
    cache.mkdir(parents=True, exist_ok=True)
    if (cache / "provision.lock").is_symlink():
        raise ValueError("Compiler cache lock cannot be a symlink")
    downloads = []
    with cache_lock(cache / "provision.lock"):
        for item in items:
            directory = cache / item["sha256"]
            if directory.is_symlink():
                raise ValueError("Compiler cache directories cannot be symlinks")
            directory.mkdir(exist_ok=True)
            destination = directory / item["name"]
            if destination.exists() or destination.is_symlink():
                authenticate(destination, item)
            else:
                downloads.append(download(item, destination))
    return {"schema": 1, "cache": str(cache.resolve()), "source": CENTRAL,
            "downloads": downloads,
            "artifacts": [{"name": item["name"], "sha256": item["sha256"], "size": item["size"]} for item in items]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".tools/kotlin")
    args = parser.parse_args()
    try:
        print(json.dumps(provision(args.cache), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
