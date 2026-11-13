"""Offline receipts for draft-only transfer; no GitHub, installers or IDE execute."""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("owned_transfer_ci_installers", ROOT / ".github/scripts/transfer_ci_installers.py")
transfer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = transfer
SPEC.loader.exec_module(transfer)

MAC_BYTES = b"owned test DMG payload" + b"koly" + bytes(508)
WINDOWS_BYTES = b"MZ\x90\x00owned test executable payload"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inputs(**changes):
    value = transfer.TransferInputs("v0.1.0-dev.9", "a" * 40, "b" * 40,
                                    17, 101, digest(MAC_BYTES), 102, digest(WINDOWS_BYTES))
    return replace(value, **changes)


def context(value):
    repository = {"id": 450, "full_name": transfer.REPOSITORY}
    workflow = {"id": 77, "path": transfer.WORKFLOW_PATH, "name": "Build native installers", "state": "active"}
    run = {"id": value.run_id, "workflow_id": 77, "path": transfer.WORKFLOW_PATH,
           "head_sha": value.source_commit, "repository": repository.copy(),
           "head_repository": repository.copy(), "event": "push", "status": "completed",
           "conclusion": "success", "run_attempt": 2}
    jobs = [{"name": spec.target, "run_id": value.run_id, "head_sha": value.source_commit,
             "run_attempt": 2, "status": "completed", "conclusion": "success"} for spec in value.specs]
    return repository, workflow, run, jobs


def draft(value):
    return {"id": 91, "draft": True, "tag_name": value.tag,
            "target_commitish": value.documentation_commit, "published_at": None,
            "body": "Reviewed release notes and native acceptance limits.",
            "assets": [{"id": 800, "name": "existing-provenance.json", "size": 8,
                        "state": "uploaded", "digest": "sha256:" + "c" * 64}]}


def archive_fixture(folder, value, target, capture, mutate=None, extra=()):
    """Tiny real ZIPs bind installer bytes to independent product/startup receipts."""
    spec = next(item for item in value.specs if item.target == target)
    name = spec.name(value.version)
    prefix = f"installers/provenance/{value.version}-{target}/"
    payload = MAC_BYTES if target == "macos-arm64" else WINDOWS_BYTES
    manifest = {"schema": 1, "name": "OpenPyCharm", "version": value.version,
                "target": target, "upstreamProduct": "PC", "sourceCommit": value.source_commit,
                "sourceInputs": capture}
    receipt = {"schema": 1, "target": target, "version": value.version, "installer": name,
               "sha256": spec.installer_sha256, "size": len(payload), "productTreeSha256": "d" * 64,
               "checks": (["hdiutil-verify", "mounted-product-tree", "copied-product-tree", "ad-hoc-signature"]
                          if target == "macos-arm64" else ["pinned-Inno-Setup", "official-tool-Authenticode",
                              "executable-installer", "silent-install-file-identity", "installed-native-startup"])}
    encode = lambda item: (json.dumps(item, indent=2) + "\n").encode()
    raw_manifest = encode(manifest)
    if target == "windows-x64":
        raw_manifest = raw_manifest.replace(b"\n", b"\r\n")
    startup = {"schema": 1, "status": "passed-startup", "target": target, "version": value.version,
               "productManifestSha256": digest(raw_manifest), "finalObservation": {
                   "errorCount": 0, "ideStarted": True, "productIdentity": True, "vendorIdentity": True,
                   "isolatedPaths": dict.fromkeys(("config", "system", "plugins", "log"), True)}}
    if target == "windows-x64":
        receipt["installedStartup"] = {"status": "passed-startup", "productManifestSha256": digest(raw_manifest)}
    product = ("product/OpenPyCharm.app/Contents/openpycharm-build.json" if target == "macos-arm64"
               else "product/OpenPyCharm/openpycharm-build.json")
    entries = {prefix + "product-build.json": raw_manifest, product: raw_manifest,
               prefix + "installer.json": encode(receipt),
               f"runtime-startup-{target}/startup.json": encode(startup),
               "installers/" + name: payload,
               "installers/" + name + ".sha256": f"{spec.installer_sha256}  {name}\n".encode()}
    if target == "windows-x64":
        entries[prefix + "installed-startup/startup.json"] = encode(startup)
    if mutate:
        mutate(entries, prefix, product, name)
    path = folder / f"fixture-{target}.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # duplicate-entry negative fixtures
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for member, data in entries.items():
                archive.writestr(member, data)
            for member, data, mode in extra:
                info = zipfile.ZipInfo(member)
                info.external_attr = mode << 16
                archive.writestr(info, data)
    metadata = {"id": spec.artifact_id, "expired": False,
                "name": f"OpenPyCharm-{target}-{value.source_commit}", "size_in_bytes": path.stat().st_size,
                "digest": "sha256:" + transfer.sha(path), "workflow_run": {
                    "id": value.run_id, "head_sha": value.source_commit, "repository_id": 450,
                    "head_repository_id": 450}}
    return path, metadata


