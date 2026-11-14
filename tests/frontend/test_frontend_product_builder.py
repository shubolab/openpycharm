from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import build_frontend_product as builder


def record(data: bytes) -> dict:
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class ProductRuntimeFixture(unittest.TestCase):
    def setUp(self):
        parent = builder.ROOT / ".tools"; parent.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="frontend-product-unit-", dir=parent)
        self.addCleanup(temporary.cleanup); self.root = Path(temporary.name)
        self.runtime = self.root / ".tools/provision/runtime/macos-arm64/pinned"
        self.runtime.mkdir(parents=True)
        source_map = json.dumps({"sources": ["../node_modules/.pnpm/commander@15.1.0/node_modules/commander/index.js"]}).encode()
        self.contents = {
            "node/bin/node": b"authenticated fixture; never executed",
            "node/LICENSE": b"node original bundled notices",
            "typescript-language-server/lib/cli.mjs": b"published fixture language server",
            "typescript-language-server/lib/cli.mjs.map": source_map,
            "typescript/lib/tsserver.js": b"pinned fixture TypeScript server",
            "notices/commander-15.1.0/LICENSE": b"original MIT license notice",
            "notices/commander-15.1.0/package.json": b'{"name":"commander","version":"15.1.0"}',
        }
        for name, data in self.contents.items():
            path = self.runtime / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            path.chmod(0o755 if name == "node/bin/node" else 0o644)
        def artifact(name, prefix, **extra):
            return {"id": name, "size": 123, "sha256": hashlib.sha256(name.encode()).hexdigest(),
                    "payload": {n: record(data) for n, data in self.contents.items() if n.startswith(prefix)}, **extra}
        self.pin = {
            "artifacts": [artifact("node-macos-arm64", "node/", target="macos-arm64", nodeExecutable="node/bin/node"),
                          artifact("typescript-language-server", "typescript-language-server/"),
                          artifact("typescript", "typescript/"),
                          artifact("notice-commander", "notices/", purpose="bundled-cli-corresponding-notices-only", package="commander", version="15.1.0")],
            "runtimeEntries": {"typescriptLanguageServer": "typescript-language-server/lib/cli.mjs", "typescriptServer": "typescript/lib/tsserver.js"},
            "bundledClosure": {"sourceMapPath": "typescript-language-server/lib/cli.mjs.map", "sourceMapSha256": record(source_map)["sha256"],
                               "sourceCount": 1, "packages": {"commander": "15.1.0"}},
        }
        self.pin_path = self.root / "tools.lock.json"; self.pin_path.write_text(json.dumps(self.pin))
        expected = builder.runtime_manifest(self.pin, "macos-arm64")
        self.saved = {"schema": 1, "owner": "OpenPyCharm frontend M0", "target": "macos-arm64", "runtimeRoot": str(self.runtime),
                      "lockSha256": builder.sha256(self.pin_path), **expected,
                      "artifacts": [{k: item[k] for k in ("id", "sha256", "size")} for item in self.pin["artifacts"]],
                      "installationScriptsExecuted": False, "productionPackaged": False, "bundledPackageNotices": 1}
        self.receipt = self.runtime / "frontend-tools.json"; self.write_receipt()
        for name, value in [("ROOT", self.root), ("PIN", self.pin_path)]:
            patcher = patch.object(builder, name, value); patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(builder, "load_pin", return_value=self.pin); patcher.start(); self.addCleanup(patcher.stop)

    def write_receipt(self):
        self.receipt.write_text(json.dumps(self.saved)); self.receipt.chmod(0o644)

    def authenticate(self):
        return builder.authenticate_runtime(self.receipt, "macos-arm64")

    def test_existing_runtime_is_read_only_and_copy_is_relative_complete_and_executable(self):
        before = {name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                  for name, path in [(name, self.runtime / name) for name in [*self.contents, "frontend-tools.json"]]}
        with patch.object(builder.subprocess, "run") as process:
            authenticated = self.authenticate()
            destination = self.root / ".tools/staging/plugin/runtime/macos-arm64"
            records = builder.copy_runtime(authenticated, destination)
            process.assert_not_called()
        manifest = json.loads((destination / "bundled-runtime.json").read_text())
        self.assertEqual(set(manifest), {"schema", "target", "owner", "lockSha256", "files", "entries"})
        self.assertEqual(manifest["owner"], "OpenPyCharm bundled frontend")
        self.assertNotIn(str(self.root), (destination / "bundled-runtime.json").read_text())
        self.assertNotIn("frontend-tools.json", records)
        self.assertEqual(set(records), set(self.contents) | {"bundled-runtime.json"})
        self.assertEqual(manifest["files"], {name: record(data) for name, data in self.contents.items()})
        if os.name != "nt": self.assertEqual(records["node/bin/node"]["mode"], 0o755)
        after = {name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                 for name, path in [(name, self.runtime / name) for name in [*self.contents, "frontend-tools.json"]]}
        self.assertEqual(before, after)

    def test_payload_tamper_cannot_be_authorized_by_forging_receipt_file_hash(self):
        name = "node/bin/node"; changed = b"changed executable"
        (self.runtime / name).write_bytes(changed)
        self.saved["files"][name] = record(changed); self.write_receipt()
        with self.assertRaisesRegex(ValueError, "pinned identity/payload/legal"):
            self.authenticate()
        self.assertEqual((self.runtime / name).read_bytes(), changed)

    def test_missing_legal_text_extra_file_and_empty_directory_are_rejected(self):
        legal = self.runtime / "notices/commander-15.1.0/LICENSE"; data = legal.read_bytes(); legal.unlink()
        with self.assertRaises(ValueError): self.authenticate()
        legal.write_bytes(data); legal.chmod(0o644)
        extra = self.runtime / "unexpected"; extra.write_bytes(b"must not be packaged")
        with self.assertRaises(ValueError): self.authenticate()
        extra.unlink(); extra.mkdir()
        with self.assertRaises(ValueError): self.authenticate()

    def test_receipt_target_entries_schema_and_install_script_claims_are_checked(self):
        original = copy.deepcopy(self.saved)
        for mutation in ({"target": "windows-x64"}, {"schema": True}, {"owner": builder.BUNDLE_OWNER},
                         {"installationScriptsExecuted": True}, {"runtimeRoot": str(self.runtime.parent)},
                         {"entries": {**original["entries"], "node": "../outside"}}, {"bundledPackageNotices": 0}):
            self.saved = {**copy.deepcopy(original), **mutation}; self.write_receipt()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.authenticate()

    def test_links_at_payload_or_ancestor_never_read_or_overwrite_the_target(self):
        destination = self.root / "untouched"; destination.write_bytes(b"outside bytes")
        path = self.runtime / "node/bin/node"; original = path.read_bytes(); path.unlink()
        try: path.symlink_to(destination)
        except OSError as error: self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "symlinks"): self.authenticate()
        path.unlink(); path.write_bytes(original); path.chmod(0o755)
        linked = self.root / ".tools/link"
        linked.symlink_to(self.runtime, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            builder.authenticate_runtime(linked / "frontend-tools.json", "macos-arm64")
        self.assertEqual(destination.read_bytes(), b"outside bytes")

    @unittest.skipIf(os.name == "nt", "POSIX executable bits have no Windows equivalent")
    def test_same_node_bytes_with_changed_executable_permissions_are_rejected(self):
        path = self.runtime / "node/bin/node"; path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "mode differs"): self.authenticate()

    def test_source_map_dependency_legal_closure_is_rechecked_independently_of_the_receipt(self):
        self.pin["bundledClosure"]["packages"] = {"missing-notice-package": "1.0.0"}
        self.pin_path.write_text(json.dumps(self.pin)); self.saved["lockSha256"] = builder.sha256(self.pin_path); self.write_receipt()
        with self.assertRaisesRegex(ValueError, "notice closure"): self.authenticate()

    def test_copy_rechecks_bytes_after_prior_authentication_and_does_not_modify_source(self):
        authenticated = self.authenticate(); name = "typescript/lib/tsserver.js"
        (self.runtime / name).write_bytes(b"changed after authentication")
        destination = self.root / ".tools/staged/runtime"
        with self.assertRaisesRegex(ValueError, "size/SHA-256"):
            builder.copy_runtime(authenticated, destination)
        self.assertEqual((self.runtime / name).read_bytes(), b"changed after authentication")

    def test_insufficient_reserve_fails_before_output_creation(self):
        authenticated = self.authenticate(); destination = self.root / ".tools/not-created/runtime"
        with patch.object(builder, "check_space", side_effect=ValueError("20 GiB reserve")):
            with self.assertRaisesRegex(ValueError, "20 GiB"):
                builder.copy_runtime(authenticated, destination)
        self.assertFalse(destination.exists())

    def test_output_escape_existing_destination_and_duplicate_metadata_fail_closed(self):
        authenticated = self.authenticate()
        with self.assertRaisesRegex(ValueError, "checkout"):
            builder.copy_runtime(authenticated, self.root / "outside")
        with self.assertRaisesRegex(ValueError, "must be new"):
            builder.copy_runtime(authenticated, self.runtime)
        text = self.receipt.read_text().replace('"schema": 1', '"schema": 1, "schema": 1')
        self.receipt.write_text(text)
        with self.assertRaisesRegex(ValueError, "Duplicate"): self.authenticate()

    def test_a_linked_output_ancestor_cannot_write_the_destination(self):
        authenticated = self.authenticate(); outside = self.root / "outside"; outside.mkdir()
        linked = self.root / ".tools/linked-output"
        try: linked.symlink_to(outside, target_is_directory=True)
        except OSError as error: self.skipTest(str(error))
        with self.assertRaisesRegex(ValueError, "symlinks"):
            builder.copy_runtime(authenticated, linked / "runtime")
        self.assertEqual(list(outside.iterdir()), [])

    def test_target_payload_is_selected_explicitly_and_cannot_mix_node_binaries(self):
        windows = {"id": "node-windows-x64", "target": "windows-x64", "nodeExecutable": "node/node.exe",
                   "payload": {"node/node.exe": record(b"pinned PE bytes")}}
        pin = copy.deepcopy(self.pin); pin["artifacts"].append(windows)
        mac = builder.runtime_manifest(pin, "macos-arm64"); win = builder.runtime_manifest(pin, "windows-x64")
        self.assertIn("node/bin/node", mac["files"]); self.assertNotIn("node/node.exe", mac["files"])
        self.assertIn("node/node.exe", win["files"]); self.assertNotIn("node/bin/node", win["files"])
        self.assertEqual(win["entries"]["node"], "node/node.exe")
        pin["artifacts"].append(copy.deepcopy(windows))
        with self.assertRaisesRegex(ValueError, "overlaps"): builder.runtime_manifest(pin, "windows-x64")

    def product(self):
        root = self.root / ".tools/product"; (root / "lib").mkdir(parents=True)
        jar = root / "lib/frontend.jar"; jar.write_bytes(b"owned compiled JAR"); jar.chmod(0o644)
        runtime = self.runtime / "node/bin/node"
        copied = builder.copy_runtime(self.authenticate(), root / "runtime/macos-arm64")
        records = {"lib/frontend.jar": {**record(jar.read_bytes()), "mode": stat.S_IMODE(jar.stat().st_mode)}}
        records.update({"runtime/macos-arm64/" + name: value for name, value in copied.items()})
        saved = {"target": "macos-arm64", "fileRecords": records, "files": {n: r["sha256"] for n, r in records.items()},
                 "jarSha256": records["lib/frontend.jar"]["sha256"],
                 "archiveVerification": {"status": "pass", "sha256": records["lib/frontend.jar"]["sha256"]}}
        return root, saved

    def test_complete_multi_file_receipt_detects_jar_runtime_mode_and_extra_payload_drift(self):
        root, saved = self.product(); builder.validate_product(root, saved)
        jar = root / "lib/frontend.jar"; node = root / "runtime/macos-arm64/node/bin/node"
        for path in (jar, node):
            original = path.read_bytes(); path.write_bytes(b"changed payload")
            with self.assertRaisesRegex(ValueError, "size/SHA-256"): builder.validate_product(root, saved)
            path.write_bytes(original)
        if os.name != "nt":
            node.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "mode differs"): builder.validate_product(root, saved)
            node.chmod(0o755)
        extra = root / "runtime/extra"; extra.write_bytes(b"unreceipted")
        with self.assertRaises(ValueError): builder.validate_product(root, saved)

    def test_cached_output_receipt_cannot_reauthorize_different_node_or_bundle_authority(self):
        root, saved = self.product(); relative = "runtime/macos-arm64/node/bin/node"; node = root / relative
        node.write_bytes(b"tampered cached Node")
        saved["fileRecords"][relative] = {**record(node.read_bytes()), "mode": 0o755}
        saved["files"][relative] = builder.sha256(node)
        with self.assertRaisesRegex(ValueError, "cannot authorize different pinned bytes"):
            builder.validate_product(root, saved)
        manifest_path = root / "runtime/macos-arm64/bundled-runtime.json"
        manifest = json.loads(manifest_path.read_text()); manifest["runtimeRoot"] = "/outside"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "bundle authority"):
            builder.validate_product(root, saved)


