#!/usr/bin/env python3
"""Explicitly provision SHA-256 pinned JDBC binaries and LGPL matching source."""
import argparse
import json
from pathlib import Path
import re
import tempfile
import time
import urllib.request

from bootstrap import check_space, sha256
from platform_layout import cache_lock

ROOT = Path(__file__).resolve().parent.parent
PIN = ROOT / "plugins/database/drivers.lock.json"
CENTRAL = "https://repo.maven.apache.org/maven2/"


def artifact_url(item):
    if item.get("role") not in {"source", "driver"}:
        raise ValueError("Invalid JDBC artifact role")
    for key in ("group", "artifact", "version"):
        if not isinstance(item.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", item[key]):
            raise ValueError("Invalid JDBC coordinate")
    suffix = "-sources" if item["role"] == "source" else ""
    name = f"{item['artifact']}-{item['version']}{suffix}.jar"
    expected = CENTRAL + "/".join((item["group"].replace(".", "/"), item["artifact"], item["version"], name))
    if item["name"] != name or item["url"] != expected or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) or type(item["size"]) is not int or not 0 < item["size"] < 32 * 1024**2:
        raise ValueError("Invalid JDBC artifact pin")
    return expected


def authenticate(path, item):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
        raise ValueError("JDBC cache hash/size/type mismatch: " + item["name"])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        response.close()
        raise ValueError("JDBC provisioning does not follow redirects away from its pinned Maven Central artifact")


def provision(cache):
    cache = cache.absolute()
    if not cache.is_relative_to(ROOT / ".tools"):
        raise ValueError("Provision only into this checkout's owned .tools directory")
    for path in [cache, *cache.parents]:
        if path.is_symlink():
            raise ValueError("JDBC cache ancestors cannot be symlinks")
        if path == ROOT:
            break
    items = json.loads(PIN.read_text())["artifacts"]
    for item in items:
        artifact_url(item)
    check_space(cache, sum(item["size"] for item in items))
    cache.mkdir(parents=True, exist_ok=True)
    with cache_lock(cache / "provision.lock"):
        for item in items:
            destination = cache / item["name"]
            if destination.exists() or destination.is_symlink():
                authenticate(destination, item)
                continue
            deadline = time.monotonic() + 120
            with tempfile.TemporaryDirectory(prefix="fetch-", dir=cache) as directory:
                candidate = Path(directory) / item["name"]
                request = urllib.request.Request(artifact_url(item), headers={"User-Agent": "OpenPyCharm-pinned-JDBC/1"})
                with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response, candidate.open("wb") as output:
                    count = 0
                    while True:
                        if time.monotonic() > deadline:
                            raise ValueError("JDBC download exceeded deadline")
                        block = response.read(min(1024**2, item["size"] + 1 - count))
                        if not block:
                            break
                        count += len(block)
                        if count > item["size"]:
                            raise ValueError("JDBC download exceeded pinned size")
                        output.write(block)
                authenticate(candidate, item)
                candidate.replace(destination)
    return {"status": "pass", "artifacts": len(items), "cache": str(cache)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".tools/jdbc")
    args = parser.parse_args()
    try:
        print(json.dumps(provision(args.cache), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")
