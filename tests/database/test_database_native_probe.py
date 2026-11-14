import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import database_completion_probe as probe


class NativeCompletionEvidenceControls(unittest.TestCase):
    def passing(self):
        return {"invocationId": "owned", "plugin": {"jarSha256": "a" * 64}, "status": "pass",
                "nativeBasicActionGatePassed": True, "projectTrusted": True, "ownedConnectionDisconnected": True,
                "heartbeatTicks": 10, "artificialSnapshotInjected": False, "lookupCreatedByProbe": False,
                "observerContributedItems": False, "projectTrustBypassed": False,
                "cases": [{"name": name, "handlerDiagnostic": False,
                           "nativeEntryPoint": "ActionUtil.invokeAction:CodeCompletion", "nativePopupShown": True,
                           "nativeSelectionMethod": "LookupImpl.finishLookup", "nativeInsertionMatched": True,
                           "observedLookupClass": "com.intellij.codeInsight.lookup.impl.LookupImpl",
                           "after": text, "observedItems": [{"lookup": "owned"}]} for name, text in probe.EXPECTED.items()]}

    def test_native_positive_evidence_is_bounded_to_all_real_action_cases(self):
        self.assertEqual(probe.assess(self.passing(), "owned", "a" * 64)["status"], "pass")

    def test_source_only_handler_only_and_empty_cases_cannot_pass(self):
        for mutate in (lambda n: n.update(cases=[]),
                       lambda n: n.update(cases=n["cases"][:3]),
                       lambda n: [c.update(handlerDiagnostic=True) for c in n["cases"]]):
            value = self.passing()
            mutate(value)
            with self.assertRaises(ValueError):
                probe.assess(value, "owned", "a" * 64)

    def test_fake_lookup_cache_items_or_trust_invalidates_result(self):
        for name in ("artificialSnapshotInjected", "lookupCreatedByProbe", "observerContributedItems", "projectTrustBypassed"):
            value = self.passing()
            value[name] = True
            with self.subTest(flag=name), self.assertRaisesRegex(ValueError, "bypass"):
                probe.assess(value, "owned", "a" * 64)

    def test_stale_invocation_or_production_jar_cannot_be_reused(self):
        for invocation, jar in (("foreign", "a" * 64), ("owned", "b" * 64)):
            with self.assertRaisesRegex(ValueError, "bind"):
                probe.assess(self.passing(), invocation, jar)

    def test_popup_and_exact_inserted_sql_are_both_required(self):
        for change in ({"nativePopupShown": False}, {"nativeSelectionMethod": "manual document replacement"},
                       {"after": "fabricated"}, {"observedLookupClass": "fake.Lookup"}):
            value = self.passing()
            value["cases"][0].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "lookup/selection"):
                probe.assess(value, "owned", "a" * 64)

    def test_default_cli_prepares_without_ever_launching(self):
        prepared = {"workspace": "/owned/prepared", "probeBuild": {"pluginSha256": "a" * 64}, "productionJarSha256": "b" * 64}
        with patch.object(sys, "argv", ["probe", "--sdk", "/sdk", "--app", "/app", "--workspace", "/owned"]), \
             patch.object(probe, "prepare", return_value=prepared), \
             patch.object(probe, "run", side_effect=AssertionError("No --run authorization")), \
             patch.object(probe.subprocess, "Popen", side_effect=AssertionError("No IDE may start")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main(), 0)

    def test_existing_workspace_rejected_before_sdk_or_app_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / ".tools/existing"
            workspace.mkdir(parents=True)
            with patch.object(probe, "ROOT", root), patch.object(probe, "app_layout", side_effect=AssertionError("No app access")):
                with self.assertRaisesRegex(ValueError, "existing profiles"):
                    probe.prepare(Path("/sdk"), workspace, Path("/app"))

    def test_unicode_prepare_and_report_with_cp1252_defaults_without_an_ide(self):
        """Exercise launcher I/O with a Windows-like default even on a UTF-8 host."""
        read_text, write_text = Path.read_text, Path.write_text

        def cp1252_read(path, encoding=None, errors=None):
            return read_text(path, encoding=encoding or "cp1252", errors=errors)

        def cp1252_write(path, data, encoding=None, errors=None, newline=None):
            return write_text(path, data, encoding=encoding or "cp1252", errors=errors, newline=newline)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "中文路径"
            contents = root / "应用"
            binary = contents / "bin"
            binary.mkdir(parents=True)
            (binary / "pycharm64.exe.vmoptions").write_text("# 中文配置\n-Xmx128m\n", encoding="utf-8")
            production = contents / "plugins/database/lib/database.jar"
            production.parent.mkdir(parents=True)
            production.write_bytes(b"test-only artifact, never loaded")
            manifest = {"plugins": [{"id": "dev.openpycharm.database", "jar": "plugins/database/lib/database.jar"}],
                        "sourceCommit": "fixture-中文"}
            (contents / "openpycharm-build.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            app = SimpleNamespace(sdk_root=contents, contents=contents, platform="windows", jcmd=binary / "jcmd.exe")
            process = SimpleNamespace(pid=1234, poll=lambda: 0, returncode=0)
            job = SimpleNamespace(assign_and_resume=lambda p: None)
            workspace = root / ".tools/窗口 中文"
            with patch.object(Path, "read_text", cp1252_read), patch.object(Path, "write_text", cp1252_write), \
                 patch.object(probe, "ROOT", root), patch.object(probe, "app_layout", return_value=app), \
                 patch.object(probe, "sdk_layout", return_value=SimpleNamespace(sdk_root=root / "SDK")), \
                 patch.object(probe, "verify_product_plugins"), \
                 patch.object(probe, "build_probe", return_value=(root / "observer", {"pluginSha256": "b" * 64})), \
                 patch.object(probe.uuid, "uuid4", return_value=SimpleNamespace(hex="owned")), \
                 patch.object(probe, "WindowsJob", return_value=job), \
                 patch.object(probe.subprocess, "Popen", return_value=process) as launch, \
                 patch.object(probe, "stop_owned", return_value={"status": "pass"}):
                # The emulation rejects Unicode without an explicit encoding; PYTHONUTF8 cannot hide regressions.
                with self.assertRaises(UnicodeEncodeError):
                    (root / "default-encoding-negative.txt").write_text("中文")
                prepared = probe.prepare(root / "SDK", workspace, contents)
                self.assertEqual(prepared["productionSourceCommit"], "fixture-中文")
                self.assertEqual(probe.prepare_profile(Path(prepared["profile"]), []), Path(prepared["properties"]))
                native = self.passing()
                native["plugin"]["jarSha256"] = prepared["productionJarSha256"]
                (workspace / "native-report.json").write_text(json.dumps(native, ensure_ascii=False), encoding="utf-8")
                result = probe.run(prepared, 60)
                self.assertEqual(result["assessment"]["status"], "pass")
                self.assertEqual(launch.call_count, 1)  # A mock only; no process or IDE starts in this control.
                (workspace / "native-report.json").unlink()
                with patch.object(probe.subprocess, "run", return_value=SimpleNamespace(stdout="线程 中文\n", stderr="诊断\n")) as dump:
                    self.assertEqual(probe.run(prepared, 60)["assessment"]["status"], "fail")
                    self.assertEqual(dump.call_args.kwargs["encoding"], "utf-8")
                    self.assertEqual(dump.call_args.kwargs["errors"], "replace")
            for name in ("prepared.json", "result.json", "probe.vmoptions"):
                self.assertIn("中文", (workspace / name).read_bytes().decode("utf-8"))
            self.assertIn("# 中文配置", (workspace / "probe.vmoptions").read_bytes().decode("utf-8"))
            self.assertEqual((workspace / "external-timeout-threads.txt").read_bytes().decode("utf-8"), "线程 中文\n诊断\n")


if __name__ == "__main__":
    unittest.main()