class ProductReceiptTests(unittest.TestCase):
    def test_m0_descriptor_or_missing_registration_cannot_be_relabeled_as_product(self):
        descriptor = b'<idea-plugin><id>dev.openpycharm.frontend</id><version>@VERSION@</version><depends>com.intellij.modules.platform</depends><depends>com.intellij.modules.lsp</depends><extensions defaultExtensionNs="com.intellij.platform.lsp"><integrationProvider implementation="dev.openpycharm.frontend.FrontendProductLspProvider"/></extensions></idea-plugin>'
        self.assertIn(b"0.1.0-dev.4", builder.render_descriptor(descriptor, builder.VERSION))
        for bad in (descriptor.replace(b"dev.openpycharm.frontend</id>", b"dev.openpycharm.frontend.m0</id>"),
                    descriptor.replace(b"FrontendProductLspProvider", b"FrontendLspProvider"),
                    descriptor.replace(b'<extensions defaultExtensionNs="com.intellij.platform.lsp"><integrationProvider implementation="dev.openpycharm.frontend.FrontendProductLspProvider"/></extensions>', b'')):
            with self.subTest(descriptor=bad), self.assertRaisesRegex(ValueError, "descriptor"):
                builder.render_descriptor(bad, builder.VERSION)


if __name__ == "__main__":
    unittest.main()