class GitFixture:
    def __init__(self, root):
        self.root = root
        root.mkdir()
        self.command("init", "-q")
        self.command("config", "user.name", "Owned fixture")
        self.command("config", "user.email", "fixture@example.invalid")
        self.command("config", "core.autocrlf", "false")
        self.files = {"scripts/build.py": b"print('owned fixture')\n",
                      "product/product.json": b'{"version":"0.1.0-dev.9"}\n',
                      "plugins/http/NOTICE": b"Owned fixture notice\n",
                      "requirements-build.txt": b"fixture==1\n", "LICENSE": b"Fixture license\n",
                      "NOTICE": b"Fixture attribution\n"}
        for name, data in self.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.source = self.commit("production")
        docs = root / "docs/release.md"
        docs.parent.mkdir()
        docs.write_text("Reviewed fixture notes.\n")
        self.documentation = self.commit("documentation only")

    def command(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()

    def commit(self, message):
        self.command("add", ".")
        self.command("commit", "-qm", message)
        return self.command("rev-parse", "HEAD")

    def value(self):
        return inputs(source_commit=self.source, documentation_commit=self.documentation)

    def capture(self, windows=False):
        return {name: digest(data.replace(b"\n", b"\r\n") if windows else data)
                for name, data in self.files.items()}


class FakeGitHub:
    """The only mutating operation exposed is non-overwriting asset attachment."""
    def __init__(self, value, artifacts):
        self.value = value
        self.repository, self.workflow, self.run, self.jobs = context(value)
        self.artifacts = artifacts
        self.state = draft(value)
        self.uploads, self.downloads = [], []
        self.release_reads = 0
        self.release_hook = None
        self.refs, self.tag_objects = [], {}
        self.run_reads = 0
        self.run_hook = None

    def json(self, endpoint, *unused):
        known = {f"repos/{transfer.REPOSITORY}": self.repository,
                 f"repos/{transfer.REPOSITORY}/actions/workflows/build.yml": self.workflow,
                 f"repos/{transfer.REPOSITORY}/actions/runs/{self.value.run_id}": self.run,
                 f"repos/{transfer.REPOSITORY}/git/matching-refs/tags/{self.value.tag}": self.refs}
        for identifier, data in self.tag_objects.items():
            known[f"repos/{transfer.REPOSITORY}/git/tags/{identifier}"] = data
        for identifier, (_, metadata) in self.artifacts.items():
            known[f"repos/{transfer.REPOSITORY}/actions/artifacts/{identifier}"] = metadata
        if endpoint not in known:
            raise AssertionError("Unexpected API operation: " + endpoint)
        result = copy.deepcopy(known[endpoint])
        if endpoint == f"repos/{transfer.REPOSITORY}/actions/runs/{self.value.run_id}":
            self.run_reads += 1
            if self.run_hook:
                self.run_hook(self, self.run_reads, result)
        return result

    def pages(self, endpoint, key=None):
        assert endpoint.endswith(f"/attempts/{self.run['run_attempt']}/jobs") and key == "jobs"
        return copy.deepcopy(self.jobs)

    def release(self, tag):
        assert tag == self.value.tag
        self.release_reads += 1
        result = copy.deepcopy(self.state)
        if self.release_hook:
            self.release_hook(self, self.release_reads, result)
        return result

    def download(self, artifact_id, destination, expected_size):
        source, _ = self.artifacts[artifact_id]
        assert source.stat().st_size == expected_size
        self.downloads.append(artifact_id)
        shutil.copyfile(source, destination)

    def upload(self, release_id, installer):
        assert release_id == self.state["id"] and self.state["draft"] is True
        assert installer.name not in {item["name"] for item in self.state["assets"]}
        record = {"id": 900 + len(self.uploads), "name": installer.name, "size": installer.size,
                  "state": "uploaded", "digest": "sha256:" + transfer.sha(installer.path)}
        self.uploads.append(record)
        self.state["assets"].append(record)
        return copy.deepcopy(record)


class TransferIdentityTests(unittest.TestCase):
    def test_inputs_require_exact_commits_hashes_tag_and_distinct_integer_ids(self):
        transfer.validate_inputs(inputs())
        cases = [{"tag": "0.1.0-dev.9"}, {"tag": "v0.1.0;echo"}, {"source_commit": "a" * 7},
                 {"documentation_commit": "B" * 40}, {"run_id": True}, {"mac_artifact_id": -1},
                 {"windows_artifact_id": 101}, {"mac_sha256": "A" * 64}, {"windows_sha256": "0" * 63}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                transfer.validate_inputs(inputs(**changes))

    def test_official_run_requires_own_repo_success_and_both_current_native_jobs(self):
        value = inputs()
        good = context(value)
        transfer.validate_context(value, *good)
        mutations = [lambda r, w, run, j: r.update(full_name="foreign/repository"),
                     lambda r, w, run, j: w.update(path=".github/workflows/unreviewed.yml"),
                     lambda r, w, run, j: run["head_repository"].update(id=999),
                     lambda r, w, run, j: run.update(event="pull_request"),
                     lambda r, w, run, j: run.update(status="in_progress"),
                     lambda r, w, run, j: run.update(conclusion="failure"),
                     lambda r, w, run, j: run.update(head_sha="e" * 40),
                     lambda r, w, run, j: j.pop(),
                     lambda r, w, run, j: j.append(j[0].copy()),
                     lambda r, w, run, j: j[1].update(run_attempt=1),
                     lambda r, w, run, j: j[1].update(conclusion="skipped")]
        for mutate in mutations:
            data = copy.deepcopy(good)
            mutate(*data)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                transfer.validate_context(value, *data)

    def test_artifact_must_bind_current_own_run_source_target_and_digest(self):
        value = inputs()
        spec = value.specs[0]
        good = {"id": spec.artifact_id, "name": f"OpenPyCharm-{spec.target}-{value.source_commit}",
                "expired": False, "size_in_bytes": 123, "digest": "sha256:" + "d" * 64,
                "workflow_run": {"id": value.run_id, "head_sha": value.source_commit,
                                 "repository_id": 450, "head_repository_id": 450}}
        transfer.validate_artifact(value, spec, good, 450)
        for changes in ({"expired": True}, {"id": 5}, {"name": "wrong-target"}, {"digest": "unknown"},
                        {"size_in_bytes": transfer.MAX_ARCHIVE + 1},
                        {"workflow_run": {**good["workflow_run"], "head_repository_id": 451}},
                        {"workflow_run": {**good["workflow_run"], "id": value.run_id + 1}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                transfer.validate_artifact(value, spec, {**good, **changes}, 450)

    def test_release_snapshot_and_preflight_reject_identity_notes_assets_or_public_drift(self):
        value = inputs()
        original = draft(value)
        snapshot = transfer.release_snapshot(value, original)
        for changes in ({"id": 92}, {"tag_name": "v0.1.0-dev.8"}, {"target_commitish": "e" * 40},
                        {"draft": False}, {"published_at": "2026-11-14T00:00:00Z"}, {"immutable": True},
                        {"body": "Changed reviewed notes"}, {"name": "Changed name"},
                        {"prerelease": True}, {"assets": []}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                transfer.verify_draft(value, {**original, **changes}, snapshot, snapshot["assets"])

    def test_existing_lightweight_or_annotated_tag_must_resolve_to_documentation_commit(self):
        value = inputs()
        client = FakeGitHub(value, {})
        transfer.verify_tag(value, client)  # A draft is allowed to have no tag yet.
        client.refs = [{"ref": "refs/tags/" + value.tag,
                        "object": {"type": "commit", "sha": value.documentation_commit}}]
        transfer.verify_tag(value, client)
        client.refs[0]["object"]["sha"] = value.source_commit
        with self.assertRaisesRegex(ValueError, "another documentation commit"):
            transfer.verify_tag(value, client)
        tag_sha = "e" * 40
        client.refs[0]["object"] = {"type": "tag", "sha": tag_sha}
        client.tag_objects[tag_sha] = {"object": {"type": "commit", "sha": value.documentation_commit}}
        transfer.verify_tag(value, client)
        client.tag_objects[tag_sha]["object"]["sha"] = value.source_commit
        with self.assertRaisesRegex(ValueError, "another documentation commit"):
            transfer.verify_tag(value, client)


class GitHubTransportTests(unittest.TestCase):
    def test_client_requires_explicit_token_and_uses_owned_config_without_debug(self):
        with patch.dict(transfer.os.environ, {"GITHUB_TOKEN": "not-an-explicit-gh-token"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ephemeral GH_TOKEN"):
                transfer.GitHub(Path("owned-gh-config"))
        with patch.dict(transfer.os.environ, {"GH_TOKEN": "ephemeral-fixture-token", "GH_DEBUG": "api",
                                              "GH_CONFIG_DIR": "shared-config", "GH_HOST": "other.invalid"}, clear=True):
            client = transfer.GitHub(Path("owned-gh-config"))
        self.assertEqual("ephemeral-fixture-token", client.environment["GH_TOKEN"])
        self.assertEqual("owned-gh-config", client.environment["GH_CONFIG_DIR"])
        self.assertEqual("github.com", client.environment["GH_HOST"])
        self.assertEqual("1", client.environment["GH_PROMPT_DISABLED"])
        self.assertNotIn("GH_DEBUG", client.environment)

    def test_draft_lookup_uses_authenticated_listing_then_the_frozen_numeric_id(self):
        value = inputs()
        with patch.dict(transfer.os.environ, {"GH_TOKEN": "ephemeral-fixture-token"}, clear=True):
            client = transfer.GitHub(Path("owned-gh-config"))
        existing = draft(value)
        def pages(endpoint, key=None):
            self.assertIsNone(key)
            if endpoint == "repos/shubolab/openpycharm/releases":
                return [{"id": 5, "tag_name": value.tag + ".old", "draft": True},
                        {"id": 91, "tag_name": value.tag, "draft": True}]
            self.assertEqual("repos/shubolab/openpycharm/releases/91/assets", endpoint)
            return existing["assets"]
        with patch.object(client, "pages", side_effect=pages) as listed, \
                patch.object(client, "json", return_value={**existing, "assets": []}) as fetched:
            actual = client.release(value.tag)
        fetched.assert_called_once_with("repos/shubolab/openpycharm/releases/91")
        self.assertEqual(2, listed.call_count)
        self.assertEqual(existing, actual)

    def test_draft_lookup_refuses_missing_ambiguous_published_or_noninteger_id(self):
        value = inputs()
        with patch.dict(transfer.os.environ, {"GH_TOKEN": "ephemeral-fixture-token"}, clear=True):
            client = transfer.GitHub(Path("owned-gh-config"))
        matching = {"id": 91, "tag_name": value.tag, "draft": True}
        for candidates in ([], [matching, matching.copy()], [{**matching, "draft": False}],
                           [{**matching, "id": True}], [{**matching, "id": "91"}]):
            with self.subTest(candidates=candidates), patch.object(client, "pages", return_value=candidates), \
                    patch.object(client, "json") as fetched:
                with self.assertRaises(ValueError):
                    client.release(value.tag)
                fetched.assert_not_called()

    def test_upload_uses_frozen_release_id_and_explicit_verified_content_length(self):
        with patch.dict(transfer.os.environ, {"GH_TOKEN": "ephemeral-fixture-token"}, clear=True):
            client = transfer.GitHub(Path("owned-gh-config"))
        name = "OpenPyCharm-0.1.0-dev.9-macos-arm64.dmg"
        installer = transfer.VerifiedInstaller("macos-arm64", name, Path("owned-installer.dmg"), len(MAC_BYTES),
                                               digest(MAC_BYTES), 101, "a" * 64, [])
        with patch.object(client, "json", return_value={"id": 900}) as request:
            self.assertEqual({"id": 900}, client.upload(91, installer))
            request.assert_called_once_with(
                "https://uploads.github.com/repos/shubolab/openpycharm/releases/91/assets?name=" + name,
                "--method", "POST", "-H", "Content-Type: application/octet-stream",
                "-H", f"Content-Length: {len(MAC_BYTES)}", "--input", "owned-installer.dmg")
            self.assertFalse(any("clobber" in str(arg) or "DELETE" == str(arg) for arg in request.call_args.args))
        for release_id in (True, 0, -1, "91"):
            with self.subTest(release_id=release_id), patch.object(client, "json") as request:
                with self.assertRaisesRegex(ValueError, "frozen release ID"):
                    client.upload(release_id, installer)
                request.assert_not_called()


class ArchiveReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.value = inputs()
        self.capture = {"scripts/build.py": digest(b"owned source\n")}
        self.sequence = 0

    def check(self, target="macos-arm64", mutate=None, extra=(), metadata_change=None):
        self.sequence += 1
        folder = self.root / str(self.sequence)
        folder.mkdir()
        path, metadata = archive_fixture(folder, self.value, target, self.capture, mutate, extra)
        if metadata_change:
            metadata_change(metadata)
        output = folder / "verified"
        output.mkdir()
        seen = []
        def source_verifier(capture):
            self.assertEqual(self.capture, capture)
            seen.append(capture)
            return []
        result = transfer.verify_archive(path, self.value, next(x for x in self.value.specs if x.target == target),
                                         metadata, output, source_verifier)
        self.assertEqual(1, len(seen))
        return result

    def test_real_minimal_mac_and_windows_receipts_verify_expected_installer_bytes(self):
        for target, expected in (("macos-arm64", MAC_BYTES), ("windows-x64", WINDOWS_BYTES)):
            with self.subTest(target=target):
                verified = self.check(target)
                self.assertEqual(expected, verified.path.read_bytes())
                self.assertEqual(len(expected), verified.size)

    def test_archive_hash_and_length_are_checked_before_proof_parsing(self):
        for mutate in (lambda m: m.update(digest="sha256:" + "f" * 64),
                       lambda m: m.update(size_in_bytes=m["size_in_bytes"] + 1)):
            with self.subTest(mutation=mutate), self.assertRaisesRegex(ValueError, "Downloaded archive"):
                self.check(metadata_change=mutate)

    def test_zip_rejects_duplicates_paths_and_symbolic_link_members(self):
        prefix = "installers/provenance/0.1.0-dev.9-macos-arm64/"
        for name, mode in ((prefix + "installer.json", stat.S_IFREG | 0o644),
                           ("../outside", stat.S_IFREG | 0o644), ("/absolute", stat.S_IFREG | 0o644),
                           ("nested\\windows-path", stat.S_IFREG | 0o644),
                           ("link-to-private", stat.S_IFLNK | 0o777)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(extra=[(name, b"not extracted", mode)])

    def test_oversized_or_duplicate_key_json_is_not_accepted_as_a_receipt(self):
        for raw in (b" " * (transfer.MAX_JSON + 1), b'{"schema":1,"schema":1}'):
            def mutate(entries, prefix, product, name):
                entries[prefix + "installer.json"] = raw
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                self.check(mutate=mutate)

    def test_manifest_receipt_startup_checksum_and_installer_tampering_fail(self):
        def edit_json(entries, name, changes):
            data = json.loads(entries[name])
            data.update(changes)
            entries[name] = json.dumps(data).encode()
        mutations = [lambda e, p, product, n: edit_json(e, p + "product-build.json", {"sourceCommit": "e" * 40}),
                     lambda e, p, product, n: edit_json(e, product, {"version": "0.1.0-dev.8"}),
                     lambda e, p, product, n: edit_json(e, p + "installer.json", {"version": "0.1.0-dev.8"}),
                     lambda e, p, product, n: edit_json(e, p + "installer.json", {"target": "windows-x64"}),
                     lambda e, p, product, n: edit_json(e, p + "installer.json", {"sha256": "f" * 64}),
                     lambda e, p, product, n: edit_json(e, p + "installer.json", {"size": len(MAC_BYTES) + 1}),
                     lambda e, p, product, n: edit_json(e, p + "installer.json", {"checks": []}),
                     lambda e, p, product, n: edit_json(e, "runtime-startup-macos-arm64/startup.json", {"productManifestSha256": "f" * 64}),
                     lambda e, p, product, n: e.update({"installers/" + n + ".sha256": b"wrong checksum\n"}),
                     lambda e, p, product, n: e.update({"installers/" + n: MAC_BYTES[:-1] + b"!"})]
        for mutate in mutations:
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.check(mutate=mutate)

    def test_windows_installed_startup_must_bind_the_raw_crlf_manifest(self):
        def mutate(entries, prefix, product, name):
            data = json.loads(entries[prefix + "installed-startup/startup.json"])
            data["productManifestSha256"] = digest(entries[prefix + "product-build.json"].replace(b"\r\n", b"\n"))
            entries[prefix + "installed-startup/startup.json"] = json.dumps(data).encode()
        with self.assertRaisesRegex(ValueError, "startup proof"):
            self.check("windows-x64", mutate)

    def test_matching_sha_receipts_cannot_disguise_wrong_installer_container_type(self):
        for target, payload, expected_error in (
            ("macos-arm64", MAC_BYTES[:-512] + b"nope" + bytes(508), "UDIF trailer"),
            ("windows-x64", b"NO" + WINDOWS_BYTES[2:], "executable header"),
        ):
            with self.subTest(target=target):
                self.value = inputs(**{"mac_sha256" if target == "macos-arm64" else "windows_sha256": digest(payload)})
                def mutate(entries, prefix, product, name):
                    entries["installers/" + name] = payload
                with self.assertRaisesRegex(ValueError, expected_error):
                    self.check(target, mutate)


class GitSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = GitFixture(Path(self.temporary.name) / "repo")

    def test_documentation_only_descendant_preserves_exact_complete_source_capture(self):
        self.assertEqual([], transfer.verify_git_sources(self.repo.root, self.repo.value(), self.repo.capture(), "macos-arm64"))
        for capture in ({**self.repo.capture(), "scripts/extra.py": "a" * 64},
                        {name: digest for name, digest in self.repo.capture().items() if name != "NOTICE"},
                        {**self.repo.capture(), "scripts/build.py": "f" * 64}):
            with self.subTest(capture=capture), self.assertRaises(ValueError):
                transfer.verify_git_sources(self.repo.root, self.repo.value(), capture, "macos-arm64")

    def test_documentation_commit_cannot_change_production_inputs_or_precede_source(self):
        (self.repo.root / "scripts/build.py").write_bytes(b"print('changed code')\n")
        changed = self.repo.commit("code drift")
        with self.assertRaisesRegex(ValueError, "production inputs differ"):
            transfer.verify_git_sources(self.repo.root, replace(self.repo.value(), documentation_commit=changed), self.repo.capture(), "macos-arm64")
        with self.assertRaisesRegex(ValueError, "descend"):
            transfer.verify_git_sources(self.repo.root, replace(self.repo.value(), source_commit=changed), self.repo.capture(), "macos-arm64")

    def test_windows_allows_only_exact_text_checkout_newline_conversion(self):
        converted = transfer.verify_git_sources(self.repo.root, self.repo.value(), self.repo.capture(True), "windows-x64")
        self.assertEqual(sorted(self.repo.files), converted)
        with self.assertRaises(ValueError):
            transfer.verify_git_sources(self.repo.root, self.repo.value(), self.repo.capture(True), "macos-arm64")
        bad = self.repo.capture(True)
        bad["scripts/build.py"] = digest(self.repo.files["scripts/build.py"].replace(b"\n", b"\r\r\n"))
        with self.assertRaises(ValueError):
            transfer.verify_git_sources(self.repo.root, self.repo.value(), bad, "windows-x64")

    def test_existing_crlf_blob_cannot_be_doubled_and_documentation_mode_drift_fails(self):
        self.repo.files["plugins/http/NOTICE"] = b"Already CRLF\r\n"
        (self.repo.root / "plugins/http/NOTICE").write_bytes(self.repo.files["plugins/http/NOTICE"])
        self.repo.source = self.repo.commit("preserve CRLF fixture blob")
        self.repo.documentation = self.repo.source
        bad = self.repo.capture()
        bad["plugins/http/NOTICE"] = digest(b"Already CRLF\r\r\n")
        with self.assertRaisesRegex(ValueError, "production Git blob"):
            transfer.verify_git_sources(self.repo.root, self.repo.value(), bad, "windows-x64")
        self.repo.command("update-index", "--chmod=+x", "scripts/build.py")
        self.repo.command("commit", "-qm", "production file mode drift")
        self.repo.documentation = self.repo.command("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "production inputs differ"):
            transfer.verify_git_sources(self.repo.root, self.repo.value(), self.repo.capture(), "macos-arm64")

    def test_binary_source_cannot_take_text_conversion_and_source_symlinks_fail(self):
        binary = self.repo.root / "plugins/http/payload.bin"
        binary.write_bytes(b"binary\0payload\n")
        self.repo.files["plugins/http/payload.bin"] = binary.read_bytes()
        self.repo.source = self.repo.commit("binary source fixture")
        (self.repo.root / "docs/release.md").write_text("Updated documentation.\n")
        self.repo.documentation = self.repo.commit("documentation")
        with self.assertRaisesRegex(ValueError, "production Git blob"):
            transfer.verify_git_sources(self.repo.root, self.repo.value(), self.repo.capture(True), "windows-x64")
        binary.unlink()
        binary.symlink_to("../../LICENSE")
        linked = self.repo.commit("source symlink")
        with self.assertRaisesRegex(ValueError, "links/submodules"):
            transfer.verify_git_sources(self.repo.root, replace(self.repo.value(), source_commit=linked, documentation_commit=linked), self.repo.capture(), "macos-arm64")


class TransferOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = GitFixture(self.root / "repo")
        self.value = self.repo.value()
        self.fixtures = self.root / "fixtures"
        self.fixtures.mkdir()
        disk = patch.object(transfer.shutil, "disk_usage", return_value=SimpleNamespace(free=100 * 1024**3))
        disk.start()
        self.addCleanup(disk.stop)

    def client(self, bad_windows=False):
        artifacts = {}
        for spec in self.value.specs:
            def corrupt(entries, prefix, product, name):
                receipt = json.loads(entries[prefix + "installer.json"])
                receipt["version"] = "0.1.0-dev.8"
                entries[prefix + "installer.json"] = json.dumps(receipt).encode()
            artifacts[spec.artifact_id] = archive_fixture(self.fixtures, self.value, spec.target,
                self.repo.capture(spec.target == "windows-x64"), corrupt if bad_windows and spec.target == "windows-x64" else None)
        return FakeGitHub(self.value, artifacts)

    def invoke(self, client, upload=True):
        workspace = self.root / "transfer"
        workspace.mkdir()
        return transfer.transfer(self.value, client, self.repo.root, workspace, upload)

    def test_both_installers_verify_before_nonoverwriting_uploads_to_same_existing_draft(self):
        client = self.client()
        existing = copy.deepcopy(client.state["assets"])
        result = self.invoke(client)
        self.assertEqual([101, 102], client.downloads)
        self.assertEqual(2, len(client.uploads))
        self.assertEqual(existing, client.state["assets"][:len(existing)])
        self.assertTrue(client.state["draft"])
        self.assertFalse(result["draftPublished"])
        self.assertTrue(result["uploaded"])

    def test_default_verification_never_calls_upload(self):
        client = self.client()
        result = self.invoke(client, False)
        self.assertEqual(2, len(result["installers"]))
        self.assertFalse(result["uploaded"])
        self.assertEqual([], client.uploads)

    def test_late_invalid_second_artifact_causes_zero_uploads(self):
        client = self.client(bad_windows=True)
        with self.assertRaisesRegex(ValueError, "Installer receipt"):
            self.invoke(client)
        self.assertEqual([101, 102], client.downloads)
        self.assertEqual([], client.uploads)

    def test_existing_installer_prevents_even_archive_download_and_never_overwrites(self):
        client = self.client()
        client.state["assets"].append({"name": self.value.specs[0].name(self.value.version)})
        original = copy.deepcopy(client.state)
        with self.assertRaisesRegex(ValueError, "overwrite is forbidden"):
            self.invoke(client)
        self.assertEqual([], client.downloads)
        self.assertEqual([], client.uploads)
        self.assertEqual(original, client.state)

    def test_preupload_draft_drift_stops_before_any_upload(self):
        for key, changed in (("draft", False), ("id", 999), ("body", "Changed notes")):
            with self.subTest(key=key):
                client = self.client()
                client.release_hook = lambda c, count, result: result.update({key: changed}) if count == 2 else None
                workspace = self.root / ("preflight-" + key)
                workspace.mkdir()
                with self.assertRaises(ValueError):
                    transfer.transfer(self.value, client, self.repo.root, workspace, True)
                self.assertEqual([], client.uploads)

    def test_postupload_draft_drift_is_detected_without_second_upload_or_publish(self):
        client = self.client()
        client.release_hook = lambda c, count, result: result.update(draft=False) if count == 3 else None
        with self.assertRaises(ValueError):
            self.invoke(client)
        self.assertEqual(1, len(client.uploads))
        self.assertTrue(client.state["draft"])
        self.assertEqual("existing-provenance.json", client.state["assets"][0]["name"])

    def test_rerun_or_new_wrong_tag_is_rejected_before_first_upload(self):
        for kind in ("rerun", "tag"):
            with self.subTest(kind=kind):
                client = self.client()
                if kind == "rerun":
                    client.run_hook = lambda c, count, result: result.update(run_attempt=3) if count == 2 else None
                else:
                    client.refs = [{"ref": "refs/tags/" + self.value.tag,
                                    "object": {"type": "commit", "sha": self.value.source_commit}}]
                workspace = self.root / ("late-" + kind)
                workspace.mkdir()
                with self.assertRaises(ValueError):
                    transfer.transfer(self.value, client, self.repo.root, workspace, True)
                self.assertEqual([], client.uploads)

    def test_verified_local_installer_drift_before_upload_is_detected(self):
        client = self.client()
        def change_file(_client, count, _result):
            if count == 2:
                path = self.root / "transfer" / self.value.specs[0].name(self.value.version)
                path.write_bytes(b"unexpected local mutation")
        client.release_hook = change_file
        with self.assertRaisesRegex(ValueError, "changed before upload"):
            self.invoke(client)
        self.assertEqual([], client.uploads)


if __name__ == "__main__":
    unittest.main()
