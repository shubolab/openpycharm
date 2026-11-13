#!/usr/bin/env python3
"""Verify two official CI installers, then optionally attach them to an existing draft.

Never executes artifact code, creates a release/tag, overwrites an asset, or
publishes. Validation patterns also used by shubolab/opengoland's
scripts/publish_tested_installers.py are adapted here for OpenPyCharm receipts.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import threading
from urllib.parse import quote
import zipfile

REPOSITORY = "shubolab/openpycharm"
WORKFLOW_PATH = ".github/workflows/build.yml"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"v([0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)")
MAX_ARCHIVE = 2 * 1024**3
MAX_INSTALLER = 1536 * 1024**2
MAX_JSON = 4 * 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def decode_json(data: bytes):
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object)


@dataclass(frozen=True)
class ArtifactSpec:
    target: str
    artifact_id: int
    installer_sha256: str

    def __post_init__(self):
        require(self.target in {"macos-arm64", "windows-x64"}, "Unsupported installer target")

    def name(self, version):
        suffix = "macos-arm64.dmg" if self.target == "macos-arm64" else "windows-x64-setup.exe"
        return f"OpenPyCharm-{version}-{suffix}"


@dataclass(frozen=True)
class TransferInputs:
    tag: str
    source_commit: str
    documentation_commit: str
    run_id: int
    mac_artifact_id: int
    mac_sha256: str
    windows_artifact_id: int
    windows_sha256: str

    @property
    def version(self):
        require(isinstance(self.tag, str), "Tag must be text")
        match = VERSION.fullmatch(self.tag)
        require(match is not None, "Tag must be v followed by an installer version")
        return match.group(1)

    @property
    def specs(self):
        return (ArtifactSpec("macos-arm64", self.mac_artifact_id, self.mac_sha256),
                ArtifactSpec("windows-x64", self.windows_artifact_id, self.windows_sha256))


def validate_inputs(value: TransferInputs):
    value.version
    require(all(isinstance(commit, str) and HEX40.fullmatch(commit) for commit in
                (value.source_commit, value.documentation_commit)),
            "Full lowercase production and release-documentation commit SHAs are required")
    require(all(type(number) is int and number > 0 for number in
                (value.run_id, value.mac_artifact_id, value.windows_artifact_id)), "Positive integer IDs are required")
    require(value.mac_artifact_id != value.windows_artifact_id, "Two distinct platform artifact IDs are required")
    require(all(isinstance(spec.installer_sha256, str) and HEX64.fullmatch(spec.installer_sha256) for spec in value.specs),
            "Exact lowercase installer SHA-256 values are required")


def validate_context(value, repository, workflow, run, jobs):
    require(repository.get("full_name") == REPOSITORY and type(repository.get("id")) is int, "Wrong repository")
    require(workflow.get("path") == WORKFLOW_PATH and workflow.get("name") == "Build native installers"
            and workflow.get("state") == "active", "Wrong official build workflow")
    require(run.get("id") == value.run_id and run.get("workflow_id") == workflow.get("id")
            and run.get("path") == WORKFLOW_PATH and run.get("head_sha") == value.source_commit,
            "Build run/workflow/source mismatch")
    require(all(run.get(key, {}).get("id") == repository["id"] and
                run.get(key, {}).get("full_name") == REPOSITORY for key in ("repository", "head_repository")),
            "Fork or foreign build runs are not accepted")
    require(run.get("event") in {"push", "workflow_dispatch"} and run.get("status") == "completed"
            and run.get("conclusion") == "success", "A completed successful own-repository build is required")
    require(type(run.get("run_attempt")) is int and run["run_attempt"] > 0, "Missing build attempt")
    for target in ("macos-arm64", "windows-x64"):
        matches = [job for job in jobs if job.get("name") == target]
        require(len(matches) == 1, "Exactly one current job per native target is required")
        job = matches[0]
        require(job.get("run_id") == value.run_id and job.get("head_sha") == value.source_commit
                and job.get("run_attempt", run["run_attempt"]) == run["run_attempt"]
                and job.get("status") == "completed" and job.get("conclusion") == "success", "Native target job did not pass")


def validate_artifact(value, spec, metadata, repository_id):
    require(metadata.get("id") == spec.artifact_id and metadata.get("expired") is False
            and metadata.get("name") == f"OpenPyCharm-{spec.target}-{value.source_commit}", "Artifact identity/expiry mismatch")
    require(type(metadata.get("size_in_bytes")) is int and 0 < metadata["size_in_bytes"] <= MAX_ARCHIVE,
            "Artifact archive exceeds its size bound")
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", metadata.get("digest", "")), "GitHub artifact SHA-256 metadata is required")
    source = metadata.get("workflow_run", {})
    require(source.get("id") == value.run_id and source.get("head_sha") == value.source_commit
            and source.get("repository_id") == repository_id and source.get("head_repository_id") == repository_id,
            "Artifact does not belong to the verified build/source/repository")


def safe_name(name):
    require(isinstance(name, str) and name and not any(c in name for c in "\\:\0\r\n"), "Unsafe archive/source path")
    clean = name[:-1] if name.endswith("/") else name
    path = PurePosixPath(clean)
    require(not path.is_absolute() and path.as_posix() == clean and
            all(part not in {"", ".", ".."} for part in clean.split("/")), "Unsafe archive/source path")
    return path


class SafeZip:
    def __init__(self, path):
        self.archive = zipfile.ZipFile(path)
        self.members = {}
        try:
            items = self.archive.infolist()
            require(len(items) <= 10000 and sum(item.file_size for item in items) <= 3 * 1024**3,
                    "Artifact expands beyond its member/size bounds")
            for item in items:
                safe_name(item.filename)
                require(item.orig_filename == item.filename and item.filename not in self.members, "Duplicate or truncated ZIP member")
                mode = stat.S_IFMT(item.external_attr >> 16)
                require(mode in {0, stat.S_IFREG, stat.S_IFDIR} and not item.flag_bits & 1
                        and item.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, "Unsupported ZIP member type/encoding")
                require(not (mode == stat.S_IFDIR and not item.is_dir()), "Invalid ZIP directory")
                self.members[item.filename] = item
        except Exception:
            self.archive.close()
            raise

    def close(self):
        self.archive.close()

    def read(self, name, limit=MAX_JSON):
        item = self.members.get(name)
        require(item is not None and not item.is_dir() and item.file_size <= limit, "Missing or oversized proof member: " + name)
        with self.archive.open(item) as stream:
            data = stream.read(limit + 1)
        require(len(data) == item.file_size and len(data) <= limit, "Proof size mismatch")
        return data


def git(repo, *args, input=None):
    completed = subprocess.run(["git", *args], cwd=repo, input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    require(completed.returncode == 0, "Required production/documentation Git object is unavailable")
    return completed.stdout


def verify_git_sources(repo, value, capture, target):
    require(isinstance(capture, dict) and 0 < len(capture) <= 2000, "Missing or oversized source inventory")
    for name, digest in capture.items():
        safe_name(name)
        require(isinstance(digest, str) and HEX64.fullmatch(digest), "Invalid source inventory digest")
    require(subprocess.run(["git", "merge-base", "--is-ancestor", value.source_commit, value.documentation_commit],
                           cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60).returncode == 0,
            "Release documentation must descend from the production source")
    trees = []
    for commit in (value.source_commit, value.documentation_commit):
        tree = {}
        for entry in git(repo, "ls-tree", "-rz", commit, "--", "scripts", "product", "plugins", "requirements-build.txt", "LICENSE", "NOTICE").split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            mode, kind, object_id = metadata.decode("ascii").split()
            name = raw_name.decode("utf-8")
            safe_name(name)
            if "__pycache__" in PurePosixPath(name).parts:
                continue
            require(kind == "blob" and mode in {"100644", "100755"}, "Source links/submodules/special objects are not accepted")
            tree[name] = (mode, object_id)
        trees.append(tree)
    require(set(capture) == set(trees[0]) and trees[0] == trees[1], "Source inventory or release-documentation production inputs differ")
    converted = []
    total = 0
    for name, (_, object_id) in trees[0].items():
        size = int(git(repo, "cat-file", "-s", object_id))
        total += size
        require(size <= 8 * 1024**2 and total <= 32 * 1024**2, "Source blob inventory exceeds its bounds")
        data = git(repo, "cat-file", "blob", object_id)
        if hashlib.sha256(data).hexdigest() == capture[name]:
            continue
        require(target == "windows-x64" and b"\0" not in data and b"\r" not in data and
                hashlib.sha256(data.replace(b"\n", b"\r\n")).hexdigest() == capture[name], "Captured source differs from the production Git blob")
        data.decode("utf-8")
        converted.append(name)
    return sorted(converted)


@dataclass(frozen=True)
class VerifiedInstaller:
    target: str
    name: str
    path: Path
    size: int
    sha256: str
    artifact_id: int
    archive_sha256: str
    windows_checkout_conversions: list[str]


def startup_proof(data, value, spec, manifest_sha):
    require(data.get("schema") == 1 and data.get("status") == "passed-startup" and data.get("target") == spec.target
            and data.get("version") == value.version and data.get("productManifestSha256") == manifest_sha,
            "Native startup proof does not bind this product")
    observation = data.get("finalObservation", data.get("observation", {}))
    require(observation.get("errorCount") == 0 and all(observation.get(key) is True for key in
            ("ideStarted", "productIdentity", "vendorIdentity"))
            and all(observation.get("isolatedPaths", {}).get(key) is True for key in ("config", "system", "plugins", "log")),
            "Native startup identity/isolation/error gate failed")


def verify_archive(path, value, spec, metadata, output, source_verifier):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == metadata["size_in_bytes"]
            and sha(path) == metadata["digest"][7:], "Downloaded archive size/SHA differs from GitHub metadata")
    package = SafeZip(path)
    try:
        prefix = f"installers/provenance/{value.version}-{spec.target}/"
        raw_manifest = package.read(prefix + "product-build.json")
        manifest = decode_json(raw_manifest)
        require(all(manifest.get(key) == expected for key, expected in
                    {"schema": 1, "name": "OpenPyCharm", "version": value.version, "target": spec.target,
                     "upstreamProduct": "PC", "sourceCommit": value.source_commit}.items()), "Product manifest identity/version/source mismatch")
        product = "product/OpenPyCharm.app/Contents/openpycharm-build.json" if spec.target == "macos-arm64" else "product/OpenPyCharm/openpycharm-build.json"
        require(decode_json(package.read(product)) == manifest, "Assembled and installer product manifests disagree")
        converted = source_verifier(manifest["sourceInputs"])
        receipt = decode_json(package.read(prefix + "installer.json"))
        name = spec.name(value.version)
        require(all(receipt.get(key) == expected for key, expected in
                    {"schema": 1, "target": spec.target, "version": value.version, "installer": name,
                     "sha256": spec.installer_sha256}.items()), "Installer receipt identity/version/digest mismatch")
        require(type(receipt.get("size")) is int and 0 < receipt["size"] <= MAX_INSTALLER
                and HEX64.fullmatch(receipt.get("productTreeSha256", "")), "Invalid installer size/product tree receipt")
        expected_checks = ({"hdiutil-verify", "mounted-product-tree", "copied-product-tree", "ad-hoc-signature"}
                           if spec.target == "macos-arm64" else {"pinned-Inno-Setup", "official-tool-Authenticode",
                               "executable-installer", "silent-install-file-identity", "installed-native-startup"})
        require(expected_checks.issubset(receipt.get("checks", [])), "Installer verification checks are incomplete")
        manifest_sha = hashlib.sha256(raw_manifest).hexdigest()
        startup_proof(decode_json(package.read(f"runtime-startup-{spec.target}/startup.json")), value, spec, manifest_sha)
        if spec.target == "windows-x64":
            startup_proof(decode_json(package.read(prefix + "installed-startup/startup.json")), value, spec, manifest_sha)
            require(receipt.get("installedStartup", {}).get("status") == "passed-startup"
                    and receipt["installedStartup"].get("productManifestSha256") == manifest_sha, "Installed startup receipt mismatch")
        sidecar = package.read("installers/" + name + ".sha256", 1024).decode("ascii").strip()
        require(sidecar == f"{spec.installer_sha256}  {name}", "Installer checksum sidecar differs")
        item = package.members.get("installers/" + name)
        require(item is not None and not item.is_dir() and item.file_size == receipt["size"], "Installer member size differs from receipt")
        destination = output / name
        with package.archive.open(item) as source, destination.open("xb") as target:
            copied = 0
            while block := source.read(min(1024 * 1024, receipt["size"] + 1 - copied)):
                copied += len(block)
                require(copied <= receipt["size"], "Installer expands beyond declared size")
                target.write(block)
        require(copied == receipt["size"] and sha(destination) == spec.installer_sha256, "Installer actual size/SHA mismatch")
        with destination.open("rb") as stream:
            if spec.target == "windows-x64":
                require(stream.read(2) == b"MZ", "Windows installer executable header missing")
            else:
                require(copied >= 512, "DMG trailer missing")
                stream.seek(-512, os.SEEK_END)
                require(stream.read(4) == b"koly", "macOS installer UDIF trailer missing")
        return VerifiedInstaller(spec.target, name, destination, copied, spec.installer_sha256,
                                 spec.artifact_id, metadata["digest"][7:], converted)
    finally:
        package.close()


def release_snapshot(value, release):
    require(type(release.get("id")) is int and release["id"] > 0 and release.get("draft") is True
            and release.get("tag_name") == value.tag and release.get("target_commitish") == value.documentation_commit,
            "Only the matching existing draft with the exact documentation target is accepted")
    require(release.get("published_at") is None and release.get("immutable") is not True, "Release is already public/immutable")
    require(isinstance(release.get("body"), str) and release["body"].strip(), "Prepare reviewed draft release notes first")
    assets = {}
    for asset in release.get("assets", []):
        name = asset.get("name")
        require(isinstance(name, str) and name not in assets, "Duplicate/invalid release asset names")
        assets[name] = {key: asset.get(key) for key in ("id", "name", "size", "state", "digest")}
    return {"id": release["id"], "tag": value.tag, "documentationCommit": value.documentation_commit,
            "name": release.get("name"), "prerelease": release.get("prerelease"),
            "bodySha256": hashlib.sha256(release["body"].encode()).hexdigest(), "assets": assets}


def verify_draft(value, release, original, assets):
    current = release_snapshot(value, release)
    require({key: current[key] for key in current if key != "assets"} ==
            {key: original[key] for key in original if key != "assets"} and current["assets"] == assets,
            "Draft identity, notes or assets changed during verification/transfer")


def verify_tag(value, client):
    # Drafts may not have created a tag yet. An existing lightweight/annotated
    # tag must already resolve to the explicitly reviewed documentation commit.
    refs = client.json(f"repos/{REPOSITORY}/git/matching-refs/tags/{quote(value.tag, safe='')}")
    require(isinstance(refs, list) and len(refs) <= 1000, "Invalid or excessive tag reference response")
    matches = [ref for ref in refs if ref.get("ref") == "refs/tags/" + value.tag]
    require(len(matches) <= 1, "Ambiguous tag reference")
    if not matches:
        return
    target = matches[0].get("object", {})
    for _ in range(5):
        require(HEX40.fullmatch(target.get("sha", "")), "Invalid tag object")
        if target.get("type") == "commit":
            require(target["sha"] == value.documentation_commit, "Existing tag points to another documentation commit")
            return
        require(target.get("type") == "tag", "Tag does not point to a commit")
        target = client.json(f"repos/{REPOSITORY}/git/tags/{target['sha']}").get("object", {})
    raise ValueError("Annotated tag nesting exceeds its bound")


class GitHub:
    def __init__(self, config):
        require(bool(os.environ.get("GH_TOKEN")), "Only an explicitly supplied ephemeral GH_TOKEN is supported")
        self.environment = dict(os.environ, GH_HOST="github.com", GH_CONFIG_DIR=str(config), GH_PROMPT_DISABLED="1")
        self.environment.pop("GH_DEBUG", None)

    def json(self, endpoint, *args):
        completed = subprocess.run(["gh", "api", "--hostname", "github.com", endpoint, *args],
                                   env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        require(completed.returncode == 0, "GitHub API operation failed; no client stderr/tokens are logged")
        require(len(completed.stdout) <= 16 * 1024**2, "API response exceeds its bound")
        return decode_json(completed.stdout)

    def pages(self, endpoint, key=None):
        result = []
        for page in range(1, 11):
            data = self.json(endpoint + ("&" if "?" in endpoint else "?") + f"per_page=100&page={page}")
            items = data[key] if key else data
            require(isinstance(items, list), "Unexpected paginated API response")
            result.extend(items)
            if len(items) < 100:
                return result
        raise ValueError("API pagination exceeds its bound")

    def release(self, tag):
        # REST's release-by-tag endpoint does not resolve draft releases. List
        # authenticated drafts, require one exact tag, then freeze its database ID.
        matches = [item for item in self.pages(f"repos/{REPOSITORY}/releases") if item.get("tag_name") == tag]
        require(len(matches) == 1 and matches[0].get("draft") is True,
                "Exactly one matching existing draft release is required")
        release_id = matches[0].get("id")
        require(type(release_id) is int and release_id > 0, "Invalid draft release ID")
        result = self.json(f"repos/{REPOSITORY}/releases/{release_id}")
        result["assets"] = self.pages(f"repos/{REPOSITORY}/releases/{result['id']}/assets")
        return result

    def download(self, artifact_id, destination, expected_size):
        with destination.open("xb") as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(["gh", "api", "--hostname", "github.com",
                                        f"repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"],
                                       env=self.environment, stdout=subprocess.PIPE, stderr=errors)
            watchdog = threading.Timer(600, process.kill)
            watchdog.start()
            count = 0
            try:
                while block := process.stdout.read(min(1024 * 1024, expected_size + 1 - count)):
                    count += len(block)
                    require(count <= expected_size, "Artifact download exceeds GitHub's declared size")
                    output.write(block)
                require(process.wait(timeout=10) == 0 and count == expected_size, "Artifact download failed or is incomplete")
            finally:
                watchdog.cancel()
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
                process.stdout.close()

    def upload(self, release_id, installer):
        # The release ID is frozen; never re-resolve the tag through gh release upload.
        require(type(release_id) is int and release_id > 0, "Invalid frozen release ID")
        endpoint = f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release_id}/assets?name={quote(installer.name, safe='')}"
        # gh api's generic input reader does not imply a Content-Length. Set
        # the independently verified byte count explicitly for release uploads.
        return self.json(endpoint, "--method", "POST", "-H", "Content-Type: application/octet-stream",
                         "-H", f"Content-Length: {installer.size}", "--input", str(installer.path))


def transfer(value, client, repo, workspace, upload=False):
    validate_inputs(value)
    repository = client.json(f"repos/{REPOSITORY}")
    workflow = client.json(f"repos/{REPOSITORY}/actions/workflows/build.yml")
    run = client.json(f"repos/{REPOSITORY}/actions/runs/{value.run_id}")
    jobs = client.pages(f"repos/{REPOSITORY}/actions/runs/{value.run_id}/attempts/{run.get('run_attempt')}/jobs", "jobs")
    validate_context(value, repository, workflow, run, jobs)
    release = client.release(value.tag)
    snapshot = release_snapshot(value, release)
    verify_tag(value, client)
    expected_names = {spec.name(value.version) for spec in value.specs}
    require(not expected_names.intersection(snapshot["assets"]), "An installer asset already exists; overwrite is forbidden")
    verified = []
    for spec in value.specs:
        metadata = client.json(f"repos/{REPOSITORY}/actions/artifacts/{spec.artifact_id}")
        validate_artifact(value, spec, metadata, repository["id"])
        require(shutil.disk_usage(workspace).free >= 20 * 1024**3 + metadata["size_in_bytes"] + MAX_INSTALLER,
                "Installer verification must retain 20 GiB free")
        archive = workspace / f"{spec.target}.zip"
        client.download(spec.artifact_id, archive, metadata["size_in_bytes"])
        verified.append(verify_archive(archive, value, spec, metadata, workspace,
            lambda capture, target=spec.target: verify_git_sources(repo, value, capture, target)))
    assets = dict(snapshot["assets"])
    for item in verified:
        current_run = client.json(f"repos/{REPOSITORY}/actions/runs/{value.run_id}")
        require(current_run.get("run_attempt") == run["run_attempt"], "Build was rerun during verification")
        validate_context(value, repository, workflow, current_run, jobs)
        verify_tag(value, client)
        verify_draft(value, client.release(value.tag), snapshot, assets)
        require(sha(item.path) == item.sha256 and item.path.stat().st_size == item.size, "Verified installer changed before upload")
        if upload:
            result = client.upload(snapshot["id"], item)
            require(type(result.get("id")) is int and result.get("state") == "uploaded" and result.get("name") == item.name
                    and result.get("size") == item.size and result.get("digest") == "sha256:" + item.sha256,
                    "Uploaded asset identity/size/digest is incomplete or differs")
            assets[item.name] = {key: result.get(key) for key in ("id", "name", "size", "state", "digest")}
            verify_draft(value, client.release(value.tag), snapshot, assets)
            verify_tag(value, client)
    return {"schema": 1, "repository": REPOSITORY, "runId": value.run_id, "sourceCommit": value.source_commit,
            "documentationCommit": value.documentation_commit, "tag": value.tag, "releaseId": snapshot["id"],
            "uploaded": upload, "draftPublished": False,
            "installers": [{key: getattr(item, key) for key in ("target", "name", "size", "sha256", "artifact_id", "archive_sha256", "windows_checkout_conversions")} for item in verified]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("tag", "source-commit", "documentation-commit", "mac-sha256", "windows-sha256"):
        parser.add_argument("--" + name, required=True)
    for name in ("run-id", "mac-artifact-id", "windows-artifact-id"):
        parser.add_argument("--" + name, required=True, type=int)
    parser.add_argument("--upload", action="store_true", help="Attach only after all checks; default verifies without upload")
    args = parser.parse_args()
    if args.upload:
        require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
                and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and os.environ.get("GITHUB_REF") == "refs/heads/main",
                "Uploads are supported only by the manual main-branch workflow in this repository")
    value = TransferInputs(args.tag, args.source_commit, args.documentation_commit, args.run_id,
                           args.mac_artifact_id, args.mac_sha256, args.windows_artifact_id, args.windows_sha256)
    with tempfile.TemporaryDirectory(prefix="openpycharm-transfer-", dir=os.environ.get("RUNNER_TEMP")) as directory:
        work = Path(directory)
        result = transfer(value, GitHub(work / "gh-config"), Path.cwd(), work, args.upload)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        raise SystemExit("Installer transfer refused: " + str(error))
