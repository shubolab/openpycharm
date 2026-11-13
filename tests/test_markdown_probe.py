import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from markdown_probe import assess


class MarkdownColdEvidenceTests(unittest.TestCase):
    def report(self):
        return {"invocationId": "current", "status": "pass", "httpSettingsColdBefore": True,
                "migrationServiceColdBefore": True, "jcefStartedAfterConstruction": True,
                "httpSettingsCreatedAfter": True, "migrationServiceCreatedAfter": True, "nativeBrowserRendered": True,
                "panelClass": "org.intellij.plugins.markdown.ui.preview.jcef.MarkdownJCEFHtmlPanel",
                "renderedText": "Markdown preview 中文 current"}

    def test_cold_actual_panel_and_rendering_are_required(self):
        self.assertEqual(assess(self.report(), "current")["status"], "pass")
        mutations = [lambda report, key=key: report.update({key: False}) for key in (
            "httpSettingsColdBefore", "migrationServiceColdBefore", "jcefStartedAfterConstruction",
            "httpSettingsCreatedAfter", "migrationServiceCreatedAfter", "nativeBrowserRendered")]
        mutations += [lambda report: report.update(invocationId="stale"), lambda report: report.update(renderedText="current"),
                      lambda report: report.update(panelClass="generic.browser"), lambda report: report.update(status="fail"),
                      lambda report: report.update(cleanupFailure="owned resource not disposed")]
        for mutate in mutations:
            report = copy.deepcopy(self.report())
            mutate(report)
            with self.subTest(report=report), self.assertRaises(ValueError):
                assess(report, "current")


if __name__ == "__main__":
    unittest.main()
