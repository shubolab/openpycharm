import contextlib
import copy
import io
from pathlib import Path
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
