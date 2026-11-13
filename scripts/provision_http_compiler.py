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


def receipt_url(url: str) -> str:
    """Retain endpoint identity without temporary GitHub signed query values."""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(query="", fragment=""))


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
        raise ValueError(f"Maven compiler endpoint rejected: {receipt_url(candidate)!r}; expected pinned HTTPS origin/path {pinned!r}")


def release_redirect(item: dict) -> dict | None:
    route = item.get("releaseRedirect")
    if route is None:
        return None
    if (not isinstance(route, dict) or (item.get("group"), item.get("artifact"), item.get("version")) !=
            ("org.jetbrains.kotlin", "kotlin-compiler-embeddable", "2.3.21")):
        raise ValueError("Only the verified Kotlin compiler artifact has a release redirect route")
    expected = f"https://github.com/JetBrains/kotlin/releases/download/v2.3.21/{item['name']}"
    cdn = urllib.parse.urlsplit(route.get("assetCdnUrl", ""))
    if (route.get("repository") != "JetBrains/kotlin" or route.get("tag") != "v2.3.21"
            or type(route.get("assetId")) is not int or route["assetId"] != 598615460
            or route.get("metadataUrl") != "https://api.github.com/repos/JetBrains/kotlin/releases/assets/598615460"
            or route.get("url") != expected or route.get("assetSize") != item["size"]
            or route.get("assetSha256") != item["sha256"]
            or cdn.scheme != "https" or cdn.netloc != "release-assets.githubusercontent.com"
            or cdn.path != "/github-production-release-asset/3432266/8c5a5b7a-09b2-47cf-9427-cdcb63c3596b"
            or cdn.query or cdn.fragment):
        raise ValueError("Kotlin compiler release route differs from its verified asset identity")
    return route


def endpoint_role(candidate: str, pinned: str, route: dict | None) -> str:
    try:
        validate_endpoint(candidate, pinned)
        return "maven"
    except ValueError:
        pass
    if route is not None:
        try:
            validate_endpoint(candidate, route["url"])
            return "release"
        except ValueError:
            pass
        parts, cdn = urllib.parse.urlsplit(candidate), urllib.parse.urlsplit(route["assetCdnUrl"])
        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        allowed_keys = {"sp", "sv", "sr", "spr", "se", "rscd", "rsct", "skt", "ske", "sks", "skv",
                        "skoid", "sktid", "sig", "jwt", "response-content-disposition", "response-content-type"}
        disposition = "attachment; filename=kotlin-compiler-embeddable-2.3.21.jar"
        if (parts.scheme == "https" and parts.hostname == cdn.hostname and parts.port in {None, 443}
                and parts.username is None and parts.password is None and parts.path == cdn.path and not parts.fragment
                and len(parts.query) <= 8192 and set(query).issubset(allowed_keys) and all(len(value) == 1 for value in query.values())
                and all(query.get(key) == [value] for key, value in (("sp", "r"), ("spr", "https"), ("sr", "b")))
                and bool(query.get("sig", [""])[0])
                and all(key not in query or query[key] == [value] for key, value in
                        (("rscd", disposition), ("response-content-disposition", disposition),
                         ("rsct", "application/octet-stream"), ("response-content-type", "application/octet-stream")))):
            return "cdn"
    raise ValueError(f"Compiler endpoint is outside this artifact's verified route: {receipt_url(candidate)!r}")


class PinnedArtifactRedirect(urllib.request.HTTPRedirectHandler):
    """Check every redirect before urllib opens its destination."""
    max_redirections = 3
    max_repeats = 1

    def __init__(self, pinned: str, route: dict | None = None):
        self.pinned = pinned
        self.route = route
        self.hops = []

    def redirect_request(self, request, response, code, message, headers, newurl):
        try:
            source = endpoint_role(request.full_url, self.pinned, self.route)
            target = endpoint_role(newurl, self.pinned, self.route)
            if (source, target) not in {("maven", "maven"), ("maven", "release"), ("release", "release"), ("release", "cdn")}:
                raise ValueError("Redirect does not follow Maven to the pinned primary release and asset CDN")
        except ValueError as error:
            response.close()
            raise ValueError(f"Maven compiler redirect rejected before following HTTP {code}: "
                             f"{receipt_url(request.full_url)!r} -> {receipt_url(newurl)!r}; {error}") from error
        hop = {"status": code, "source": receipt_url(request.full_url), "destination": receipt_url(newurl)}
        if urllib.parse.urlsplit(newurl).query:
            hop["signedQueryOmitted"] = True
        self.hops.append(hop)
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
    release_redirect(item)
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
    route = release_redirect(item)
    redirects = PinnedArtifactRedirect(url, route)
    opener = urllib.request.build_opener(redirects)
    # An incomplete/tampered response never replaces the authenticated cache.
    with tempfile.TemporaryDirectory(prefix="download-", dir=destination.parent) as directory:
        candidate = Path(directory) / item["name"]
        with opener.open(request, timeout=30) as response, candidate.open("wb") as output:
            final_url = response.geturl()
            endpoint_role(final_url, url, route)
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
    result = {"name": item["name"], "requestedUrl": url, "finalUrl": receipt_url(final_url), "redirects": redirects.hops}
    if urllib.parse.urlsplit(final_url).query:
        result["signedQueryOmitted"] = True
    return result


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
